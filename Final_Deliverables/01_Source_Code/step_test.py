"""Step Test Runner — Automated open-loop plant excitation for system identification.

Executes controlled step changes in choke position and records the transient
response of all four process outputs. Used as input to the ModelIdentifier
for FOPDT parameter estimation.
"""

import logging
from typing import List, Tuple, Optional

from config import ControllerConfig
from models import StepTestResult

logger = logging.getLogger(__name__)


class StepTestRunner:
    """
    Utility class for executing step tests on the plant to gather dynamic data.
    """
    
    def __init__(self, config: ControllerConfig):
        """
        Initialize with controller configuration.
        """
        self.config = config

    def run_single_test(self, simulator, u_start: float, delta_u: float, 
                        settle_steps: int = 5, record_steps: int = 10) -> StepTestResult:
        """
        Run a single step test on the simulator.
        
        Args:
            simulator: Simulator object with a .step() method.
            u_start: Initial choke position.
            delta_u: Step magnitude.
            settle_steps: Number of steps to reach steady state.
            record_steps: Number of steps to record the transient response.
            
        Returns:
            StepTestResult with captured data.
        """
        # 1. Settle to steady state
        q, whp, flp, bhp = 0.0, 0.0, 0.0, 0.0
        for _ in range(settle_steps):
            q, whp, flp, bhp = simulator.step(u_start)
            
        # 2. Record initial values
        q_init, whp_init, flp_init, bhp_init = q, whp, flp, bhp
        
        # 3. Apply step
        u_end = u_start + delta_u
        times = []
        q_resp, whp_resp, flp_resp, bhp_resp = [], [], [], []
        
        # 4. Record response
        for t in range(record_steps):
            times.append(t * self.config.ts)
            q, whp, flp, bhp = simulator.step(u_end)
            
            q_resp.append(q)
            whp_resp.append(whp)
            flp_resp.append(flp)
            bhp_resp.append(bhp)
            
        # 5. Build results
        return StepTestResult(
            u_start=u_start,
            u_end=u_end,
            delta_u=delta_u,
            duration=record_steps * self.config.ts,
            time=times,
            q_response=q_resp,
            whp_response=whp_resp,
            flp_response=flp_resp,
            bhp_response=bhp_resp,
            q_initial=q_init,
            whp_initial=whp_init,
            flp_initial=flp_init,
            bhp_initial=bhp_init,
            q_final=q_resp[-1],
            whp_final=whp_resp[-1],
            flp_final=flp_resp[-1],
            bhp_final=bhp_resp[-1]
        )

    def run_exploration_suite(self, simulator, steps: Optional[List[Tuple[float, float]]] = None) -> List[StepTestResult]:
        """
        Execute a sequence of step tests across the operating range.
        
        Args:
            simulator: Simulator object.
            steps: Optional list of (u_start, delta_u) pairs.
            
        Returns:
            List of StepTestResults.
        """
        if steps is None:
            # Default sequence across the range
            steps = [(10.0, 10.0), (20.0, 10.0), (30.0, 10.0), 
                     (50.0, 10.0), (70.0, 10.0), (80.0, 10.0)]
            
        results = []
        for u_start, delta_u in steps:
            logger.info(f"Running step test: start={u_start}, delta={delta_u}")
            res = self.run_single_test(simulator, u_start, delta_u)
            results.append(res)
            
        return results
