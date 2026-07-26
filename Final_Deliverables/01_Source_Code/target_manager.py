"""Target Manager — Operating mode determination and target arbitration.

Manages the controller's operating mode state machine (STARTUP → TRACKING →
INFEASIBLE) and computes the effective production target based on current mode,
steady-state condition, and constraint feasibility.
"""

import logging
from config import ControllerConfig
from models import OperatingMode

logger = logging.getLogger(__name__)

class TargetManager:
    """Manages the operating mode and target of the controller."""
    def __init__(self, config: ControllerConfig):
        self.config = config
        self.reset()
        
    def reset(self) -> None:
        """Resets the target manager state."""
        self._mode = OperatingMode.STARTUP
        self._prev_target = None
        self._steady_steps = 0
        
    @property
    def mode(self) -> OperatingMode:
        """Returns the current operating mode."""
        return self._mode
        
    def update(self, q_target: float, q_current: float, is_steady: bool, ss_infeasible: bool) -> tuple[float, OperatingMode, bool]:
        """Updates the state and returns the effective target, operating mode, and whether the target changed."""
        target_changed = False
        if self._prev_target is not None and abs(self._prev_target - q_target) > 1e-6:
            self._mode = OperatingMode.TRACKING
            target_changed = True
            self._steady_steps = 0
            
        self._prev_target = q_target
        
        if is_steady:
            self._steady_steps += 1
        else:
            self._steady_steps = 0
            
        if self._mode == OperatingMode.STARTUP:
            tolerance = self.config.target_tolerance * max(abs(q_target), 1.0)
            if abs(q_current - q_target) < tolerance and self._steady_steps > 3:
                self._mode = OperatingMode.TRACKING
        elif self._mode == OperatingMode.TRACKING:
            if ss_infeasible and self._steady_steps > 3:
                self._mode = OperatingMode.INFEASIBLE
                
        effective_target = q_target
        if self._mode == OperatingMode.INFEASIBLE:
            effective_target = q_current
            
        return effective_target, self._mode, target_changed

__all__ = ['TargetManager']
