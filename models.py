"""
Core data models for the Autonomous Choke Controller.

Defines all data structures exchanged between controller modules.
Uses dataclasses for immutability where appropriate and enums for
categorical states. These models form the interface contract between
all modules in the system.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ──────────────────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────────────────

class OperatingMode(Enum):
    """Controller operating mode — drives objective function behavior."""
    STARTUP = "startup"
    TRACKING = "tracking"
    INFEASIBLE = "infeasible"


class SafetyStatus(Enum):
    """Safety proximity alert level — drives candidate restriction."""
    NORMAL = "normal"
    CAUTION = "caution"
    WARNING = "warning"
    EMERGENCY = "emergency"


# ──────────────────────────────────────────────────────────────
# Model Parameters
# ──────────────────────────────────────────────────────────────

@dataclass
class FOPDTParams:
    """Discrete First-Order Plus Dead Time model parameters.

    Continuous form: G(s) = K·exp(-θs) / (τs + 1)
    Discrete form:   y(k) = a·y(k-1) + b·u(k-d) + c

    Attributes:
        gain: Steady-state gain K = Δy_ss / Δu.
        time_constant: Time constant τ [hours].
        dead_time: Dead time in samples d = ceil(θ / Ts).
        a: Discrete dynamics parameter = exp(-Ts/τ).
        b: Discrete input parameter = K·(1 - a).
        bias: Operating-point offset constant.
    """
    gain: float = 0.0
    time_constant: float = 1.0
    dead_time: int = 0
    a: float = 0.0
    b: float = 0.0
    bias: float = 0.0

    @classmethod
    def from_continuous(
        cls,
        gain: float,
        time_constant: float,
        dead_time_hours: float,
        ts: float = 1.0,
        bias: float = 0.0,
    ) -> FOPDTParams:
        """Create discrete parameters from continuous FOPDT parameters.

        Args:
            gain: Steady-state process gain K.
            time_constant: Process time constant τ [hours].
            dead_time_hours: Dead time θ [hours].
            ts: Sampling interval [hours].
            bias: Steady-state offset.

        Returns:
            FOPDTParams with computed discrete coefficients.
        """
        if time_constant <= 1e-10:
            # Static or very fast process — treat as instantaneous
            a = 0.0
            b = gain
        else:
            a = math.exp(-ts / time_constant)
            b = gain * (1.0 - a)
        d = max(0, math.ceil(dead_time_hours / ts)) if dead_time_hours > 0 else 0
        return cls(
            gain=gain,
            time_constant=time_constant,
            dead_time=d,
            a=min(a, 0.999),  # Clamp for numerical stability
            b=b,
            bias=bias,
        )

    @classmethod
    def from_discrete(cls, a: float, b: float, d: int, ts: float = 1.0) -> FOPDTParams:
        """Create from directly identified discrete parameters.

        Args:
            a: AR coefficient.
            b: Input coefficient.
            d: Dead-time in samples.
            ts: Sampling interval [hours].
        """
        a = min(max(a, -0.999), 0.999)  # Stability clamp
        gain = b / (1.0 - a) if abs(1.0 - a) > 1e-10 else b
        tau = -ts / math.log(abs(a)) if abs(a) > 1e-10 else 0.0
        return cls(gain=gain, time_constant=tau, dead_time=d, a=a, b=b)

    def predict_steady_state(self, u: float) -> float:
        """Predict steady-state output for a given input."""
        return self.gain * u + self.bias


@dataclass
class WellModel:
    """Collection of FOPDT models for all four well outputs.

    Each output has an independent FOPDT model identified from step tests.
    For gain-scheduled operation, multiple WellModel instances are used,
    one per operating region.
    """
    q: FOPDTParams = field(default_factory=FOPDTParams)
    whp: FOPDTParams = field(default_factory=FOPDTParams)
    flp: FOPDTParams = field(default_factory=FOPDTParams)
    bhp: FOPDTParams = field(default_factory=FOPDTParams)

    def get_model(self, variable: str) -> FOPDTParams:
        """Retrieve model for a named variable."""
        return getattr(self, variable)


# ──────────────────────────────────────────────────────────────
# Process State
# ──────────────────────────────────────────────────────────────

@dataclass
class Measurements:
    """Raw simulator outputs at a single time step."""
    q: float
    whp: float
    flp: float
    bhp: float


@dataclass
class ProcessState:
    """Complete controller state at a single time step.

    Maintained and updated by the ProcessMonitor module.
    Consumed by Predictor, SafetyGate, and Selector.
    """
    step: int = 0
    q: float = 0.0
    whp: float = 0.0
    flp: float = 0.0
    bhp: float = 0.0
    u: float = 0.0

    # Rolling history buffers
    q_history: list[float] = field(default_factory=list)
    whp_history: list[float] = field(default_factory=list)
    flp_history: list[float] = field(default_factory=list)
    bhp_history: list[float] = field(default_factory=list)
    u_history: list[float] = field(default_factory=list)

    # Prediction bias corrections (exponentially weighted)
    bias: dict[str, float] = field(
        default_factory=lambda: {"q": 0.0, "whp": 0.0, "flp": 0.0, "bhp": 0.0}
    )

    # Derived state flags
    is_steady: bool = False
    safety_status: SafetyStatus = SafetyStatus.NORMAL

    def get_output(self, variable: str) -> float:
        """Get current value of a named output variable."""
        return getattr(self, variable)

    def get_history(self, variable: str) -> list[float]:
        """Get history buffer for a named variable."""
        return getattr(self, f"{variable}_history")


# ──────────────────────────────────────────────────────────────
# Predictions
# ──────────────────────────────────────────────────────────────

@dataclass
class Prediction:
    """Predicted output trajectories for a single candidate move.

    Contains the predicted values at each step of the prediction
    horizon, plus steady-state predictions.
    """
    delta_u: float                   # Proposed choke movement [%]
    u_new: float                     # Resulting choke position [%]

    # Trajectories over prediction horizon (length = Np)
    q_traj: list[float] = field(default_factory=list)
    whp_traj: list[float] = field(default_factory=list)
    flp_traj: list[float] = field(default_factory=list)
    bhp_traj: list[float] = field(default_factory=list)

    # Steady-state predictions
    q_ss: float = 0.0
    whp_ss: float = 0.0
    flp_ss: float = 0.0
    bhp_ss: float = 0.0


# ──────────────────────────────────────────────────────────────
# Constraint Evaluation
# ──────────────────────────────────────────────────────────────

@dataclass
class CandidateResult:
    """A candidate move annotated with safety evaluation results.

    Produced by the SafetyGate. Consumed by the Selector.
    """
    prediction: Prediction
    is_feasible: bool = True
    violation_type: Optional[str] = None
    violation_step: Optional[int] = None
    min_margin: float = float("inf")   # Minimum normalized margin across all vars/steps
    margins: dict[str, float] = field(  # Per-variable minimum margins
        default_factory=lambda: {"whp": float("inf"), "flp": float("inf"), "bhp": float("inf")}
    )


# ──────────────────────────────────────────────────────────────
# Controller Output
# ──────────────────────────────────────────────────────────────

@dataclass
class ControlAction:
    """Final controller decision at a single time step.

    Includes the action, its rationale, and all metadata needed
    for logging and presentation.
    """
    step: int
    u_prev: float
    u_next: float
    delta_u: float
    cost: float
    reason: str
    mode: OperatingMode
    safety_status: SafetyStatus
    q_target: float

    # Current measurements (for logging)
    q: float = 0.0
    whp: float = 0.0
    flp: float = 0.0
    bhp: float = 0.0

    # Candidate evaluation summary
    n_candidates: int = 0
    n_feasible: int = 0


# ──────────────────────────────────────────────────────────────
# Step Test Data
# ──────────────────────────────────────────────────────────────

@dataclass
class StepTestResult:
    """Results from a single open-loop step test experiment."""
    u_start: float               # Initial choke position [%]
    u_end: float                 # Final choke position [%]
    delta_u: float               # Step size [%]
    duration: int                # Number of time steps recorded

    # Time-series data (length = duration)
    time: list[float] = field(default_factory=list)
    q_response: list[float] = field(default_factory=list)
    whp_response: list[float] = field(default_factory=list)
    flp_response: list[float] = field(default_factory=list)
    bhp_response: list[float] = field(default_factory=list)

    # Identified steady-state values
    q_initial: float = 0.0
    q_final: float = 0.0
    whp_initial: float = 0.0
    whp_final: float = 0.0
    flp_initial: float = 0.0
    flp_final: float = 0.0
    bhp_initial: float = 0.0
    bhp_final: float = 0.0
