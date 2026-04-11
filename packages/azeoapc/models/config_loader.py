"""Load and save simulation configuration from YAML.

A SimConfig can be persisted as either:
  - a controller config YAML (sections: controller, model, manipulated_variables, ...)
  - an .apcproj file -- the same YAML format with an extra ``project:`` header
    that carries metadata (schema_version, author, created/modified timestamps).

Both extensions resolve through the same loader. ``save_config`` round-trips
the SimConfig back to YAML, preserving the original ``model:`` section
(including matrix file references) and any unknown top-level keys.
"""
import os
import datetime
import importlib.util
import yaml
import numpy as np
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from .variables import MV, CV, DV, Limits
from .plant import StateSpacePlant, FOPTDPlant, NonlinearPlant

SCHEMA_VERSION = 1


@dataclass
class ProjectMetadata:
    """Metadata for an .apcproj file -- written under the YAML ``project:`` key."""
    schema_version: int = SCHEMA_VERSION
    author: str = ""
    created: str = ""    # ISO timestamp
    modified: str = ""
    apc_architect_version: str = "0.1.0"
    notes: str = ""


@dataclass
class Subcontroller:
    """A logical group of MVs/CVs (DMC3 subcontroller).

    For our single-controller simulator, all variables typically live in
    one subcontroller. Subcontrollers exist for visual organization and
    forward compatibility with multi-controller deployments.
    """
    name: str = "MAIN"
    description: str = ""
    is_critical: bool = False
    min_good_cvs: int = 0
    min_good_mvs: int = 0


@dataclass
class OptimizerConfig:
    prediction_horizon: int = 20
    control_horizon: int = 5
    model_horizon: int = 60
    observer_gain: float = 0.85


@dataclass
class Layer3Config:
    """Layer 3 NLP / RTO configuration."""
    enabled: bool = False
    execution_interval_sec: float = 3600.0
    max_iter: int = 500
    tolerance: float = 1e-6
    verbose: bool = False


@dataclass
class DisplayConfig:
    history_length: int = 200
    refresh_ms: int = 100
    plot_layout: str = "auto"


@dataclass
class SimConfig:
    """Complete simulation configuration."""
    name: str = "Untitled"
    description: str = ""
    sample_time: float = 1.0
    time_to_steady_state: float = 0.0  # auto-computed if 0
    mvs: List[MV] = field(default_factory=list)
    cvs: List[CV] = field(default_factory=list)
    dvs: List[DV] = field(default_factory=list)
    plant: object = None
    subcontrollers: List[Subcontroller] = field(default_factory=list)
    layer3: Layer3Config = field(default_factory=Layer3Config)
    calculations: list = field(default_factory=list)  # raw dicts for SimEngine
    optimizer: OptimizerConfig = field(default_factory=OptimizerConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)

    # Phase B: project metadata + round-trip support
    project: ProjectMetadata = field(default_factory=ProjectMetadata)
    deployment: Optional[object] = None      # azeoapc.deployment.DeploymentConfig
    source_path: Optional[str] = None        # absolute path the cfg was loaded from
    _raw_yaml: Optional[dict] = None         # original parsed dict for round-trip


def _parse_limits(d: dict) -> Limits:
    lim = Limits()
    if not d:
        return lim
    v = d.get("validity", {})
    e = d.get("engineering", {})
    o = d.get("operating", {})
    s = d.get("safety", {})
    # Support both [lo, hi] list and {lo:, hi:} dict forms
    def _pair(x, default_lo=-1e20, default_hi=1e20):
        if isinstance(x, list) and len(x) == 2:
            return x[0], x[1]
        if isinstance(x, dict):
            return x.get("lo", default_lo), x.get("hi", default_hi)
        return default_lo, default_hi

    lim.validity_lo, lim.validity_hi = _pair(v)
    lim.engineering_lo, lim.engineering_hi = _pair(e)
    lim.operating_lo, lim.operating_hi = _pair(o)
    lim.safety_lo, lim.safety_hi = _pair(s)
    return lim


_config_dir = "."

def _load_matrix(val):
    """Load matrix from inline list or .npy file path."""
    if val is None:
        return None
    if isinstance(val, str):
        # Resolve relative to config file directory
        fpath = os.path.join(_config_dir, val) if not os.path.isabs(val) else val
        return np.load(fpath)
    return np.array(val, dtype=np.float64)


def load_config(path: str) -> SimConfig:
    """Load a simulation config from a YAML or .apcproj file."""
    global _config_dir
    abs_path = os.path.abspath(path)
    _config_dir = os.path.dirname(abs_path)

    with open(path, "r") as f:
        raw = yaml.safe_load(f) or {}

    cfg = SimConfig()
    cfg.source_path = abs_path
    cfg._raw_yaml = raw

    # -- Project metadata (.apcproj header) --
    proj_raw = raw.get("project", {}) or {}
    cfg.project = ProjectMetadata(
        schema_version=int(proj_raw.get("schema_version", SCHEMA_VERSION)),
        author=proj_raw.get("author", ""),
        created=proj_raw.get("created", ""),
        modified=proj_raw.get("modified", ""),
        apc_architect_version=proj_raw.get("apc_architect_version", "0.1.0"),
        notes=proj_raw.get("notes", ""),
    )

    ctrl = raw.get("controller", {})
    cfg.name = ctrl.get("name", "Untitled")
    cfg.description = ctrl.get("description", "")
    cfg.sample_time = ctrl.get("sample_time", 1.0)
    cfg.time_to_steady_state = ctrl.get("time_to_steady_state", 0.0)

    # -- Optimizer --
    opt = raw.get("optimizer", {})
    cfg.optimizer = OptimizerConfig(
        prediction_horizon=opt.get("prediction_horizon", 20),
        control_horizon=opt.get("control_horizon", 5),
        model_horizon=opt.get("model_horizon", 60),
        observer_gain=opt.get("observer_gain", 0.85),
    )

    # -- Display --
    disp = raw.get("display", {})
    cfg.display = DisplayConfig(
        history_length=disp.get("history_length", 200),
        refresh_ms=disp.get("refresh_ms", 100),
        plot_layout=disp.get("plot_layout", "auto"),
    )

    # -- Subcontrollers --
    for sub_raw in raw.get("subcontrollers", []):
        cfg.subcontrollers.append(Subcontroller(
            name=sub_raw["name"],
            description=sub_raw.get("description", ""),
            is_critical=sub_raw.get("is_critical", False),
            min_good_cvs=sub_raw.get("min_good_cvs", 0),
            min_good_mvs=sub_raw.get("min_good_mvs", 0),
        ))
    # Default subcontroller if none specified
    if not cfg.subcontrollers:
        cfg.subcontrollers.append(Subcontroller(name="MAIN",
            description="Default subcontroller"))

    # -- MVs --
    for mv_raw in raw.get("manipulated_variables", []):
        cfg.mvs.append(MV(
            tag=mv_raw["tag"],
            name=mv_raw.get("name", mv_raw["tag"]),
            units=mv_raw.get("units", ""),
            steady_state=mv_raw.get("steady_state", 0.0),
            limits=_parse_limits(mv_raw.get("limits", {})),
            rate_limit=mv_raw.get("rate_limit", 1e20),
            move_suppress=mv_raw.get("move_suppress", 1.0),
            cost=mv_raw.get("cost", 0.0),
            cost_rank=mv_raw.get("cost_rank", 0),
            opt_type=mv_raw.get("opt_type", "No Preference"),
            subcontroller=mv_raw.get("subcontroller", cfg.subcontrollers[0].name),
            plot_lo=mv_raw.get("plot_lo"),
            plot_hi=mv_raw.get("plot_hi"),
        ))

    # -- CVs --
    for cv_raw in raw.get("controlled_variables", []):
        cfg.cvs.append(CV(
            tag=cv_raw["tag"],
            name=cv_raw.get("name", cv_raw["tag"]),
            units=cv_raw.get("units", ""),
            steady_state=cv_raw.get("steady_state", 0.0),
            setpoint=cv_raw.get("setpoint", cv_raw.get("steady_state", 0.0)),
            limits=_parse_limits(cv_raw.get("limits", {})),
            weight=cv_raw.get("weight", 1.0),
            priority=cv_raw.get("priority", 4),
            noise=cv_raw.get("noise", 0.0),
            cv_cost=cv_raw.get("cv_cost", 0.0),
            opt_type=cv_raw.get("opt_type", "Setpoint Track"),
            concern_lo=cv_raw.get("concern_lo", 1.0),
            concern_hi=cv_raw.get("concern_hi", 1.0),
            rank_lo=cv_raw.get("rank_lo", 20),
            rank_hi=cv_raw.get("rank_hi", 20),
            filter_type=cv_raw.get("filter_type", "Full Feedback"),
            pred_error_lag=cv_raw.get("pred_error_lag", 0.0),
            pred_error_horizon=cv_raw.get("pred_error_horizon", 0),
            rotation_factor=cv_raw.get("rotation_factor", 0.0),
            intermittent=cv_raw.get("intermittent", False),
            intermittent_timeout=cv_raw.get("intermittent_timeout", 0),
            is_ramp=cv_raw.get("is_ramp", False),
            subcontroller=cv_raw.get("subcontroller", cfg.subcontrollers[0].name),
            plot_lo=cv_raw.get("plot_lo"),
            plot_hi=cv_raw.get("plot_hi"),
        ))

    # -- DVs --
    for dv_raw in raw.get("disturbance_variables", []):
        cfg.dvs.append(DV(
            tag=dv_raw["tag"],
            name=dv_raw.get("name", dv_raw["tag"]),
            units=dv_raw.get("units", ""),
            steady_state=dv_raw.get("steady_state", 0.0),
            limits=_parse_limits(dv_raw.get("limits", {})),
            subcontroller=dv_raw.get("subcontroller", cfg.subcontrollers[0].name),
            plot_lo=dv_raw.get("plot_lo"),
            plot_hi=dv_raw.get("plot_hi"),
        ))

    # -- Plant Model --
    mdl = raw.get("model", {})
    mtype = mdl.get("type", "state_space")
    matrices = mdl.get("matrices", {})
    ss = mdl.get("steady_state", {})

    if mtype == "state_space":
        A = _load_matrix(matrices["A"])
        Bu = _load_matrix(matrices["Bu"])
        C = _load_matrix(matrices["C"])
        Bd_raw = matrices.get("Bd")
        Bd = _load_matrix(Bd_raw) if Bd_raw is not None else np.zeros((A.shape[0], max(len(cfg.dvs), 1)))
        D_raw = matrices.get("D")
        D = _load_matrix(D_raw) if D_raw is not None else np.zeros((C.shape[0], Bu.shape[1]))
        cfg.plant = StateSpacePlant(
            A=A, Bu=Bu, Bd=Bd, C=C, D=D,
            x0=np.array(ss.get("x0", np.zeros(A.shape[0]))),
            u0=np.array(ss.get("u0", [mv.steady_state for mv in cfg.mvs])),
            d0=np.array(ss.get("d0", [dv.steady_state for dv in cfg.dvs])) if cfg.dvs else np.zeros(0),
            y0=np.array(ss.get("y0", [cv.steady_state for cv in cfg.cvs])),
            sample_time=cfg.sample_time,
            continuous=mdl.get("continuous", False),
        )

    elif mtype == "foptd":
        cfg.plant = FOPTDPlant(
            gains=_load_matrix(matrices["gains"]),
            time_constants=_load_matrix(matrices["time_constants"]),
            dead_times=_load_matrix(matrices["dead_times"]),
            sample_time=cfg.sample_time,
        )

    elif mtype == "nonlinear":
        # Load Python module containing the ODE function
        # YAML must specify:
        #   model:
        #     type: nonlinear
        #     module: "path/to/cstr_model.py"  (relative to YAML)
        #     function: "cstr_ode"              (function name)
        #     nx, nu, nd, ny: dimensions
        #     output_indices: [0, 2]            (which states are CVs)
        #     steady_state: {x0, u0, d0, y0}
        module_path = mdl.get("module")
        if not module_path:
            raise ValueError("nonlinear plant requires 'module' field in YAML")
        if not os.path.isabs(module_path):
            module_path = os.path.join(_config_dir, module_path)
        if not os.path.exists(module_path):
            raise FileNotFoundError(f"Plant module not found: {module_path}")

        spec = importlib.util.spec_from_file_location("user_plant", module_path)
        user_plant = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(user_plant)

        fn_name = mdl.get("function", "ode")
        ode_fn = getattr(user_plant, fn_name)

        nx = int(mdl["nx"])
        nu = int(mdl.get("nu", len(cfg.mvs)))
        nd = int(mdl.get("nd", len(cfg.dvs)))
        ny = int(mdl.get("ny", len(cfg.cvs)))
        output_indices = mdl.get("output_indices", list(range(ny)))

        cfg.plant = NonlinearPlant(
            ode=ode_fn, nx=nx, nu=nu, nd=nd, ny=ny,
            x0=np.array(ss.get("x0", np.zeros(nx))),
            u0=np.array(ss.get("u0", [mv.steady_state for mv in cfg.mvs])),
            d0=np.array(ss.get("d0", [dv.steady_state for dv in cfg.dvs])) if cfg.dvs else np.zeros(0),
            y0=np.array(ss.get("y0", [cv.steady_state for cv in cfg.cvs])),
            sample_time=cfg.sample_time,
            output_indices=output_indices,
        )

    elif mtype == "bundle":
        # Identified model bundle (.apcmodel HDF5) produced by apc_ident.
        #
        # YAML format:
        #   model:
        #     type: bundle
        #     source: relative/path/to/my_furnace.apcmodel
        #     steady_state:                  # optional override
        #       u0: [100.0, 100.0, 100.0]
        #       y0: [750.0, 200.0, 0.0, 900.0, 900.0]
        #
        # The bundle's MV/CV tags are checked against cfg.mvs/cfg.cvs and
        # a warning is logged on mismatch (we trust the YAML, not the bundle).
        from ..identification.model_bundle import load_model_bundle

        bundle_path = mdl.get("source")
        if not bundle_path:
            raise ValueError("bundle plant requires 'source' field in YAML")
        if not os.path.isabs(bundle_path):
            bundle_path = os.path.join(_config_dir, bundle_path)
        if not os.path.exists(bundle_path):
            raise FileNotFoundError(f"Model bundle not found: {bundle_path}")

        bundle = load_model_bundle(bundle_path)
        if bundle.A is None:
            raise ValueError(
                f"Bundle '{bundle_path}' has no state-space realisation -- "
                "cannot build a SimEngine plant from it.")

        # Sanity-check tag alignment (warn, don't crash)
        cfg_mv_tags = [mv.tag for mv in cfg.mvs]
        cfg_cv_tags = [cv.tag for cv in cfg.cvs]
        if cfg_mv_tags and bundle.mv_tags != cfg_mv_tags:
            print(f"[load_config] WARNING: bundle MV tags {bundle.mv_tags} "
                  f"do not match controller MVs {cfg_mv_tags}")
        if cfg_cv_tags and bundle.cv_tags != cfg_cv_tags:
            print(f"[load_config] WARNING: bundle CV tags {bundle.cv_tags} "
                  f"do not match controller CVs {cfg_cv_tags}")

        nx = bundle.A.shape[0]
        nu_b = bundle.B.shape[1]
        ny_b = bundle.C.shape[0]

        # Bundles don't model disturbances -- Bd is all zeros with width nd.
        nd = max(len(cfg.dvs), 1)
        Bd = np.zeros((nx, nd))

        # Steady-state: prefer YAML override, fall back to bundle, else CV/MV defaults
        u0 = np.array(
            ss.get("u0", bundle.u0 if bundle.u0 is not None
                   else [mv.steady_state for mv in cfg.mvs]),
            dtype=np.float64)
        y0 = np.array(
            ss.get("y0", bundle.y0 if bundle.y0 is not None
                   else [cv.steady_state for cv in cfg.cvs]),
            dtype=np.float64)
        d0 = (np.array(ss.get("d0", [dv.steady_state for dv in cfg.dvs]),
                       dtype=np.float64)
              if cfg.dvs else np.zeros(0))
        x0 = np.array(ss.get("x0", np.zeros(nx)), dtype=np.float64)

        cfg.plant = StateSpacePlant(
            A=bundle.A, Bu=bundle.B, Bd=Bd, C=bundle.C, D=bundle.D,
            x0=x0, u0=u0, d0=d0, y0=y0,
            sample_time=cfg.sample_time,
            continuous=False,   # bundles are always discrete
        )

    # -- Layer 3 NLP / RTO --
    l3 = raw.get("layer3", {})
    if l3:
        cfg.layer3 = Layer3Config(
            enabled=l3.get("enabled", False),
            execution_interval_sec=l3.get("execution_interval_sec", 3600.0),
            max_iter=l3.get("max_iter", 500),
            tolerance=l3.get("tolerance", 1e-6),
            verbose=l3.get("verbose", False),
        )

    # -- User calculations (Python scripts) --
    calcs_raw = raw.get("calculations", []) or []
    for c in calcs_raw:
        cfg.calculations.append({
            "name": c.get("name", "calc"),
            "description": c.get("description", ""),
            "type": c.get("type", "input"),
            "code": c.get("code", ""),
            "sequence": c.get("sequence", 0),
            "enabled": c.get("enabled", True),
        })

    # -- Deployment (IO Tags + Online Settings) --
    dep_raw = raw.get("deployment")
    if dep_raw:
        try:
            from ..deployment.yaml_io import deployment_from_dict
            cfg.deployment = deployment_from_dict(dep_raw)
        except Exception as e:
            print(f"[load_config] failed to parse deployment section: {e}")
            cfg.deployment = None

    return cfg


# ============================================================================
# Save -- write a SimConfig back to YAML
# ============================================================================
def save_config(cfg: SimConfig, path: str, *, mark_as_project: bool = True) -> None:
    """Round-trip a SimConfig back to YAML on disk.

    Strategy: start from the original ``_raw_yaml`` dict if present (so
    unknown keys and the ``model:`` section with its file references are
    preserved), then overwrite every section the GUI can edit with fresh
    values from the in-memory config. The result is yaml.safe_dump'd.

    If ``mark_as_project`` is true (default), updates the ``project:`` header
    with the current timestamp and schema version.
    """
    raw: Dict[str, Any] = dict(cfg._raw_yaml) if cfg._raw_yaml else {}

    # ── Project metadata header ──
    if mark_as_project:
        now = datetime.datetime.now().isoformat(timespec="seconds")
        if not cfg.project.created:
            cfg.project.created = now
        cfg.project.modified = now
        cfg.project.schema_version = SCHEMA_VERSION
    raw["project"] = {
        "schema_version": cfg.project.schema_version,
        "author": cfg.project.author,
        "created": cfg.project.created,
        "modified": cfg.project.modified,
        "apc_architect_version": cfg.project.apc_architect_version,
        "notes": cfg.project.notes,
    }

    # ── Controller header ──
    raw["controller"] = {
        "name": cfg.name,
        "description": cfg.description,
        "sample_time": float(cfg.sample_time),
        "time_to_steady_state": float(cfg.time_to_steady_state),
    }

    # ── Subcontrollers ──
    raw["subcontrollers"] = [
        {
            "name": s.name,
            "description": s.description,
            "is_critical": bool(s.is_critical),
            "min_good_cvs": int(s.min_good_cvs),
            "min_good_mvs": int(s.min_good_mvs),
        }
        for s in cfg.subcontrollers
    ]

    # ── Optimizer ──
    raw["optimizer"] = {
        "prediction_horizon": int(cfg.optimizer.prediction_horizon),
        "control_horizon": int(cfg.optimizer.control_horizon),
        "model_horizon": int(cfg.optimizer.model_horizon),
        "observer_gain": float(cfg.optimizer.observer_gain),
    }

    # ── Display ──
    raw["display"] = {
        "history_length": int(cfg.display.history_length),
        "refresh_ms": int(cfg.display.refresh_ms),
        "plot_layout": cfg.display.plot_layout,
    }

    # ── Layer 3 ──
    raw["layer3"] = {
        "enabled": bool(cfg.layer3.enabled),
        "execution_interval_sec": float(cfg.layer3.execution_interval_sec),
        "max_iter": int(cfg.layer3.max_iter),
        "tolerance": float(cfg.layer3.tolerance),
        "verbose": bool(cfg.layer3.verbose),
    }

    # ── MVs / CVs / DVs ──
    raw["manipulated_variables"] = [_mv_to_dict(mv) for mv in cfg.mvs]
    raw["controlled_variables"] = [_cv_to_dict(cv) for cv in cfg.cvs]
    raw["disturbance_variables"] = [_dv_to_dict(dv) for dv in cfg.dvs]

    # ── Calculations -- already plain dicts ──
    raw["calculations"] = [
        {
            "name": c.get("name", "calc"),
            "description": c.get("description", ""),
            "type": c.get("type", "input"),
            "code": c.get("code", ""),
            "sequence": int(c.get("sequence", 0)),
            "enabled": bool(c.get("enabled", True)),
        }
        for c in cfg.calculations
    ]

    # ── Deployment ──
    if cfg.deployment is not None:
        try:
            from ..deployment.yaml_io import deployment_to_dict
            raw["deployment"] = deployment_to_dict(cfg.deployment)
        except Exception as e:
            print(f"[save_config] failed to serialize deployment section: {e}")
    else:
        raw.pop("deployment", None)

    # ── Plant model: preserve raw section -- we never edit matrices in GUI ──
    # If the original load had a model section, _raw_yaml still has it.
    # If it doesn't (e.g. a New project), leave it absent.
    #
    # Rewrite any matrix/module file references so they remain valid after a
    # Save As to a different directory. We resolve them against the ORIGINAL
    # source directory and then make them relative to the NEW save location.
    abs_path = os.path.abspath(path)
    new_dir = os.path.dirname(abs_path)
    old_dir = (os.path.dirname(cfg.source_path)
               if cfg.source_path else new_dir)
    if "model" in raw and isinstance(raw["model"], dict):
        _rewrite_model_paths(raw["model"], old_dir, new_dir)

    os.makedirs(new_dir or ".", exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(_HEADER_COMMENT)
        yaml.safe_dump(
            raw, f, sort_keys=False, default_flow_style=False, indent=2,
            allow_unicode=True, width=100,
        )

    cfg.source_path = abs_path
    cfg._raw_yaml = raw


def _rewrite_path(value: Any, old_dir: str, new_dir: str) -> Any:
    """If value is a relative file path string, rebase it from old_dir to new_dir."""
    if not isinstance(value, str):
        return value
    if os.path.isabs(value):
        return value
    abs_p = os.path.normpath(os.path.join(old_dir, value))
    if not os.path.exists(abs_p):
        return value  # leave it alone -- not a real file ref
    try:
        return os.path.relpath(abs_p, new_dir).replace("\\", "/")
    except ValueError:
        # Different drives on Windows -- fall back to absolute
        return abs_p.replace("\\", "/")


def _rewrite_model_paths(model: dict, old_dir: str, new_dir: str) -> None:
    """In-place rewrite of file references inside the model: section."""
    if old_dir == new_dir:
        return
    matrices = model.get("matrices")
    if isinstance(matrices, dict):
        for k, v in list(matrices.items()):
            matrices[k] = _rewrite_path(v, old_dir, new_dir)
    if "module" in model:
        model["module"] = _rewrite_path(model["module"], old_dir, new_dir)


_HEADER_COMMENT = (
    "# Azeotrope APC project file (.apcproj)\n"
    "# Generated by APC Architect -- safe to edit by hand.\n"
    "# Schema version: 1\n\n"
)


def _serialize_limits(lim: Limits) -> Dict[str, Any]:
    """Render a Limits struct as the {validity/engineering/operating/safety} dict."""
    out: Dict[str, Any] = {}

    def _pair(lo: float, hi: float):
        # Drop sentinel infinities so the YAML stays compact
        if lo <= -1e19 and hi >= 1e19:
            return None
        return [float(lo), float(hi)]

    v = _pair(lim.validity_lo, lim.validity_hi)
    e = _pair(lim.engineering_lo, lim.engineering_hi)
    o = _pair(lim.operating_lo, lim.operating_hi)
    s = _pair(lim.safety_lo, lim.safety_hi)
    if v is not None:
        out["validity"] = v
    if e is not None:
        out["engineering"] = e
    if o is not None:
        out["operating"] = o
    if s is not None:
        out["safety"] = s
    return out


def _mv_to_dict(mv: MV) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "tag": mv.tag,
        "name": mv.name,
        "units": mv.units,
        "steady_state": float(mv.steady_state),
        "limits": _serialize_limits(mv.limits),
        "rate_limit": float(mv.rate_limit) if mv.rate_limit < 1e19 else 1e20,
        "move_suppress": float(mv.move_suppress),
        "cost": float(mv.cost),
        "cost_rank": int(mv.cost_rank),
        "opt_type": mv.opt_type,
        "subcontroller": mv.subcontroller,
    }
    if mv.plot_lo is not None:
        d["plot_lo"] = float(mv.plot_lo)
    if mv.plot_hi is not None:
        d["plot_hi"] = float(mv.plot_hi)
    return d


def _cv_to_dict(cv: CV) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "tag": cv.tag,
        "name": cv.name,
        "units": cv.units,
        "steady_state": float(cv.steady_state),
        "setpoint": float(cv.setpoint),
        "limits": _serialize_limits(cv.limits),
        "weight": float(cv.weight),
        "priority": int(cv.priority),
        "noise": float(cv.noise),
        "cv_cost": float(cv.cv_cost),
        "opt_type": cv.opt_type,
        "concern_lo": float(cv.concern_lo),
        "concern_hi": float(cv.concern_hi),
        "rank_lo": int(cv.rank_lo),
        "rank_hi": int(cv.rank_hi),
        "filter_type": cv.filter_type,
        "pred_error_lag": float(cv.pred_error_lag),
        "pred_error_horizon": int(cv.pred_error_horizon),
        "rotation_factor": float(cv.rotation_factor),
        "intermittent": bool(cv.intermittent),
        "intermittent_timeout": int(cv.intermittent_timeout),
        "is_ramp": bool(cv.is_ramp),
        "subcontroller": cv.subcontroller,
    }
    if cv.plot_lo is not None:
        d["plot_lo"] = float(cv.plot_lo)
    if cv.plot_hi is not None:
        d["plot_hi"] = float(cv.plot_hi)
    return d


def _dv_to_dict(dv: DV) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "tag": dv.tag,
        "name": dv.name,
        "units": dv.units,
        "steady_state": float(dv.steady_state),
        "limits": _serialize_limits(dv.limits),
        "subcontroller": dv.subcontroller,
    }
    if dv.plot_lo is not None:
        d["plot_lo"] = float(dv.plot_lo)
    if dv.plot_hi is not None:
        d["plot_hi"] = float(dv.plot_hi)
    return d
