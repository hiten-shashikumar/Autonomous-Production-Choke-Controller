"""
Configuration module for the Autonomous Choke Controller.

Centralizes all tuning parameters, constraint limits, and operating
constants into typed dataclasses. This is the single source of truth
for every configurable value in the system.
"""

from dataclasses import dataclass, field


@dataclass
class ConstraintLimits:
    """Safe operating ranges for constrained pressure variables.

    All pressures must remain within [min, max] at all times.
    These values MUST be discovered from the simulator before
    the controller can operate.
    """
    whp_min: float = 0.0
    whp_max: float = float("inf")
    flp_min: float = 0.0
    flp_max: float = float("inf")
    bhp_min: float = 0.0
    bhp_max: float = float("inf")

    def get_range(self, variable: str) -> float:
        """Return the span (max - min) for a given variable name."""
        ranges = {
            "whp": self.whp_max - self.whp_min,
            "flp": self.flp_max - self.flp_min,
            "bhp": self.bhp_max - self.bhp_min,
        }
        return ranges[variable]

    def get_limits(self, variable: str) -> tuple[float, float]:
        """Return (min, max) for a given variable name."""
        limits = {
            "whp": (self.whp_min, self.whp_max),
            "flp": (self.flp_min, self.flp_max),
            "bhp": (self.bhp_min, self.bhp_max),
        }
        return limits[variable]


@dataclass
class ControllerConfig:
    """Master configuration for the Autonomous Choke Controller.

    All tuning parameters with engineering rationale documented.
    Default values follow the reviewed design specification.
    """

    # --- Process Parameters (Fixed by Problem Statement) ---
    ts: float = 1.0            # Control interval [hours]
    ramp_limit: float = 5.0    # Max choke movement per step [%]
    choke_min: float = 0.0     # Minimum choke opening [%]
    choke_max: float = 100.0   # Maximum choke opening [%]

    # --- Prediction Configuration ---
    prediction_horizon: int = 3       # Np: number of steps to predict ahead
    candidate_step: float = 1.0       # Resolution of candidate Δu values [%]
    fine_step: float = 0.5            # Fine resolution when near target [%]
    fine_threshold: float = 0.05      # Switch to fine resolution when |e|/Q_range < this

    # --- Cost Function Weights (Simplified 3-term design) ---
    weight_effort: float = 0.01       # λ_effort: penalizes |Δu|²
    weight_margin: float = 0.005      # λ_margin: rewards constraint distance

    # --- Safety Configuration ---
    safety_margin: float = 0.05       # Fraction of constraint range as buffer
    proximity_caution: float = 0.20   # Proximity threshold for CAUTION status
    proximity_warning: float = 0.10   # Proximity threshold for WARNING status
    proximity_emergency: float = 0.05 # Proximity threshold for EMERGENCY status
    warning_ramp_limit: float = 2.0   # Restricted ramp rate in WARNING status [%]

    # --- Bias Correction ---
    bias_alpha: float = 0.3           # Exponential smoothing factor for bias

    # --- Steady-State Detection ---
    steady_state_tol: float = 0.005   # Relative change threshold for steady-state
    steady_state_steps: int = 3       # Consecutive steps below tolerance

    # --- State History ---
    history_size: int = 20            # Rolling buffer size for measurements

    # --- Target Management ---
    target_tolerance: float = 0.02    # Fraction of Q_range for "target reached"
    deadband: float = 0.01            # Fraction of Q_range to suppress micro-moves

    # --- Gain Scheduling Regions ---
    region_boundaries: list[float] = field(
        default_factory=lambda: [35.0, 65.0]
    )  # Choke % boundaries between low/mid/high regions
