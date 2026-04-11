"""Model bundle (.apcmodel) -- the handoff format between apc_ident and apc_architect.

A single HDF5 file containing everything apc_architect needs to consume an
identified model: tag lists (the link to controller variables), FIR
coefficients with confidence bands, the cumulative step response, and a
state-space realisation derived via ERA so the architect's SimEngine can
build a StateSpacePlant immediately.

Schema layout (version 1):

  /metadata                     (group, attrs only)
      schema_version            int
      name                      string
      created                   ISO8601 string
      dt_seconds                float
      ident_method              string  (dls | cor | ridge)
      ident_n_coeff             int
      ident_alpha               float
      ident_smoothing           string
      source_csv                string
      source_project            string
      fit_summary_json          string  (per-channel R^2/RMSE/Ljung-Box)

  /tags
      mvs                       string array (variable names: "FIC-101.SP")
      cvs                       string array
      dvs                       string array (may be empty)

  /fir
      coefficients              float64 [ny, n_coeff, nu]
      confidence_lo             float64 [ny, n_coeff, nu]   (optional)
      confidence_hi             float64 [ny, n_coeff, nu]   (optional)

  /step_response
      coefficients              float64 [ny, n_coeff, nu]   (cumsum of FIR)
      gain_matrix               float64 [ny, nu]
      settling_index            int32   [ny, nu]

  /state_space
      A                         float64 [nx, nx]
      B                         float64 [nx, nu]    (Bu only -- DVs not identified)
      C                         float64 [ny, nx]
      D                         float64 [ny, nu]
      u0                        float64 [nu]        (operating point)
      y0                        float64 [ny]
      era_order                 int                 (number of states retained)
"""
from __future__ import annotations

import datetime
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from .control_model import ControlModel, from_fir
from .fir_ident import IdentResult


SCHEMA_VERSION = 1
BUNDLE_EXT = ".apcmodel"


# ---------------------------------------------------------------------------
# Dataclass returned by load_model_bundle
# ---------------------------------------------------------------------------
@dataclass
class ModelBundle:
    """In-memory representation of an .apcmodel file.

    The state-space matrices are arranged for direct consumption by
    apc_architect's StateSpacePlant: discrete-time, deviation-variable
    form. ``u0`` and ``y0`` give the operating point so the architect
    can convert deviations back to engineering units.
    """
    name: str
    dt: float
    mv_tags: List[str]
    cv_tags: List[str]
    dv_tags: List[str] = field(default_factory=list)

    fir: Optional[np.ndarray] = None              # (ny, n_coeff, nu)
    confidence_lo: Optional[np.ndarray] = None
    confidence_hi: Optional[np.ndarray] = None
    step: Optional[np.ndarray] = None
    gain_matrix: Optional[np.ndarray] = None
    settling_index: Optional[np.ndarray] = None

    A: Optional[np.ndarray] = None
    B: Optional[np.ndarray] = None
    C: Optional[np.ndarray] = None
    D: Optional[np.ndarray] = None
    u0: Optional[np.ndarray] = None
    y0: Optional[np.ndarray] = None
    era_order: int = 0

    # Provenance + metadata
    schema_version: int = SCHEMA_VERSION
    created: str = ""
    ident_method: str = ""
    ident_n_coeff: int = 0
    ident_alpha: float = 0.0
    ident_smoothing: str = ""
    source_csv: str = ""
    source_project: str = ""
    fit_summary: Dict[str, Any] = field(default_factory=dict)

    @property
    def ny(self) -> int:
        return self.fir.shape[0] if self.fir is not None else len(self.cv_tags)

    @property
    def nu(self) -> int:
        return self.fir.shape[2] if self.fir is not None else len(self.mv_tags)

    @property
    def n_coeff(self) -> int:
        return self.fir.shape[1] if self.fir is not None else 0

    @property
    def nx(self) -> int:
        return self.A.shape[0] if self.A is not None else 0

    def to_control_model(self, name: Optional[str] = None) -> ControlModel:
        """Hand back a ControlModel for downstream tools (validation, plots)."""
        # FIR is stored (ny, n_coeff, nu) but ControlModel wants list of (ny, nu)
        fir_list = [self.fir[:, k, :] for k in range(self.n_coeff)]
        m = from_fir(fir_list, dt=self.dt, name=name or self.name)
        if self.A is not None:
            m._set_ss((self.A, self.B, self.C, self.D))
        return m

    def summary(self) -> str:
        return (
            f"ModelBundle '{self.name}'\n"
            f"  dt           : {self.dt}s\n"
            f"  dimensions   : ny={self.ny}  nu={self.nu}  nx={self.nx}\n"
            f"  n_coeff      : {self.n_coeff}\n"
            f"  ident method : {self.ident_method}\n"
            f"  era order    : {self.era_order}\n"
            f"  mv tags      : {self.mv_tags}\n"
            f"  cv tags      : {self.cv_tags}\n"
            f"  source       : {self.source_csv}"
        )


# ---------------------------------------------------------------------------
# Build a bundle from an IdentResult
# ---------------------------------------------------------------------------
def bundle_from_ident(
    result: IdentResult,
    *,
    name: str,
    mv_tags: List[str],
    cv_tags: List[str],
    dv_tags: Optional[List[str]] = None,
    u0: Optional[np.ndarray] = None,
    y0: Optional[np.ndarray] = None,
    era_order: Optional[int] = None,
    source_csv: str = "",
    source_project: str = "",
) -> ModelBundle:
    """Convert an ``IdentResult`` into a self-contained ``ModelBundle``.

    Performs ERA reduction (default order = min(10, (n_coeff-1)//2)) so the
    bundle ships with both FIR and a low-order state-space realisation.
    """
    if len(mv_tags) != result.nu:
        raise ValueError(
            f"mv_tags length {len(mv_tags)} != ident result nu={result.nu}")
    if len(cv_tags) != result.ny:
        raise ValueError(
            f"cv_tags length {len(cv_tags)} != ident result ny={result.ny}")

    n_coeff = result.n_coeff
    ny, nu = result.ny, result.nu

    # Stack FIR list -> (ny, n_coeff, nu)
    fir_arr = np.zeros((ny, n_coeff, nu))
    for k in range(n_coeff):
        fir_arr[:, k, :] = result.fir[k]

    ci_lo = np.zeros((ny, n_coeff, nu))
    ci_hi = np.zeros((ny, n_coeff, nu))
    for k in range(n_coeff):
        ci_lo[:, k, :] = result.confidence_lo[k]
        ci_hi[:, k, :] = result.confidence_hi[k]

    step_arr = np.cumsum(fir_arr, axis=1)
    gain = step_arr[:, -1, :].copy()
    settling = result.settling_index(tol=0.02).astype(np.int32)

    # ERA reduction to get a compact SS realisation. We start at the
    # requested order (defaulting to min(10, max_valid)) and walk DOWN
    # until the resulting A is stable (all eigenvalues strictly inside
    # the unit circle). This avoids shipping a marginally-unstable A
    # that diverges over long open-loop simulations -- see the C4
    # smoke regression where order=10 gave |lambda|=1.0095 and broke
    # validation on a 300-sample hold-out window.
    cm = from_fir([result.fir[k] for k in range(n_coeff)], dt=result.config.dt)
    max_order = (n_coeff - 1) // 2
    if era_order is None:
        era_order = min(10, max_order)
    era_order = max(1, min(era_order, max_order))

    ss_model = None
    actual_order = era_order
    for try_order in range(era_order, 0, -1):
        try:
            cand = cm.to_ss_from_fir(method="era", order=try_order)
            if cand.is_stable():
                ss_model = cand
                actual_order = try_order
                break
        except Exception:
            continue
    if ss_model is None:
        # Last resort: take whatever the requested order gives us, even
        # if marginally unstable. The bundle still ships the FIR so the
        # consumer can fall back to FIR-mode simulation.
        ss_model = cm.to_ss_from_fir(method="era", order=era_order)
        actual_order = era_order
    era_order = actual_order
    A, B, C, D = ss_model.ss

    # Default operating point: zeros (deviation-variable form)
    if u0 is None:
        u0 = np.zeros(nu)
    if y0 is None:
        y0 = np.zeros(ny)

    # Compact fit_summary dict (per-channel)
    fit_summary: Dict[str, Any] = {
        "condition_number": float(result.condition_number),
        "channels": [
            {
                "cv": cv_tags[f.cv_index],
                "mv": mv_tags[f.mv_index],
                "r_squared": float(f.r_squared),
                "rmse": float(f.rmse),
                "nrmse": float(f.nrmse),
                "ljung_box_pvalue": float(f.ljung_box_pvalue),
                "is_white": bool(f.is_white),
            }
            for f in result.fits
        ],
    }

    return ModelBundle(
        name=name,
        dt=float(result.config.dt),
        mv_tags=list(mv_tags),
        cv_tags=list(cv_tags),
        dv_tags=list(dv_tags or []),
        fir=fir_arr,
        confidence_lo=ci_lo,
        confidence_hi=ci_hi,
        step=step_arr,
        gain_matrix=gain,
        settling_index=settling,
        A=A, B=B, C=C, D=D,
        u0=np.asarray(u0, dtype=np.float64),
        y0=np.asarray(y0, dtype=np.float64),
        era_order=int(era_order),
        created=datetime.datetime.now().isoformat(timespec="seconds"),
        ident_method=result.config.method.value,
        ident_n_coeff=int(n_coeff),
        ident_alpha=float(result.config.ridge_alpha),
        ident_smoothing=result.config.smooth.value,
        source_csv=source_csv,
        source_project=source_project,
        fit_summary=fit_summary,
    )


# ---------------------------------------------------------------------------
# Save / load
# ---------------------------------------------------------------------------
def save_model_bundle(bundle: ModelBundle, path: str) -> None:
    """Write a ModelBundle to a .apcmodel HDF5 file (overwrites if exists)."""
    import h5py

    abs_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(abs_path) or ".", exist_ok=True)

    with h5py.File(abs_path, "w") as f:
        meta = f.create_group("metadata")
        meta.attrs["schema_version"] = bundle.schema_version
        meta.attrs["name"] = bundle.name
        meta.attrs["created"] = bundle.created
        meta.attrs["dt_seconds"] = float(bundle.dt)
        meta.attrs["ident_method"] = bundle.ident_method
        meta.attrs["ident_n_coeff"] = int(bundle.ident_n_coeff)
        meta.attrs["ident_alpha"] = float(bundle.ident_alpha)
        meta.attrs["ident_smoothing"] = bundle.ident_smoothing
        meta.attrs["source_csv"] = bundle.source_csv
        meta.attrs["source_project"] = bundle.source_project
        meta.attrs["fit_summary_json"] = json.dumps(bundle.fit_summary)

        tags = f.create_group("tags")
        tags.create_dataset("mvs", data=_str_array(bundle.mv_tags))
        tags.create_dataset("cvs", data=_str_array(bundle.cv_tags))
        tags.create_dataset("dvs", data=_str_array(bundle.dv_tags))

        if bundle.fir is not None:
            fir_g = f.create_group("fir")
            fir_g.create_dataset("coefficients", data=bundle.fir)
            if bundle.confidence_lo is not None:
                fir_g.create_dataset("confidence_lo", data=bundle.confidence_lo)
            if bundle.confidence_hi is not None:
                fir_g.create_dataset("confidence_hi", data=bundle.confidence_hi)

        if bundle.step is not None:
            sr_g = f.create_group("step_response")
            sr_g.create_dataset("coefficients", data=bundle.step)
            if bundle.gain_matrix is not None:
                sr_g.create_dataset("gain_matrix", data=bundle.gain_matrix)
            if bundle.settling_index is not None:
                sr_g.create_dataset("settling_index",
                                     data=bundle.settling_index.astype(np.int32))

        if bundle.A is not None:
            ss_g = f.create_group("state_space")
            ss_g.create_dataset("A", data=bundle.A)
            ss_g.create_dataset("B", data=bundle.B)
            ss_g.create_dataset("C", data=bundle.C)
            ss_g.create_dataset("D", data=bundle.D)
            ss_g.create_dataset("u0", data=bundle.u0)
            ss_g.create_dataset("y0", data=bundle.y0)
            ss_g.attrs["era_order"] = int(bundle.era_order)


def load_model_bundle(path: str) -> ModelBundle:
    """Read a .apcmodel HDF5 file into a ModelBundle."""
    import h5py

    if not os.path.exists(path):
        raise FileNotFoundError(f"Model bundle not found: {path}")

    with h5py.File(path, "r") as f:
        meta = f["metadata"].attrs
        schema = int(meta.get("schema_version", 1))
        if schema > SCHEMA_VERSION:
            raise ValueError(
                f"Bundle schema version {schema} is newer than supported "
                f"({SCHEMA_VERSION}). Upgrade apc_ident.")

        bundle = ModelBundle(
            name=str(meta.get("name", "")),
            dt=float(meta.get("dt_seconds", 1.0)),
            mv_tags=_load_str_array(f["tags/mvs"]),
            cv_tags=_load_str_array(f["tags/cvs"]),
            dv_tags=_load_str_array(f["tags/dvs"]) if "tags/dvs" in f else [],
            schema_version=schema,
            created=str(meta.get("created", "")),
            ident_method=str(meta.get("ident_method", "")),
            ident_n_coeff=int(meta.get("ident_n_coeff", 0)),
            ident_alpha=float(meta.get("ident_alpha", 0.0)),
            ident_smoothing=str(meta.get("ident_smoothing", "")),
            source_csv=str(meta.get("source_csv", "")),
            source_project=str(meta.get("source_project", "")),
            fit_summary=json.loads(str(meta.get("fit_summary_json", "{}"))),
        )

        if "fir" in f:
            bundle.fir = np.asarray(f["fir/coefficients"])
            if "fir/confidence_lo" in f:
                bundle.confidence_lo = np.asarray(f["fir/confidence_lo"])
            if "fir/confidence_hi" in f:
                bundle.confidence_hi = np.asarray(f["fir/confidence_hi"])

        if "step_response" in f:
            sr = f["step_response"]
            bundle.step = np.asarray(sr["coefficients"])
            if "gain_matrix" in sr:
                bundle.gain_matrix = np.asarray(sr["gain_matrix"])
            if "settling_index" in sr:
                bundle.settling_index = np.asarray(sr["settling_index"]).astype(np.int32)

        if "state_space" in f:
            ss = f["state_space"]
            bundle.A = np.asarray(ss["A"])
            bundle.B = np.asarray(ss["B"])
            bundle.C = np.asarray(ss["C"])
            bundle.D = np.asarray(ss["D"])
            bundle.u0 = np.asarray(ss["u0"])
            bundle.y0 = np.asarray(ss["y0"])
            bundle.era_order = int(ss.attrs.get("era_order", 0))

    return bundle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _str_array(strings: List[str]) -> np.ndarray:
    """HDF5-friendly variable-length UTF-8 string array."""
    import h5py
    dt = h5py.string_dtype(encoding="utf-8")
    return np.array(list(strings), dtype=dt)


def _load_str_array(dataset) -> List[str]:
    out: List[str] = []
    for v in dataset[:]:
        if isinstance(v, bytes):
            out.append(v.decode("utf-8"))
        else:
            out.append(str(v))
    return out
