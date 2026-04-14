"""Generate a step-test CSV from the cumene hot oil heater simulator.

The cumene heater lives in a sibling repo (D:/development/GitHub/simulation).
This script imports its plant ODE directly -- no async engine, no Qt, no
SharedDataStore -- and runs a deterministic step sequence in simulation
time. The output CSV is in the format apc_ident expects: a Time column
followed by one column per tag.

Variables driven (3 MVs + 1 DV):
    FCV-410   fuel-gas valve demand   (ctx.demand_fuel,   0..1)
    SC-400    pump speed demand       (ctx.demand_pump,   0..1)
    FCV-411   air damper demand       (ctx.demand_air,    0..1)
    XI-490    ambient temp offset     (ctx.ambient_temp_offset, degF)

Variables logged (5 CVs):
    TIT-400   T_supply        supply header temperature (degF)
    TIT-402   T_coil_out      heater coil outlet temperature (degF)
    TIT-412   T_stack         stack flue gas temperature (degF)
    XI-410    excess_air_pct  excess air percentage (%)
    AIT-410   O2_pct          stack O2 (%)

Run from the repo root:

    python apps/apc_ident/examples/cumene/generate_step_test.py

Output:

    apps/apc_ident/examples/cumene/cumene_step_test.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np


# ── Locate the cumene simulator package ─────────────────────────────────
# The simulator lives in a sibling repo. Add its src/ to sys.path so we
# can ``from simulator.cumene_hotoil_process import ...``
_SIM_REPO = r"D:/development/GitHub/simulation/src"
if not os.path.isdir(_SIM_REPO):
    sys.exit(
        f"ERROR: cumene simulator not found at {_SIM_REPO}. "
        "Edit _SIM_REPO at the top of this file to point at your "
        "checkout of github.com/.../simulation."
    )
sys.path.insert(0, _SIM_REPO)

from simulator.cumene_hotoil_process import hotoil_state_vector as sv  # noqa: E402
from simulator.cumene_hotoil_process.hotoil_ode_system import (        # noqa: E402
    ODEContext, derivatives, compute_outputs,
)


# ── Step-test schedule ──────────────────────────────────────────────────
@dataclass
class Step:
    """One leg of the test schedule."""
    t_start_min: float          # simulation minute when this leg begins
    name: str                   # human label (for the events log)
    fuel: float = 0.65          # ctx.demand_fuel
    pump: float = 1.00          # ctx.demand_pump
    air:  float = 0.65          # ctx.demand_air
    amb:  float = 0.0           # ctx.ambient_temp_offset (degF)


SCHEDULE: List[Step] = [
    Step(0,   "warmup",            fuel=0.65, pump=1.00, air=0.65, amb=0.0),
    Step(30,  "fuel up   (+0.05)", fuel=0.70, pump=1.00, air=0.65, amb=0.0),
    Step(90,  "fuel down (-0.05)", fuel=0.60, pump=1.00, air=0.65, amb=0.0),
    Step(150, "fuel back",          fuel=0.65, pump=1.00, air=0.65, amb=0.0),
    Step(210, "pump down (-0.05)", fuel=0.65, pump=0.95, air=0.65, amb=0.0),
    Step(270, "pump back",          fuel=0.65, pump=1.00, air=0.65, amb=0.0),
    Step(330, "pump down (-0.08)", fuel=0.65, pump=0.92, air=0.65, amb=0.0),
    Step(390, "pump back",          fuel=0.65, pump=1.00, air=0.65, amb=0.0),
    Step(450, "air up   (+0.07)",  fuel=0.65, pump=1.00, air=0.72, amb=0.0),
    Step(510, "air down (-0.05)",  fuel=0.65, pump=1.00, air=0.60, amb=0.0),
    Step(570, "air back",           fuel=0.65, pump=1.00, air=0.65, amb=0.0),
    Step(630, "ambient +10 (DV)",  fuel=0.65, pump=1.00, air=0.65, amb=10.0),
]
TOTAL_MIN = 720    # also the start of the trailing hold-out tail


# ── Output schema ───────────────────────────────────────────────────────
# Tags are written as columns in this exact order. The first 4 are MVs/DVs
# (inputs), the last 5 are CVs (measurements). Names match the ISA tags
# from the cumene_hotoil_process tag registry.
INPUT_COLS = [
    ("FCV-410.SP", "fuel"),     # MV1
    ("SC-400.SP",  "pump"),     # MV2
    ("FCV-411.SP", "air"),      # MV3
    ("XI-490.PV",  "amb"),      # DV1 -- ambient temperature offset
]
OUTPUT_COLS = [
    ("TIT-400.PV", "T_supply"),
    ("TIT-402.PV", "T_coil_out"),
    ("TIT-412.PV", "T_stack"),
    ("XI-410.PV",  "excess_air_pct"),
    ("AIT-410.PV", "O2_pct"),
]


# ── Driver ──────────────────────────────────────────────────────────────
def schedule_at(t_min: float) -> Step:
    """Return the step that's active at the given simulation minute."""
    active = SCHEDULE[0]
    for s in SCHEDULE:
        if t_min >= s.t_start_min:
            active = s
        else:
            break
    return active


def run(out_csv: str, *, sample_min: float = 1.0,
         micro_steps: int = 60, total_min: float = TOTAL_MIN) -> None:
    """Drive the cumene plant ODE through the step schedule and write a CSV.

    Args:
        out_csv: path to write the .csv to
        sample_min: how often to log a row (minutes)
        micro_steps: integration sub-steps per minute (1/min = 1 sec)
        total_min: total simulation length
    """
    print(f"Cumene heater step test")
    print(f"  output    : {out_csv}")
    print(f"  duration  : {total_min} min")
    print(f"  sample    : {sample_min} min")
    print(f"  integrator: forward Euler, {micro_steps} micro-steps/min")
    print()

    # Initial conditions
    y = sv.initial_state()
    ctx = ODEContext()

    # Pre-warm: integrate 5 minutes at the schedule's first leg so the
    # initial state really is steady
    s0 = SCHEDULE[0]
    ctx.demand_fuel = s0.fuel
    ctx.demand_pump = s0.pump
    ctx.demand_air = s0.air
    ctx.ambient_temp_offset = s0.amb
    micro_dt = 60.0 / micro_steps    # seconds (1 minute / micro_steps)
    for _ in range(5 * micro_steps):
        dydt = derivatives(0.0, y, ctx)
        y = y + dydt * micro_dt
        _clamp(y)

    rows: List[List[float]] = []
    t_min = 0.0
    n_samples = int(round(total_min / sample_min)) + 1
    last_step_name = ""
    started = time.perf_counter()

    for k in range(n_samples):
        t_min = k * sample_min

        # Apply the active step's demand values BEFORE integration so
        # the response captures the step at the right sample.
        s = schedule_at(t_min)
        ctx.demand_fuel = s.fuel
        ctx.demand_pump = s.pump
        ctx.demand_air = s.air
        ctx.ambient_temp_offset = s.amb
        if s.name != last_step_name:
            print(f"  t={t_min:6.0f} min  -> {s.name}")
            last_step_name = s.name

        # Integrate one sample period
        n_micro = int(round(sample_min * micro_steps))
        for _ in range(n_micro):
            dydt = derivatives(t_min * 60.0, y, ctx)
            y = y + dydt * micro_dt
            _clamp(y)

        # Snapshot outputs
        outputs = compute_outputs(y, ctx)
        row = [t_min]
        for _, key in INPUT_COLS:
            row.append({
                "fuel": ctx.demand_fuel,
                "pump": ctx.demand_pump,
                "air":  ctx.demand_air,
                "amb":  ctx.ambient_temp_offset,
            }[key])
        for _, key in OUTPUT_COLS:
            row.append(float(outputs[key]))
        rows.append(row)

    elapsed = time.perf_counter() - started
    print()
    print(f"Done in {elapsed:.1f}s wall, {len(rows)} samples")

    # Write CSV
    os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        header = ["Time_min"] + [c[0] for c in INPUT_COLS] + [c[0] for c in OUTPUT_COLS]
        w.writerow(header)
        for row in rows:
            w.writerow([f"{row[0]:.2f}"] + [f"{v:.6g}" for v in row[1:]])
    size_kb = os.path.getsize(out_csv) / 1024.0
    print(f"Wrote {out_csv} ({size_kb:.1f} KB)")


def _clamp(y: np.ndarray) -> None:
    """Clamp state to physical bounds (mirrors HotOilEngine._step_plant)."""
    for idx in sv.PASS_FLUID + [sv.T_CONV_OUT, sv.T_SUPPLY, sv.T_RETURN,
                                  sv.T_SURGE_DRUM, sv.T_LO_SUPPLY]:
        y[idx] = np.clip(y[idx], 100.0, 800.0)
    for idx in sv.PASS_METAL:
        y[idx] = np.clip(y[idx], 100.0, 900.0)
    for idx in sv.HX_OUT_TEMPS:
        y[idx] = np.clip(y[idx], 100.0, 800.0)
    y[sv.T_GAS_ZONE1] = np.clip(y[sv.T_GAS_ZONE1], 300.0, 2000.0)
    y[sv.T_GAS_ZONE2] = np.clip(y[sv.T_GAS_ZONE2], 300.0, 1800.0)
    y[sv.T_FLUE_OUT]  = np.clip(y[sv.T_FLUE_OUT], 300.0, 1200.0)
    y[sv.T_REFR_INT]  = np.clip(y[sv.T_REFR_INT], 300.0, 1500.0)
    y[sv.T_REFR_COLD] = np.clip(y[sv.T_REFR_COLD], 280.0, 800.0)
    for idx in sv.HEATER_VALVES + sv.HX_VALVES:
        y[idx] = np.clip(y[idx], 0.0, 1.0)
    y[sv.P_DRAFT]    = np.clip(y[sv.P_DRAFT], -500.0, 0.0)
    y[sv.P_FUEL_GAS] = np.clip(y[sv.P_FUEL_GAS], 50000.0, 500000.0)


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--out", default=os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "cumene_step_test.csv"),
        help="output CSV path",
    )
    p.add_argument("--sample-min", type=float, default=1.0,
                   help="sample period (minutes)")
    p.add_argument("--micro-steps", type=int, default=60,
                   help="integration sub-steps per simulation minute")
    p.add_argument("--total-min", type=float, default=TOTAL_MIN,
                   help="total simulation length in minutes")
    args = p.parse_args()
    run(args.out, sample_min=args.sample_min,
        micro_steps=args.micro_steps, total_min=args.total_min)


if __name__ == "__main__":
    main()
