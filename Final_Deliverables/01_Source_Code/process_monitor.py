"""
Process Monitor — State estimation, history management, and anomaly detection.

Maintains rolling measurement history, computes prediction bias corrections
via exponential smoothing, detects steady state, and determines safety
proximity status based on how close current measurements are to constraint
boundaries.
"""

import logging
import math
from collections import deque

from config import ControllerConfig, ConstraintLimits
from models import Measurements, ProcessState, SafetyStatus

logger = logging.getLogger(__name__)

__all__ = ["ProcessMonitor"]


class ProcessMonitor:
    """Monitors process state and provides enriched state information.

    Key responsibilities:
      - Rolling history buffers for all measurements and choke positions
      - Exponential-smoothing bias correction (mandatory for offset-free tracking)
      - Steady-state detection via relative change thresholds
      - Safety proximity computation mapping to alert levels
    """

    VARIABLES = ("q", "whp", "flp", "bhp")
    CONSTRAINED = ("whp", "flp", "bhp")

    def __init__(self, config: ControllerConfig, limits: ConstraintLimits) -> None:
        self.config = config
        self.limits = limits
        self.reset()

    def reset(self) -> None:
        """Reset all internal state."""
        self._step = 0
        self._history: dict[str, deque] = {
            v: deque(maxlen=self.config.history_size) for v in (*self.VARIABLES, "u")
        }
        self._bias = {v: 0.0 for v in self.VARIABLES}
        self._prev_predictions: dict[str, float] | None = None
        self._steady_counter = 0

    def set_previous_predictions(self, predictions: dict[str, float]) -> None:
        """Store one-step-ahead predictions for bias computation at the next step."""
        self._prev_predictions = predictions

    def update(self, measurements: Measurements, u_applied: float) -> ProcessState:
        """Process new measurements and return an enriched ProcessState.

        Args:
            measurements: Raw simulator outputs.
            u_applied: Choke position that produced these measurements.

        Returns:
            Complete ProcessState for downstream modules.
        """
        # ── Bias correction ──────────────────────────────────
        if self._step > 0 and self._prev_predictions is not None:
            alpha = self.config.bias_alpha
            for var in self.VARIABLES:
                measured = getattr(measurements, var)
                predicted = self._prev_predictions.get(var, measured)
                if not (math.isfinite(measured) and math.isfinite(predicted)):
                    continue  # Skip NaN / Inf defensively
                error = measured - predicted
                self._bias[var] = alpha * error + (1.0 - alpha) * self._bias[var]

        # ── Append to history ────────────────────────────────
        for var in self.VARIABLES:
            self._history[var].append(getattr(measurements, var))
        self._history["u"].append(u_applied)

        # ── Steady-state detection ───────────────────────────
        is_steady = self._detect_steady_state(measurements)

        # ── Safety proximity ─────────────────────────────────
        safety_status = self._compute_safety_status(measurements)

        # ── Build state ──────────────────────────────────────
        state = ProcessState(
            step=self._step,
            q=measurements.q,
            whp=measurements.whp,
            flp=measurements.flp,
            bhp=measurements.bhp,
            u=u_applied,
            q_history=list(self._history["q"]),
            whp_history=list(self._history["whp"]),
            flp_history=list(self._history["flp"]),
            bhp_history=list(self._history["bhp"]),
            u_history=list(self._history["u"]),
            bias=self._bias.copy(),
            is_steady=is_steady,
            safety_status=safety_status,
        )

        self._step += 1
        return state

    # ─── Private helpers ─────────────────────────────────────

    def _detect_steady_state(self, measurements: Measurements) -> bool:
        """Check if all outputs have stabilised."""
        n = self.config.steady_state_steps
        if len(self._history["q"]) < n:
            self._steady_counter = 0
            return False

        all_stable = True
        for var in self.VARIABLES:
            recent = list(self._history[var])[-n:]
            current = getattr(measurements, var)
            vals = recent + [current]
            span = max(vals) - min(vals)
            ref = max(abs(current), 1e-6)
            if span / ref > self.config.steady_state_tol:
                all_stable = False
                break

        if all_stable:
            self._steady_counter += 1
        else:
            self._steady_counter = 0

        return self._steady_counter >= n

    def _compute_safety_status(self, measurements: Measurements) -> SafetyStatus:
        """Compute proximity-based safety alert level."""
        min_margin_frac = float("inf")
        for var in self.CONSTRAINED:
            val = getattr(measurements, var)
            v_min, v_max = self.limits.get_limits(var)
            rng = self.limits.get_range(var)
            if rng <= 0:
                continue
            margin = min(val - v_min, v_max - val) / rng
            min_margin_frac = min(min_margin_frac, margin)

        if min_margin_frac < self.config.proximity_emergency:
            return SafetyStatus.EMERGENCY
        if min_margin_frac < self.config.proximity_warning:
            return SafetyStatus.WARNING
        if min_margin_frac < self.config.proximity_caution:
            return SafetyStatus.CAUTION
        return SafetyStatus.NORMAL
