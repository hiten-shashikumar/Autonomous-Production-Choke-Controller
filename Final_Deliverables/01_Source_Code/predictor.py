"""Predictor — FOPDT-based trajectory forecasting and candidate generation.

Generates a brute-force grid of candidate choke moves within the allowed ramp
rate and predicts the resulting trajectory for all four process outputs using
First-Order Plus Dead Time (FOPDT) models. Supports gain scheduling across
multiple operating regions for nonlinear processes.
"""

import logging
from config import ControllerConfig
from models import WellModel, ProcessState, SafetyStatus, Prediction

logger = logging.getLogger(__name__)

class Predictor:
    """Predicts future trajectories and steady states for candidate actions."""
    def __init__(self, config: ControllerConfig):
        self.config = config
        self.models = {}
        self.single_model = None
        
    def set_models(self, models: dict[int, WellModel]) -> None:
        """Sets gain-scheduled models keyed by region index."""
        self.models = models
        
    def set_single_model(self, model: WellModel) -> None:
        """Sets a single model for all regions."""
        self.single_model = model
        
    def _get_region(self, u: float) -> int:
        """Maps choke position to region index."""
        if self.single_model is not None:
            return -1
        boundaries = self.config.region_boundaries
        for i, bound in enumerate(boundaries):
            if u <= bound:
                return i
        return len(boundaries)
        
    def _get_model(self, region: int) -> WellModel:
        """Retrieves the correct model for a given region."""
        if self.single_model is not None:
            return self.single_model
        return self.models.get(region, list(self.models.values())[-1])
        
    def generate_candidates(
        self,
        u_current: float,
        safety_status: SafetyStatus,
        q_range: float = 1.0,
        tracking_error: float = 1.0,
    ) -> list[float]:
        """Generates a list of delta_u candidates.

        Uses fine_step resolution when tracking error is small relative to Q_range,
        providing higher-precision control near the target. Falls back to coarse
        candidate_step for large corrections.
        """
        ramp = (
            self.config.warning_ramp_limit
            if safety_status == SafetyStatus.WARNING
            else self.config.ramp_limit
        )

        # Select resolution: fine when near target, coarse otherwise
        if q_range > 0 and abs(tracking_error) / q_range < self.config.fine_threshold:
            step = self.config.fine_step
        else:
            step = self.config.candidate_step

        candidates: list[float] = []
        c = -ramp
        while c <= ramp + 1e-6:
            candidates.append(c)
            c += step

        # Always include zero (hold position)
        if 0.0 not in candidates:
            candidates.append(0.0)

        # Clip to physical choke limits
        valid: list[float] = []
        for du in candidates:
            u_new = u_current + du
            if self.config.choke_min <= u_new <= self.config.choke_max:
                valid.append(du)
        return sorted(list(set(valid)))
        
    def predict(self, u_current: float, delta_u: float, state: ProcessState) -> Prediction:
        """Predicts the process outcome for a single candidate delta_u."""
        u_new = u_current + delta_u
        region = self._get_region(u_new)
        model = self._get_model(region)
        
        Np = self.config.prediction_horizon
        
        trajectories = {'q': [], 'whp': [], 'flp': [], 'bhp': []}
        steady_states = {}
        
        for var in ['q', 'whp', 'flp', 'bhp']:
            m = model.get_model(var)
            dt = int(m.dead_time)
            u_seq = state.u_history + [u_new] * Np
            
            y_curr = getattr(state, var)
            traj = []
            y_prev = y_curr
            
            for j in range(Np):
                u_idx = len(state.u_history) + j - dt
                if u_idx < 0:
                    u_val = u_seq[0] if len(u_seq) > 0 else u_new
                else:
                    u_val = u_seq[u_idx]
                    
                # Discrete FOPDT: y(k+1) = a*y(k) + b*u(k-d) + (1-a)*offset
                # The (1-a)*offset term ensures convergence to y_ss = K*u + offset
                c = (1.0 - m.a) * m.bias
                y_next = m.a * y_prev + m.b * u_val + c
                traj.append(y_next + state.bias[var])
                y_prev = y_next
                
            trajectories[var] = traj
            steady_states[var] = m.predict_steady_state(u_new) + state.bias[var]
            
        return Prediction(
            delta_u=delta_u,
            u_new=u_new,
            q_traj=trajectories['q'],
            whp_traj=trajectories['whp'],
            flp_traj=trajectories['flp'],
            bhp_traj=trajectories['bhp'],
            q_ss=steady_states['q'],
            whp_ss=steady_states['whp'],
            flp_ss=steady_states['flp'],
            bhp_ss=steady_states['bhp']
        )
        
    def predict_all(self, u_current: float, candidates: list[float], state: ProcessState) -> list[Prediction]:
        """Predicts outcomes for multiple candidates."""
        return [self.predict(u_current, du, state) for du in candidates]

__all__ = ['Predictor']
