"""Process variable definitions with DCS-style limit levels."""
from dataclasses import dataclass, field
from typing import Optional


# DMC3-style optimization preferences (for Layer 2 LP)
MV_OPT_TYPES = [
    "No Preference",
    "Minimize",          # negative LP cost: drive to lo limit
    "Maximize",          # positive LP cost: drive to hi limit
    "Min Movement",      # high move suppression, no LP cost
    "Hold at SS",        # try to keep at steady state value
]

CV_OPT_TYPES = [
    "Bounds Only",       # no economic objective, just stay within hi/lo
    "Minimize",          # drive to lo limit
    "Maximize",          # drive to hi limit
    "Setpoint Track",    # use SP from Setpoint column (QP tracking)
    "Ideal Value",       # track Ideal SS column
]


@dataclass
class Limits:
    """Three-level limit structure matching DCS convention."""
    validity_lo: float = -1e20
    validity_hi: float = 1e20
    engineering_lo: float = -1e20
    engineering_hi: float = 1e20
    operating_lo: float = -1e20
    operating_hi: float = 1e20
    safety_lo: float = -1e20
    safety_hi: float = 1e20


@dataclass
class MV:
    """Manipulated variable."""
    tag: str
    name: str
    units: str
    steady_state: float
    limits: Limits = field(default_factory=Limits)
    rate_limit: float = 1e20
    move_suppress: float = 1.0
    cost: float = 0.0
    cost_rank: int = 0           # DMC3 lexicographic LP rank (higher = solved first)
    opt_type: str = "No Preference"  # DMC3 optimization preference
    subcontroller: str = "MAIN"  # DMC3 subcontroller group name
    plot_lo: Optional[float] = None
    plot_hi: Optional[float] = None
    value: float = 0.0  # current runtime value

    def __post_init__(self):
        if self.value == 0.0:
            self.value = self.steady_state
        if self.plot_lo is None:
            self.plot_lo = self.limits.engineering_lo
        if self.plot_hi is None:
            self.plot_hi = self.limits.engineering_hi


@dataclass
class CV:
    """Controlled variable."""
    tag: str
    name: str
    units: str
    steady_state: float
    setpoint: float = 0.0
    limits: Limits = field(default_factory=Limits)
    weight: float = 1.0
    priority: int = 4
    noise: float = 0.0
    cv_cost: float = 0.0       # LP cost for CVs (drive to bound)
    opt_type: str = "Setpoint Track"  # DMC3 optimization preference
    # DMC3 ranking and concern fields
    concern_lo: float = 1.0     # penalty weight for lower bound violation
    concern_hi: float = 1.0     # penalty weight for upper bound violation
    rank_lo: int = 20           # constraint relaxation order (lower = relaxed first)
    rank_hi: int = 20
    # DMC3 disturbance filter (Configuration > Feedback Filters)
    filter_type: str = "Full Feedback"  # Full Feedback / First Order / Moving Average
    pred_error_lag: float = 0.0         # filter time constant for First Order / MA
    pred_error_horizon: int = 0         # window size for Moving Average
    rotation_factor: float = 0.0        # for ramp variables only
    intermittent: bool = False
    intermittent_timeout: int = 0
    is_ramp: bool = False
    # DMC3 subcontroller group
    subcontroller: str = "MAIN"
    plot_lo: Optional[float] = None
    plot_hi: Optional[float] = None
    value: float = 0.0

    def __post_init__(self):
        if self.setpoint == 0.0:
            self.setpoint = self.steady_state
        if self.value == 0.0:
            self.value = self.steady_state
        if self.plot_lo is None:
            self.plot_lo = self.limits.engineering_lo
        if self.plot_hi is None:
            self.plot_hi = self.limits.engineering_hi


def mv_lp_cost(mv: 'MV') -> float:
    """Translate an MV's opt_type to an effective LP cost."""
    t = mv.opt_type
    if t == "Minimize":
        return abs(mv.cost) if mv.cost else 1.0
    if t == "Maximize":
        return -abs(mv.cost) if mv.cost else -1.0
    return 0.0   # No Preference, Min Movement, Hold at SS


def mv_effective_move_suppress(mv: 'MV') -> float:
    """Min Movement / Hold at SS use higher move suppression."""
    if mv.opt_type in ("Min Movement", "Hold at SS"):
        return max(mv.move_suppress, 100.0)
    return mv.move_suppress


def cv_lp_cost(cv: 'CV') -> float:
    """Translate a CV's opt_type to an effective LP cost."""
    t = cv.opt_type
    if t == "Minimize":
        return abs(cv.cv_cost) if cv.cv_cost else 1.0
    if t == "Maximize":
        return -abs(cv.cv_cost) if cv.cv_cost else -1.0
    return 0.0   # Bounds Only, Setpoint Track, Ideal Value


def cv_effective_weight(cv: 'CV') -> float:
    """All opt types use the configured weight EXCEPT Bounds Only (weight=0).
    For Minimize/Maximize, the weight drives the CV toward the bound used as setpoint."""
    if cv.opt_type == "Bounds Only":
        return 0.0
    # Minimize/Maximize/Setpoint Track/Ideal Value: use configured weight
    # Default to 1.0 if user has weight=0 but wants directional optimization
    if cv.opt_type in ("Minimize", "Maximize") and cv.weight <= 0:
        return 1.0
    return cv.weight


def cv_effective_setpoint(cv: 'CV') -> float:
    """For Maximize/Minimize, use the bound as the QP target."""
    t = cv.opt_type
    if t == "Maximize":
        return cv.limits.operating_hi if cv.limits.operating_hi < 1e19 else cv.setpoint
    if t == "Minimize":
        return cv.limits.operating_lo if cv.limits.operating_lo > -1e19 else cv.setpoint
    return cv.setpoint


@dataclass
class DV:
    """Disturbance variable."""
    tag: str
    name: str
    units: str
    steady_state: float
    limits: Limits = field(default_factory=Limits)
    subcontroller: str = "MAIN"
    plot_lo: Optional[float] = None
    plot_hi: Optional[float] = None
    value: float = 0.0

    def __post_init__(self):
        if self.value == 0.0:
            self.value = self.steady_state
        if self.plot_lo is None:
            self.plot_lo = self.limits.engineering_lo
        if self.plot_hi is None:
            self.plot_hi = self.limits.engineering_hi
