"""
Main orchestration module for the Autonomous Choke Controller.

Coordinates all 5 core modules (Process Monitor, Target Manager,
Predictor, Safety Gate, Selector) in the correct execution sequence
to produce control actions at each time step.
"""

import logging
from typing import Union

from config import ControllerConfig, ConstraintLimits
from models import (
    WellModel, Measurements, ControlAction,
    OperatingMode, SafetyStatus,
)
from process_monitor import ProcessMonitor
from target_manager import TargetManager
from predictor import Predictor
from safety_gate import SafetyGate
from selector import Selector

logger = logging.getLogger(__name__)

__all__ = ["AutonomousChokeController"]


class AutonomousChokeController:
    """Industrial-grade autonomous choke controller.

    Orchestrates the 5-phase control pipeline:
      1. Perception  — ProcessMonitor reads and processes measurements
      2. Targeting   — TargetManager determines mode and effective target
      3. Prediction  — Predictor generates candidates and forecasts outcomes
      4. Safety      — SafetyGate filters unsafe candidates
      5. Selection   — Selector picks the optimal safe action

    Usage::

        controller = AutonomousChokeController(config, limits, model)
        log = controller.run(simulator, q_targets, initial_choke=10.0)
    """

    def __init__(
        self,
        config: ControllerConfig,
        limits: ConstraintLimits,
        models: Union[dict[int, WellModel], WellModel],
    ) -> None:
        self.config = config
        self.limits = limits

        # Instantiate sub-modules
        self.process_monitor = ProcessMonitor(config, limits)
        self.target_manager = TargetManager(config)
        self.predictor = Predictor(config)
        self.safety_gate = SafetyGate(config, limits)
        self.selector = Selector(config)

        # Register models
        if isinstance(models, WellModel):
            self.predictor.set_single_model(models)
        else:
            self.predictor.set_models(models)

        # Runtime state
        self.u_current: float = 0.0
        self.q_range: float = 0.0
        self.delta_u_prev: float = 0.0
        self.step_count: int = 0
        self._ss_infeasible: bool = False
        self._action_log: list[ControlAction] = []
        self._q_observed_min: float = float("inf")
        self._q_observed_max: float = float("-inf")

    # ─── Public API ──────────────────────────────────────────────

    def step(self, measurements: Measurements, q_target: float) -> float:
        """Execute ONE control step and return the next choke position.

        Args:
            measurements: Current process readings (Q, WHP, FLP, BHP).
            q_target: Desired oil flow rate for this step.

        Returns:
            u_next — the choke position [%] to apply.
        """
        self.step_count += 1

        # ── PHASE 1: PERCEPTION ──────────────────────────────
        state = self.process_monitor.update(measurements, self.u_current)

        # Track observed Q range for normalisation
        self._q_observed_min = min(self._q_observed_min, measurements.q)
        self._q_observed_max = max(self._q_observed_max, measurements.q)
        self.q_range = max(1.0, self._q_observed_max - self._q_observed_min)

        # ── EMERGENCY CHECK ──────────────────────────────────
        is_emergency, emergency_du = self.safety_gate.check_emergency(measurements)
        if is_emergency:
            u_prev = self.u_current
            self.u_current = max(
                self.config.choke_min,
                min(self.config.choke_max, self.u_current + emergency_du),
            )
            self.delta_u_prev = self.u_current - u_prev
            action = ControlAction(
                step=self.step_count,
                u_prev=u_prev,
                u_next=self.u_current,
                delta_u=self.delta_u_prev,
                cost=0.0,
                reason="EMERGENCY OVERRIDE",
                mode=OperatingMode.TRACKING,
                safety_status=SafetyStatus.EMERGENCY,
                q_target=q_target,
                q=measurements.q,
                whp=measurements.whp,
                flp=measurements.flp,
                bhp=measurements.bhp,
                n_candidates=0,
                n_feasible=0,
            )
            self._action_log.append(action)
            logger.warning("Step %d: EMERGENCY override du=%.1f%%", self.step_count, self.delta_u_prev)
            return self.u_current

        # ── PHASE 2: TARGETING ───────────────────────────────
        q_eff, mode, target_changed = self.target_manager.update(
            q_target, measurements.q, state.is_steady, self._ss_infeasible
        )

        # ── PHASE 3: PREDICTION ──────────────────────────────
        tracking_error = measurements.q - q_target
        candidates = self.predictor.generate_candidates(
            self.u_current, state.safety_status, self.q_range, tracking_error
        )
        predictions = self.predictor.predict_all(self.u_current, candidates, state)

        # ── PHASE 4: SAFETY ──────────────────────────────────
        evaluated = self.safety_gate.evaluate(predictions, measurements)

        # ── PHASE 5: SELECTION ───────────────────────────────
        action = self.selector.select(
            evaluated, q_eff, self.q_range, mode, self.delta_u_prev
        )

        # ── POST-PROCESSING ──────────────────────────────────

        # Update SS infeasibility flag for next step
        feasible = [c for c in evaluated if c.is_feasible]
        if feasible:
            tol = self.config.target_tolerance * max(abs(q_target), 1.0)
            self._ss_infeasible = all(
                abs(c.prediction.q_ss - q_target) > tol for c in feasible
            )
        else:
            self._ss_infeasible = True

        # Store one-step-ahead predictions for bias correction
        best_pred = action  # u_next is already applied
        if predictions:
            # Find the prediction matching the selected delta_u
            for p in predictions:
                if abs(p.delta_u - action.delta_u) < 1e-9:
                    self.process_monitor.set_previous_predictions({
                        "q": p.q_traj[0] if p.q_traj else measurements.q,
                        "whp": p.whp_traj[0] if p.whp_traj else measurements.whp,
                        "flp": p.flp_traj[0] if p.flp_traj else measurements.flp,
                        "bhp": p.bhp_traj[0] if p.bhp_traj else measurements.bhp,
                    })
                    break

        # Update controller state
        self.u_current = action.u_next
        self.delta_u_prev = action.delta_u

        # Enrich the action log entry
        action.step = self.step_count
        action.q = measurements.q
        action.whp = measurements.whp
        action.flp = measurements.flp
        action.bhp = measurements.bhp
        action.q_target = q_target
        action.mode = mode
        action.safety_status = state.safety_status
        action.n_candidates = len(candidates)
        action.n_feasible = len(feasible)
        self._action_log.append(action)

        logger.info(
            "Step %d: u=%.1f%% -> %.1f%% | Q=%.1f (target=%.1f) | mode=%s | safe=%d/%d",
            self.step_count,
            action.u_prev,
            action.u_next,
            measurements.q,
            q_target,
            mode.value,
            len(feasible),
            len(candidates),
        )

        return self.u_current

    def run(
        self,
        simulator,
        q_targets: list[float],
        initial_choke: float = 10.0,
    ) -> list[ControlAction]:
        """Run the complete control simulation.

        Args:
            simulator: Object with a `step(choke_position) -> (Q, WHP, FLP, BHP)` method.
            q_targets: Production target at each time step.
            initial_choke: Starting choke position [%].

        Returns:
            Complete action log.
        """
        self.u_current = initial_choke

        # Initial measurement
        q, whp, flp, bhp = simulator.step(initial_choke)

        for k, q_target in enumerate(q_targets):
            meas = Measurements(q=q, whp=whp, flp=flp, bhp=bhp)
            self.step(meas, q_target)
            q, whp, flp, bhp = simulator.step(self.u_current)

        return list(self._action_log)

    @property
    def log(self) -> list[ControlAction]:
        """Access the action log."""
        return self._action_log

    def reset(self) -> None:
        """Reset all controller state for a new run."""
        self._action_log.clear()
        self.step_count = 0
        self.delta_u_prev = 0.0
        self.u_current = 0.0
        self.q_range = 0.0
        self._ss_infeasible = False
        self._q_observed_min = float("inf")
        self._q_observed_max = float("-inf")
        self.process_monitor.reset()
        self.target_manager.reset()
