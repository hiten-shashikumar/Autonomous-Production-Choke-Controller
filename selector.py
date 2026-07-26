"""Selector — Optimal control action selection via cost minimization.

Applies the 3-term cost function (tracking + effort + margin) to all feasible
candidates and selects the one with minimum cost. Handles deadband suppression,
infeasible-mode max-production logic, and least-infeasible fallback.
"""

import logging
from config import ControllerConfig
from models import CandidateResult, ControlAction, OperatingMode, SafetyStatus

logger = logging.getLogger(__name__)

class Selector:
    """Selects the best control action from the evaluated candidates."""
    def __init__(self, config: ControllerConfig):
        self.config = config
        
    def select(
        self,
        candidates: list[CandidateResult],
        q_target: float,
        q_range: float,
        mode: OperatingMode,
        delta_u_prev: float,
    ) -> ControlAction:
        """Evaluates costs and selects the optimal action.

        Args:
            candidates: Safety-evaluated candidate moves.
            q_target: Desired oil flow rate target.
            q_range: Observed Q range for normalization.
            mode: Current operating mode (affects cost function).
            delta_u_prev: Previous move magnitude (reserved for future
                move-suppression term in the cost function).
        """
        if not candidates:
            return ControlAction(
                step=0, u_prev=0.0, u_next=0.0, delta_u=0.0, cost=0.0,
                reason='No candidates', mode=mode, safety_status=SafetyStatus.NORMAL,
                q_target=q_target, q=0.0, whp=0.0, flp=0.0, bhp=0.0,
                n_candidates=0, n_feasible=0
            )
            
        feasible = [c for c in candidates if c.is_feasible]
        qr = max(q_range, 1.0)
        n_cand = len(candidates)
        n_feas = len(feasible)
        
        if not feasible:
            # Least infeasible
            best = max(candidates, key=lambda c: c.min_margin)
            reason = 'No feasible candidate — selecting least infeasible'
            return self._build_action(best, 0.0, reason, mode, q_target, n_cand, n_feas)
            
        best_cand = None
        best_cost = float('inf')
        best_reason = ''
        
        for cand in feasible:
            pred = cand.prediction
            q_end = pred.q_traj[-1] if pred.q_traj else pred.q_ss
            
            # J_track
            if mode == OperatingMode.INFEASIBLE:
                j_track = -(q_end / qr)
            else:
                j_track = ((q_end - q_target) / qr) ** 2
                if abs(q_end - q_target) < self.config.deadband * qr:
                    j_track = 0.0
                    
            # J_effort
            j_effort = (pred.delta_u / self.config.ramp_limit) ** 2
            
            # J_margin
            j_margin = -cand.min_margin
            
            cost = j_track + self.config.weight_effort * j_effort + self.config.weight_margin * j_margin
            
            if cost < best_cost:
                best_cost = cost
                best_cand = cand
                
                if j_track == 0.0 and mode != OperatingMode.INFEASIBLE:
                    best_reason = 'Target reached — holding'
                elif mode == OperatingMode.INFEASIBLE:
                    best_reason = f'Infeasible — maximizing safe production at Q={q_end:.2f}'
                else:
                    best_reason = f'Tracking target'
                    
        return self._build_action(best_cand, best_cost, best_reason, mode, q_target, n_cand, n_feas)

    def _build_action(
        self,
        cand: CandidateResult,
        cost: float,
        reason: str,
        mode: OperatingMode,
        q_target: float,
        n_cand: int,
        n_feas: int,
    ) -> ControlAction:
        """Constructs a ControlAction from the selected candidate.

        Uses the stored delta_u and u_new from the prediction directly rather
        than back-calculating, avoiding floating-point reconstruction errors.
        """
        pred = cand.prediction
        u_next = max(self.config.choke_min, min(self.config.choke_max, pred.u_new))
        u_prev = u_next - pred.delta_u
        delta_u = pred.delta_u
        
        return ControlAction(
            step=0, # Will be filled by the top-level controller
            u_prev=u_prev,
            u_next=u_next,
            delta_u=delta_u,
            cost=cost,
            reason=reason,
            mode=mode,
            safety_status=SafetyStatus.NORMAL, # Enriched by controller later
            q_target=q_target,
            q=pred.q_traj[-1] if pred.q_traj else pred.q_ss,
            whp=pred.whp_traj[-1] if pred.whp_traj else pred.whp_ss,
            flp=pred.flp_traj[-1] if pred.flp_traj else pred.flp_ss,
            bhp=pred.bhp_traj[-1] if pred.bhp_traj else pred.bhp_ss,
            n_candidates=n_cand,
            n_feasible=n_feas
        )

__all__ = ['Selector']
