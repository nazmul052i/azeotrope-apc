"""Safe expression evaluator for calculated (derived) process variables.

Engineers frequently need derived variables that don't exist as raw tags
in the historian: pressure-compensated temperatures, tray-to-tray delta-T,
flow ratios, rates of change, etc.

This module provides a safe, sandboxed expression evaluator that:

- Supports standard arithmetic operators (+, -, *, /, **, %)
- Provides 20+ built-in functions (abs, sqrt, log, exp, sin, cos,
  rolling_mean, rolling_std, diff, lag, clip, etc.)
- References DataFrame columns by name in curly braces: ``{TI101}``
- Validates expressions via AST inspection (no imports, no attribute
  access, no builtins abuse)
- Returns pandas Series indexed to the source DataFrame

Usage::

    expr = "{upper_tray_T} - {lower_tray_T}"
    result = evaluate_expression(expr, df)

    expr = "rolling_mean({TI101}, 10) + 15 * ({P_ref} - {pressure})"
    result = evaluate_expression(expr, df)

    # Batch add
    tags = [
        CalculatedTag("Delta_T", "{TI101} - {TI102}", "degC"),
        CalculatedTag("Flow_Ratio", "{FI101} / {FI102}", ""),
    ]
    df_out = add_calculated_tags(df, tags)
"""
from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Column reference pattern: {column_name}
_COL_PATTERN = re.compile(r"\{([^}]+)\}")


@dataclass
class CalculatedTag:
    """Specification for a derived variable."""
    name: str
    expression: str
    unit: str = ""
    description: str = ""
    enabled: bool = True


# ---------------------------------------------------------------------------
# Safe math namespace
# ---------------------------------------------------------------------------
def _build_namespace(df: pd.DataFrame) -> Dict:
    """Build the evaluation namespace with safe functions and column refs."""
    ns: Dict = {}

    # Safe math functions
    ns["abs"] = np.abs
    ns["sqrt"] = np.sqrt
    ns["log"] = np.log
    ns["log10"] = np.log10
    ns["exp"] = np.exp
    ns["sin"] = np.sin
    ns["cos"] = np.cos
    ns["tan"] = np.tan
    ns["sign"] = np.sign
    ns["clip"] = np.clip
    ns["min"] = np.minimum
    ns["max"] = np.maximum
    ns["pow"] = np.power
    ns["pi"] = np.pi
    ns["e"] = np.e

    # Rolling window functions (center-aligned for process data)
    def rolling_mean(series, window):
        return pd.Series(series).rolling(int(window), center=True, min_periods=1).mean().values

    def rolling_std(series, window):
        return pd.Series(series).rolling(int(window), center=True, min_periods=1).std().values

    def rolling_max(series, window):
        return pd.Series(series).rolling(int(window), center=True, min_periods=1).max().values

    def rolling_min(series, window):
        return pd.Series(series).rolling(int(window), center=True, min_periods=1).min().values

    ns["rolling_mean"] = rolling_mean
    ns["rolling_std"] = rolling_std
    ns["rolling_max"] = rolling_max
    ns["rolling_min"] = rolling_min

    # Temporal functions
    def diff(series, periods=1):
        return pd.Series(series).diff(int(periods)).values

    def lag(series, periods=1):
        return pd.Series(series).shift(int(periods)).values

    ns["diff"] = diff
    ns["lag"] = lag

    # Aggregate references
    ns["mean"] = lambda series: np.nanmean(series)
    ns["std"] = lambda series: np.nanstd(series)
    ns["median"] = lambda series: np.nanmedian(series)

    # Add DataFrame columns as variables
    for col in df.columns:
        ns[col] = df[col].values.astype(np.float64)

    return ns


# ---------------------------------------------------------------------------
# AST validation
# ---------------------------------------------------------------------------
_SAFE_NODES = {
    ast.Module, ast.Expr, ast.Expression,
    ast.BinOp, ast.UnaryOp, ast.Compare,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd,
    ast.Num, ast.Constant,
    ast.Name, ast.Load,
    ast.Call,
    ast.IfExp,
    ast.BoolOp, ast.And, ast.Or, ast.Not,
    ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq,
    ast.Tuple, ast.List,
}


def _validate_ast(expression: str):
    """Validate expression AST for safety.

    Blocks: imports, attribute access, starred expressions,
    subscript operations on non-data objects, and any non-arithmetic nodes.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Invalid expression syntax: {e}")

    for node in ast.walk(tree):
        if type(node) not in _SAFE_NODES:
            raise ValueError(
                f"Unsafe expression element: {type(node).__name__}. "
                f"Only arithmetic expressions and safe functions are allowed.")


# ---------------------------------------------------------------------------
# Expression evaluation
# ---------------------------------------------------------------------------
def evaluate_expression(
    expression: str,
    df: pd.DataFrame,
) -> pd.Series:
    """Evaluate an expression against a DataFrame and return a Series.

    Column references use curly braces: ``{column_name}``.

    Parameters
    ----------
    expression : str
        Arithmetic expression (e.g. ``"{TI101} - {TI102}"``).
    df : DataFrame
        Source data.

    Returns
    -------
    Series
        Result indexed to the DataFrame.
    """
    # Replace {col} references with bare variable names
    col_refs = _COL_PATTERN.findall(expression)
    expr_clean = expression
    for col in col_refs:
        if col not in df.columns:
            raise ValueError(f"Column '{col}' not found in DataFrame")
        # Replace {col} with a safe identifier
        safe_name = col.replace(" ", "_").replace("-", "_").replace(".", "_")
        expr_clean = expr_clean.replace(f"{{{col}}}", safe_name)

    # Validate AST
    _validate_ast(expr_clean)

    # Build namespace
    ns = _build_namespace(df)
    # Add safe-named references for columns with special characters
    for col in col_refs:
        safe_name = col.replace(" ", "_").replace("-", "_").replace(".", "_")
        if safe_name != col:
            ns[safe_name] = df[col].values.astype(np.float64)

    # Evaluate
    try:
        result = eval(expr_clean, {"__builtins__": {}}, ns)  # noqa: S307
    except Exception as e:
        raise ValueError(f"Expression evaluation failed: {e}")

    if isinstance(result, np.ndarray):
        return pd.Series(result, index=df.index, name="calculated")
    elif isinstance(result, (int, float)):
        return pd.Series(result, index=df.index, name="calculated")
    else:
        return pd.Series(np.asarray(result), index=df.index, name="calculated")


def add_calculated_tags(
    df: pd.DataFrame,
    tags: List[CalculatedTag],
) -> pd.DataFrame:
    """Batch-add calculated tags to a DataFrame.

    Returns a copy of df with new columns appended.
    """
    df_out = df.copy()
    for tag in tags:
        if not tag.enabled:
            continue
        try:
            result = evaluate_expression(tag.expression, df_out)
            df_out[tag.name] = result
        except Exception as e:
            logger.warning("Failed to evaluate '%s': %s", tag.name, e)
    return df_out
