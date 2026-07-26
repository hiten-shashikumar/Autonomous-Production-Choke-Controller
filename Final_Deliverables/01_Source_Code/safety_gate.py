"""Safety Gate — Constraint enforcement with defense-in-depth protection.

Evaluates every candidate control move against tightened constraint boundaries
(safety margin applied), checks both transient trajectory and steady-state
violations, and provides emergency override when hard limits are breached.
"""

import logging
from config import ControllerConfig, ConstraintLimits
from models import Measurements, Prediction, CandidateResult

logger = logging.getLogger(__name__)

class SafetyGate:
    """Evaluates prediction safety against tightened constraints."""
    def __init__(self, config: ControllerConfig, limits: ConstraintLimits):
        self.config = config
        self.limits = limits
        
    def evaluate(self, predictions: list[Prediction], measurements: Measurements) -> list[CandidateResult]:
        """Evaluates predictions and returns candidate results with feasibility status."""
        results = []
        vars_to_check = ['whp', 'flp', 'bhp']
        
        for pred in predictions:
            is_feasible = True
            violation_type = None
            violation_step = None
            min_margin = float('inf')
            margins = {}
            
            Np = len(pred.q_traj)
            
            for var in vars_to_check:
                limit_min, limit_max = self.limits.get_limits(var)
                rng = self.limits.get_range(var)
                if rng == 0:
                    rng = 1.0

                t_min = limit_min + self.config.safety_margin * rng
                t_max = limit_max - self.config.safety_margin * rng

                traj = getattr(pred, f"{var}_traj")
                ss_val = getattr(pred, f"{var}_ss")

                var_min_margin: float = float("inf")

                # Check trajectory
                for j, val in enumerate(traj):
                    m_min = (val - t_min) / rng
                    m_max = (t_max - val) / rng
                    step_margin = min(m_min, m_max)

                    var_min_margin = min(var_min_margin, step_margin)

                    if val < t_min:
                        is_feasible = False
                        if violation_type is None:
                            violation_type = f"{var}_low"
                            violation_step = j
                    elif val > t_max:
                        is_feasible = False
                        if violation_type is None:
                            violation_type = f"{var}_high"
                            violation_step = j

                # Check steady state
                m_min_ss = (ss_val - t_min) / rng
                m_max_ss = (t_max - ss_val) / rng
                ss_margin = min(m_min_ss, m_max_ss)

                var_min_margin = min(var_min_margin, ss_margin)

                if ss_val < t_min:
                    is_feasible = False
                    if violation_type is None:
                        violation_type = f"{var}_low_ss"
                        violation_step = Np
                elif ss_val > t_max:
                    is_feasible = False
                    if violation_type is None:
                        violation_type = f"{var}_high_ss"
                        violation_step = Np

                margins[var] = var_min_margin
                min_margin = min(min_margin, var_min_margin)
                
            results.append(CandidateResult(
                prediction=pred,
                is_feasible=is_feasible,
                violation_type=violation_type,
                violation_step=violation_step,
                min_margin=min_margin,
                margins=margins
            ))
            
        return results

    def check_emergency(self, measurements: Measurements) -> tuple[bool, float]:
        """Checks for emergency violation of hard constraints."""
        vars_to_check = ['whp', 'flp', 'bhp']
        for var in vars_to_check:
            val = getattr(measurements, var)
            limit_min, limit_max = self.limits.get_limits(var)
            
            if val < limit_min:
                return True, -self.config.ramp_limit
            elif val > limit_max:
                return True, self.config.ramp_limit
                
        return False, 0.0

__all__ = ['SafetyGate']
