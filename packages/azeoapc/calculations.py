"""User calculation runtime.

Calculations are full Python scripts that run before/after the MPC each cycle.
They have access to all live MV/CV/DV objects, persistent user state, the
SimEngine, and can import any Python module (numpy, scipy, math, ...).

Each calculation is a Python source string. When the user clicks Apply, the
source is compiled with `compile()`. The compiled code object is `exec()`d
each cycle inside a namespace that exposes:

  cvs[tag]            -- live CV object
  mvs[tag]            -- live MV object
  dvs[tag]            -- live DV object
  cv[i], mv[i], dv[i] -- index access
  user                -- persistent dict (survives between cycles)
  t                   -- current sim time (minutes)
  cycle               -- current cycle number
  dt                  -- sample time
  engine              -- SimEngine reference (advanced)
  np, math            -- pre-imported

Top-level code in the script runs each cycle. Users can also define a `run()`
function and we'll call it instead (lets them keep helpers/classes at module
scope without re-creating them every cycle).

If a calculation defines `init()`, it's called once when the calc is enabled
or applied (use it to set up persistent state).

Errors in a calculation auto-disable it and log a traceback to the activity
log; the simulation continues.
"""
from __future__ import annotations

import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Calculation:
    """A user-defined calculation."""
    name: str
    description: str = ""
    code: str = ""
    is_input: bool = True       # True = runs before MPC, False = runs after
    sequence: int = 0           # execution order within input/output group
    enabled: bool = True

    # Compiled state (set by CalculationRunner.compile())
    _code_obj: Optional[Any] = field(default=None, repr=False)
    _module_ns: Optional[Dict[str, Any]] = field(default=None, repr=False)
    _has_run_fn: bool = False
    _has_init_fn: bool = False

    # Runtime state
    last_status: str = "READY"      # READY | OK | ERROR | DISABLED | WARN
    last_error: str = ""
    last_time_ms: float = 0.0
    last_traceback: str = ""
    run_count: int = 0
    error_count: int = 0


class CalculationRunner:
    """Compiles, executes, and manages user calculations.

    The runner owns the namespace dict that's passed to each `exec()`.
    When the user calls `compile()` on a calc, the source is compiled and
    a fresh module-level namespace is created. When `init()` is defined,
    it's run once after compile.

    Each cycle, the runner walks the input calcs (sorted by sequence),
    then the simulator runs the MPC, then the runner walks the output calcs.
    """

    # Master enable toggles -- bypass ALL input or output calcs at once
    input_enabled: bool = True
    output_enabled: bool = True

    def __init__(self, engine):
        self.engine = engine
        self.input_calcs: List[Calculation] = []
        self.output_calcs: List[Calculation] = []

        # Persistent user state shared across all calculations
        self.user_state: Dict[str, Any] = {}

        # Activity log -- list of (timestamp, level, message) tuples
        self.activity: List[tuple] = []
        self.max_activity = 200

        self.input_enabled = True
        self.output_enabled = True

    # ─────────────────────────────────────────────────────────────────────
    # Calc management
    # ─────────────────────────────────────────────────────────────────────
    def add_input(self, calc: Calculation) -> Calculation:
        calc.is_input = True
        if calc.sequence == 0:
            calc.sequence = max((c.sequence for c in self.input_calcs), default=0) + 1
        self.input_calcs.append(calc)
        self.input_calcs.sort(key=lambda c: c.sequence)
        return calc

    def add_output(self, calc: Calculation) -> Calculation:
        calc.is_input = False
        if calc.sequence == 0:
            calc.sequence = max((c.sequence for c in self.output_calcs), default=0) + 1
        self.output_calcs.append(calc)
        self.output_calcs.sort(key=lambda c: c.sequence)
        return calc

    def remove(self, calc: Calculation):
        if calc in self.input_calcs:
            self.input_calcs.remove(calc)
        if calc in self.output_calcs:
            self.output_calcs.remove(calc)

    def all_calcs(self) -> List[Calculation]:
        """Combined list, input then output, each in sequence order."""
        return list(self.input_calcs) + list(self.output_calcs)

    def reorder(self, calc: Calculation, direction: int):
        """Move a calc up (-1) or down (+1) within its group."""
        group = self.input_calcs if calc.is_input else self.output_calcs
        if calc not in group:
            return
        idx = group.index(calc)
        new_idx = idx + direction
        if 0 <= new_idx < len(group):
            group.pop(idx)
            group.insert(new_idx, calc)
            for i, c in enumerate(group):
                c.sequence = i + 1

    # ─────────────────────────────────────────────────────────────────────
    # Compile
    # ─────────────────────────────────────────────────────────────────────
    def compile(self, calc: Calculation) -> tuple:
        """Compile a calc's source. Returns (success, error_message).

        On success: stores the code object and a fresh module namespace
        on the calc. If the script defines `init()`, runs it now.
        On failure: leaves the previous code object in place (so the
        running version keeps working) and returns the error.
        """
        try:
            code_obj = compile(calc.code, f"<calc:{calc.name}>", "exec")
        except SyntaxError as e:
            calc.last_status = "ERROR"
            calc.last_error = f"SyntaxError: {e.msg} (line {e.lineno})"
            calc.last_traceback = traceback.format_exc()
            return (False, calc.last_error)

        # Build a fresh module-level namespace for this calc.
        # This is where classes, top-level functions, and module-level
        # variables live across cycles. Calling exec() repopulates only
        # the local variables; def/class survive.
        ns: Dict[str, Any] = self._make_namespace()

        try:
            # First exec() defines all top-level functions and classes
            exec(code_obj, ns)
        except Exception as e:
            calc.last_status = "ERROR"
            calc.last_error = f"{type(e).__name__}: {e}"
            calc.last_traceback = traceback.format_exc()
            return (False, calc.last_error)

        calc._code_obj = code_obj
        calc._module_ns = ns
        calc._has_run_fn = callable(ns.get("run"))
        calc._has_init_fn = callable(ns.get("init"))

        # Run init() if defined
        if calc._has_init_fn:
            try:
                ns["init"]()
            except Exception as e:
                calc.last_status = "ERROR"
                calc.last_error = f"init() raised {type(e).__name__}: {e}"
                calc.last_traceback = traceback.format_exc()
                return (False, calc.last_error)

        calc.last_status = "OK"
        calc.last_error = ""
        calc.last_traceback = ""
        return (True, "")

    def _make_namespace(self) -> Dict[str, Any]:
        """Build the module-level namespace exposed to user code.

        Available names:
          cvs, mvs, dvs       -- dict[tag] -> live variable object
          cv, mv, dv          -- list, indexable
          user                -- persistent dict
          t                   -- current sim time (min)
          cycle               -- cycle counter
          dt                  -- sample time (min)
          engine              -- SimEngine
          np, math            -- pre-imports
          log                 -- function: log(msg, level='info')
        """
        import numpy as np
        import math

        eng = self.engine
        cfg = eng.cfg

        # Build dict-by-tag and list-by-index views of the live variables
        cvs_by_tag = {cv.tag: cv for cv in cfg.cvs}
        mvs_by_tag = {mv.tag: mv for mv in cfg.mvs}
        dvs_by_tag = {dv.tag: dv for dv in cfg.dvs}

        # Capture self for the log closure
        runner = self

        def log_fn(msg, level="info"):
            runner._log(level, str(msg))

        ns = {
            # Variable access
            "cvs": cvs_by_tag,
            "mvs": mvs_by_tag,
            "dvs": dvs_by_tag,
            "cv": cfg.cvs,
            "mv": cfg.mvs,
            "dv": cfg.dvs,
            # Runtime state
            "user": self.user_state,
            "t": eng.cycle * cfg.sample_time,
            "cycle": eng.cycle,
            "dt": cfg.sample_time,
            "engine": eng,
            # Standard library
            "np": np,
            "numpy": np,
            "math": math,
            # Logging
            "log": log_fn,
            # Built-ins (pass-through; not sandboxed)
            "__builtins__": __builtins__,
        }
        return ns

    def _refresh_namespace_runtime_vars(self, calc: Calculation):
        """Update t, cycle in the calc's namespace before each run.

        We don't rebuild the whole namespace -- that would wipe out any
        classes/functions/state defined at module level. We only refresh
        the per-cycle live values.
        """
        if calc._module_ns is None:
            return
        eng = self.engine
        ns = calc._module_ns
        ns["t"] = eng.cycle * eng.cfg.sample_time
        ns["cycle"] = eng.cycle
        ns["dt"] = eng.cfg.sample_time

    def compile_all(self) -> int:
        """Compile every calc. Returns the number of compile errors."""
        errors = 0
        for calc in self.all_calcs():
            ok, _ = self.compile(calc)
            if not ok:
                errors += 1
        return errors

    # ─────────────────────────────────────────────────────────────────────
    # Execute
    # ─────────────────────────────────────────────────────────────────────
    def run_inputs(self):
        if not self.input_enabled:
            return
        for calc in self.input_calcs:
            self._run_one(calc)

    def run_outputs(self):
        if not self.output_enabled:
            return
        for calc in self.output_calcs:
            self._run_one(calc)

    def _run_one(self, calc: Calculation):
        if not calc.enabled or calc._code_obj is None:
            return
        if calc.last_status == "ERROR":
            # auto-disabled until user re-applies
            return

        self._refresh_namespace_runtime_vars(calc)

        t0 = time.perf_counter()
        try:
            ns = calc._module_ns
            if calc._has_run_fn:
                ns["run"]()
            else:
                # Top-level script with no run() -- exec the code object.
                # Note: this re-executes def/class statements but that's
                # cheap and harmless (they re-bind the same names).
                exec(calc._code_obj, ns)

            calc.last_status = "OK"
            calc.last_error = ""
            calc.last_traceback = ""
            calc.run_count += 1
        except Exception as e:
            calc.last_status = "ERROR"
            calc.last_error = f"{type(e).__name__}: {e}"
            calc.last_traceback = traceback.format_exc()
            calc.error_count += 1
            self._log("error",
                      f"{calc.name} {type(e).__name__}: {e} (auto-disabled)")
        finally:
            calc.last_time_ms = (time.perf_counter() - t0) * 1000.0

    def test_run(self, calc: Calculation) -> tuple:
        """Run a single calculation once for testing.
        Returns (success, error_message).
        """
        if calc._code_obj is None:
            ok, err = self.compile(calc)
            if not ok:
                return (False, err)
        # Reset error state so the test actually runs
        calc.last_status = "READY"
        self._run_one(calc)
        if calc.last_status == "ERROR":
            return (False, calc.last_error)
        return (True, f"OK ({calc.last_time_ms:.2f} ms)")

    def reset_state(self):
        """Clear all user state and re-init each calc."""
        self.user_state.clear()
        for calc in self.all_calcs():
            if calc._code_obj is not None and calc._has_init_fn:
                try:
                    calc._module_ns["user"] = self.user_state
                    calc._module_ns["init"]()
                except Exception as e:
                    self._log("error",
                              f"{calc.name} init() failed: {e}")

    # ─────────────────────────────────────────────────────────────────────
    # Live state inspector (for the GUI)
    # ─────────────────────────────────────────────────────────────────────
    def get_live_state(self) -> List[tuple]:
        """Return a list of (name, value, source) tuples for the GUI panel.

        Includes:
          - All entries in user_state
          - Tunable parameters (cv.weight, cv.concern_*, mv.move_suppress, etc.)
          - Last values of cv.value, mv.value
        """
        items = []
        # User state
        for k, v in sorted(self.user_state.items()):
            items.append((f"user.{k}", _short_repr(v), "user state"))

        cfg = self.engine.cfg
        # CV tuning
        for cv in cfg.cvs:
            items.append((f"{cv.tag}.value", f"{cv.value:.4g}", "CV"))
            items.append((f"{cv.tag}.setpoint", f"{cv.setpoint:.4g}", "CV"))
            items.append((f"{cv.tag}.weight", f"{cv.weight:.4g}", "tuning"))
            items.append((f"{cv.tag}.concern_lo", f"{cv.concern_lo:.4g}", "tuning"))
            items.append((f"{cv.tag}.concern_hi", f"{cv.concern_hi:.4g}", "tuning"))

        # MV tuning
        for mv in cfg.mvs:
            items.append((f"{mv.tag}.value", f"{mv.value:.4g}", "MV"))
            items.append((f"{mv.tag}.move_suppress", f"{mv.move_suppress:.4g}", "tuning"))
            items.append((f"{mv.tag}.cost", f"{mv.cost:.4g}", "tuning"))
            items.append((f"{mv.tag}.cost_rank", str(mv.cost_rank), "tuning"))

        # DV values
        for dv in cfg.dvs:
            items.append((f"{dv.tag}.value", f"{dv.value:.4g}", "DV"))

        return items

    # ─────────────────────────────────────────────────────────────────────
    # Activity log
    # ─────────────────────────────────────────────────────────────────────
    def _log(self, level: str, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.activity.append((ts, level, msg))
        if len(self.activity) > self.max_activity:
            self.activity.pop(0)

    def clear_log(self):
        self.activity.clear()


def _short_repr(v: Any, maxlen: int = 60) -> str:
    """Compact repr for display in the live state panel."""
    try:
        if isinstance(v, (int, float, bool, str)):
            r = repr(v)
        elif hasattr(v, "shape"):  # numpy array
            r = f"array{tuple(v.shape)} dtype={v.dtype}"
        elif isinstance(v, (list, tuple)):
            r = repr(v[:5]) + ("..." if len(v) > 5 else "")
        elif isinstance(v, dict):
            r = "{" + ", ".join(f"{k}:..." for k in list(v)[:3]) + "}"
        else:
            r = repr(v)
        if len(r) > maxlen:
            r = r[:maxlen - 3] + "..."
        return r
    except Exception:
        return f"<{type(v).__name__}>"
