"""Load simulation configuration from YAML."""
import os
import importlib.util
import yaml
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional
from .variables import MV, CV, DV, Limits
from .plant import StateSpacePlant, FOPTDPlant, NonlinearPlant


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
    mvs: List[MV] = field(default_factory=list)
    cvs: List[CV] = field(default_factory=list)
    dvs: List[DV] = field(default_factory=list)
    plant: object = None
    layer3: Layer3Config = field(default_factory=Layer3Config)
    optimizer: OptimizerConfig = field(default_factory=OptimizerConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)


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
    """Load a simulation config from a YAML file."""
    global _config_dir
    _config_dir = os.path.dirname(os.path.abspath(path))

    with open(path, "r") as f:
        raw = yaml.safe_load(f)

    ctrl = raw.get("controller", {})
    cfg = SimConfig()
    cfg.name = ctrl.get("name", "Untitled")
    cfg.description = ctrl.get("description", "")
    cfg.sample_time = ctrl.get("sample_time", 1.0)

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

    return cfg
