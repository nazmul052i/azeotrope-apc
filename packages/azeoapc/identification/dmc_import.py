"""
dmc_import.py -- AspenTech DMC vector file import.

Reads legacy AspenTech DMC / DMCplus data files and converts them into
pandas DataFrames suitable for identification.

Supported formats
-----------------
- ``.vec``  -- DMC vector file (one tag per file, header + data)
- ``.dep``  -- DMCplus dependent variable (CV) file
- ``.ind``  -- DMCplus independent variable (MV) file

The canonical .vec format is::

    TAG_NAME.EXT
    DESCRIPTION
    UNITS
    PERIOD (minutes)
    NPTS
    value1
    value2
    ...

``.dep`` and ``.ind`` files follow the same structure but may contain
slightly different header semantics (variable type metadata).

Edge-case handling
------------------
- Missing data sentinels: ``-9999``, ``-9999.0``, ``Missing``, ``N/A``,
  ``Bad``, ``#N/A``, empty strings
- European decimal format (comma as decimal separator)
- BOM markers (UTF-8 / UTF-16)
- Mixed line endings (CR, LF, CRLF)

Author : Azeotrope Process Control
License: Proprietary
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
from numpy.typing import NDArray

logger = logging.getLogger(__name__)

Vec = NDArray[np.float64]

# Sentinel values that represent missing data in DMC files.
_MISSING_SENTINELS = {
    "-9999", "-9999.0", "-9999.00", "-9999.000",
    "missing", "n/a", "bad", "#n/a", "nan", "",
}

# Recognised file extensions (case-insensitive).
_SUPPORTED_EXTENSIONS = {".vec", ".dep", ".ind"}


# =====================================================================
#  Low-level parsing helpers
# =====================================================================

def _strip_bom(text: str) -> str:
    """Remove UTF-8 / UTF-16 BOM if present."""
    if text.startswith("\ufeff"):
        return text[1:]
    return text


def _normalise_line_endings(text: str) -> str:
    """Normalise CRLF / CR to LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _parse_float(raw: str) -> Optional[float]:
    """Parse a string as a float, handling European decimal commas.

    Returns None if the value matches a missing-data sentinel.
    """
    s = raw.strip()
    if s.lower() in _MISSING_SENTINELS:
        return None

    # European decimal: replace comma with dot, but only when there is
    # no dot already (to avoid mangling thousands separators).
    if "," in s and "." not in s:
        s = s.replace(",", ".")

    try:
        val = float(s)
    except ValueError:
        logger.debug("Cannot parse '%s' as float -- treating as missing", raw.strip())
        return None

    # Catch numeric sentinels (-9999 variants).
    if val == -9999.0:
        return None
    return val


def _read_text(path: Union[str, Path]) -> str:
    """Read a file into a single string, handling encoding quirks."""
    p = Path(path)
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = p.read_text(encoding=enc)
            return _normalise_line_endings(_strip_bom(text))
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Cannot decode file {p} with any supported encoding")


# =====================================================================
#  Format detection
# =====================================================================

def detect_format(path: Union[str, Path]) -> str:
    """Detect file format from extension.

    Parameters
    ----------
    path : str or Path
        File path to inspect.

    Returns
    -------
    str
        One of ``"vec"``, ``"dep"``, ``"ind"``, or ``"unknown"``.
    """
    ext = Path(path).suffix.lower()
    if ext in _SUPPORTED_EXTENSIONS:
        return ext.lstrip(".")
    return "unknown"


# =====================================================================
#  Single-file readers
# =====================================================================

def read_vec(
    path: Union[str, Path],
) -> Tuple[str, Vec, Dict[str, Any]]:
    """Read a single DMC ``.vec`` file.

    Parameters
    ----------
    path : str or Path
        Path to the ``.vec`` file.

    Returns
    -------
    tag_name : str
        Tag name extracted from the file header (first line).
    data : NDArray[float64]
        1-D array of data values.  Missing values are ``np.nan``.
    metadata : dict
        Header information: ``description``, ``units``, ``period_min``
        (sample period in minutes), ``npts`` (declared point count),
        ``actual_npts`` (number of values actually read), ``source``.
    """
    text = _read_text(path)
    lines = [ln.strip() for ln in text.split("\n")]
    # Remove trailing empty lines.
    while lines and lines[-1] == "":
        lines.pop()

    if len(lines) < 5:
        raise ValueError(
            f"File {path} has only {len(lines)} lines -- expected at least 5 "
            "(tag, description, units, period, npts)"
        )

    tag_name = lines[0].strip()
    description = lines[1].strip()
    units = lines[2].strip()

    # Period -- might be integer or float.
    period_raw = lines[3].strip()
    try:
        period_min = float(period_raw.replace(",", "."))
    except ValueError:
        logger.warning(
            "Cannot parse period '%s' in %s -- defaulting to 1.0 min",
            period_raw, path,
        )
        period_min = 1.0

    # Number of points.
    npts_raw = lines[4].strip()
    try:
        npts = int(npts_raw)
    except ValueError:
        logger.warning(
            "Cannot parse npts '%s' in %s -- will read all remaining lines",
            npts_raw, path,
        )
        npts = -1

    # Data values start at line 5.
    raw_values = lines[5:]
    values: List[float] = []
    for v in raw_values:
        if v == "":
            continue
        parsed = _parse_float(v)
        values.append(parsed if parsed is not None else np.nan)

    data = np.array(values, dtype=np.float64)

    if npts >= 0 and len(data) != npts:
        logger.warning(
            "File %s declares npts=%d but %d values were read",
            path, npts, len(data),
        )

    metadata: Dict[str, Any] = {
        "description": description,
        "units": units,
        "period_min": period_min,
        "npts": npts,
        "actual_npts": len(data),
        "source": str(Path(path).resolve()),
        "format": "vec",
    }
    logger.info(
        "Read %d values for tag '%s' from %s (period=%.2f min)",
        len(data), tag_name, path, period_min,
    )
    return tag_name, data, metadata


def read_dep_ind(
    path: Union[str, Path],
) -> Tuple[str, Vec, Dict[str, Any]]:
    """Read a DMCplus ``.dep`` or ``.ind`` file.

    The format is structurally identical to ``.vec`` but carries
    additional semantics (dependent = CV, independent = MV).  This
    function delegates to :func:`read_vec` and augments the metadata
    with a ``variable_type`` field.

    Parameters
    ----------
    path : str or Path
        Path to the ``.dep`` or ``.ind`` file.

    Returns
    -------
    tag_name : str
        Tag name from the file header.
    data : NDArray[float64]
        1-D data array (``np.nan`` for missing values).
    metadata : dict
        Same as :func:`read_vec` plus ``variable_type`` (``"cv"`` or
        ``"mv"``).
    """
    ext = Path(path).suffix.lower()
    tag_name, data, metadata = read_vec(path)

    if ext == ".dep":
        metadata["variable_type"] = "cv"
        metadata["format"] = "dep"
    elif ext == ".ind":
        metadata["variable_type"] = "mv"
        metadata["format"] = "ind"
    else:
        metadata["variable_type"] = "unknown"
        metadata["format"] = ext.lstrip(".")

    return tag_name, data, metadata


# =====================================================================
#  Combine multiple single-tag files
# =====================================================================

def combine_single_tag_files(
    paths: Sequence[Union[str, Path]],
) -> pd.DataFrame:
    """Combine multiple single-tag files into one DataFrame.

    Each file contributes one column.  Columns are aligned by integer
    sample index.  If files have different sample periods, a warning is
    logged and data is aligned by the *shortest* series length (i.e.,
    no interpolation is performed -- the caller should pre-resample if
    needed).

    Parameters
    ----------
    paths : sequence of str or Path
        Paths to ``.vec``, ``.dep``, or ``.ind`` files.

    Returns
    -------
    pd.DataFrame
        DataFrame with one column per tag.  Index is a
        ``pd.RangeIndex`` (integer sample number).  Column metadata is
        stored in ``df.attrs["tag_metadata"]`` as a dict of dicts keyed
        by tag name.
    """
    if not paths:
        raise ValueError("No file paths provided")

    columns: Dict[str, Vec] = {}
    all_metadata: Dict[str, Dict[str, Any]] = {}
    periods: List[float] = []

    for p in paths:
        fmt = detect_format(p)
        if fmt in ("dep", "ind"):
            tag, data, meta = read_dep_ind(p)
        elif fmt == "vec":
            tag, data, meta = read_vec(p)
        else:
            logger.warning("Skipping unsupported file format: %s", p)
            continue

        # Handle duplicate tag names by appending a suffix.
        orig_tag = tag
        suffix = 1
        while tag in columns:
            tag = f"{orig_tag}_{suffix}"
            suffix += 1
            logger.warning(
                "Duplicate tag '%s' -- renamed to '%s'", orig_tag, tag
            )

        columns[tag] = data
        all_metadata[tag] = meta
        periods.append(meta.get("period_min", 1.0))

    # Check period consistency.
    unique_periods = set(periods)
    if len(unique_periods) > 1:
        logger.warning(
            "Files have different sample periods: %s -- "
            "alignment is by sample index only",
            sorted(unique_periods),
        )

    # Build DataFrame, padding shorter series with NaN.
    max_len = max(len(v) for v in columns.values())
    aligned: Dict[str, Vec] = {}
    for tag, data in columns.items():
        if len(data) < max_len:
            padded = np.full(max_len, np.nan, dtype=np.float64)
            padded[: len(data)] = data
            aligned[tag] = padded
        else:
            aligned[tag] = data

    df = pd.DataFrame(aligned)
    df.attrs["tag_metadata"] = all_metadata

    logger.info(
        "Combined %d tags into DataFrame (%d rows x %d cols)",
        len(columns), len(df), len(df.columns),
    )
    return df


# =====================================================================
#  Universal import entry point
# =====================================================================

def import_data(
    paths_or_dir: Union[str, Path, Sequence[Union[str, Path]]],
    extensions: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """Universal entry point for importing DMC data files.

    Accepts a single file, a list of files, or a directory.  When given
    a directory, all files matching the supported extensions are loaded.

    Parameters
    ----------
    paths_or_dir : str, Path, or sequence thereof
        A single file path, a list of file paths, or a directory path.
    extensions : sequence of str, optional
        File extensions to include when scanning a directory.  Defaults
        to ``[".vec", ".dep", ".ind"]``.

    Returns
    -------
    pd.DataFrame
        Combined DataFrame with one column per tag.  See
        :func:`combine_single_tag_files` for details.

    Raises
    ------
    ValueError
        If no valid files are found.
    """
    if extensions is None:
        extensions = [".vec", ".dep", ".ind"]
    # Normalise to lowercase.
    extensions = [e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions]

    # Determine file list.
    if isinstance(paths_or_dir, (str, Path)):
        p = Path(paths_or_dir)
        if p.is_dir():
            files = sorted(
                f for f in p.iterdir()
                if f.is_file() and f.suffix.lower() in extensions
            )
            if not files:
                raise ValueError(
                    f"No files with extensions {extensions} found in {p}"
                )
            logger.info("Found %d data files in directory %s", len(files), p)
        elif p.is_file():
            files = [p]
        else:
            raise ValueError(f"Path {p} is neither a file nor a directory")
    else:
        files = [Path(f) for f in paths_or_dir]
        if not files:
            raise ValueError("Empty file list provided")

    return combine_single_tag_files(files)
