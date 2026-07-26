"""Model Identifier — FOPDT parameter estimation from step test data.

Uses the graphical 63.2% response method to identify First-Order Plus Dead Time
parameters (gain, time constant, dead time) from open-loop step test experiments.
Provides averaging across multiple tests, gain-scheduled region identification,
and model validation with RMSE and R² metrics.
"""

import logging
import math
from typing import List, Dict

from config import ControllerConfig
from models import FOPDTParams, StepTestResult, WellModel

logger = logging.getLogger(__name__)


class ModelIdentifier:
    """
    Identifies FOPDT system parameters from step test data.
    """
    
    def __init__(self, config: ControllerConfig):
        """
        Initialize the identifier.
        """
        self.config = config

    def identify_fopdt(self, result: StepTestResult, variable: str) -> FOPDTParams:
        """
        Identify Gain, Tau, and Dead Time using graphical methods.
        
        Args:
            result: Results of a step test.
            variable: The variable to identify ('q', 'whp', 'flp', 'bhp').
            
        Returns:
            FOPDTParams representing the linear dynamics.
        """
        y_init = getattr(result, f"{variable}_initial")
        y_final = getattr(result, f"{variable}_final")
        response = getattr(result, f"{variable}_response")
        times = result.time

        delta_y = y_final - y_init
        
        # 1. Compute gain
        if abs(result.delta_u) < 1e-6:
            K = 0.0
        else:
            K = delta_y / result.delta_u

        # 6. Compute bias
        bias = y_init - K * result.u_start

        if abs(delta_y) < 1e-6 or len(times) < 2:
            return FOPDTParams.from_continuous(gain=K, time_constant=1.0, dead_time_hours=0.0, ts=self.config.ts, bias=bias)

        # 2. Compute 63.2% level
        y_63 = y_init + 0.632 * delta_y
        
        # 3. Find time constant (tau)
        tau = 1.0
        for t, y in zip(times, response):
            if (delta_y > 0 and y >= y_63) or (delta_y < 0 and y <= y_63):
                tau = max(t, 0.1)
                break
                
        # 4. Find dead time
        dead_time = 0.0
        threshold = y_init + 0.05 * delta_y
        for t, y in zip(times, response):
            if (delta_y > 0 and y >= threshold) or (delta_y < 0 and y <= threshold):
                dead_time = t
                break
                
        # 5. Form parameters
        return FOPDTParams.from_continuous(gain=K, time_constant=tau, dead_time_hours=dead_time, ts=self.config.ts, bias=bias)

    def identify_well_model(self, results: List[StepTestResult]) -> WellModel:
        """
        Average parameters across multiple tests for a single global model.
        """
        if not results:
            raise ValueError("Empty step test results provided.")

        variables = ['q', 'whp', 'flp', 'bhp']
        models_data = {v: [] for v in variables}

        for res in results:
            for v in variables:
                models_data[v].append(self.identify_fopdt(res, v))

        averaged = {}
        for v in variables:
            n = len(models_data[v])
            gain = sum(p.gain for p in models_data[v]) / n
            tau = sum(p.time_constant for p in models_data[v]) / n
            # Average dead_time in continuous hours (dead_time field is discrete
            # samples; convert back via time_constant for accurate averaging)
            dt_hours = (
                sum(p.dead_time * self.config.ts for p in models_data[v]) / n
            )
            bias = sum(p.bias for p in models_data[v]) / n

            averaged[v] = FOPDTParams.from_continuous(
                gain, tau, dt_hours, ts=self.config.ts, bias=bias
            )

        return WellModel(
            q=averaged['q'],
            whp=averaged['whp'],
            flp=averaged['flp'],
            bhp=averaged['bhp']
        )

    def identify_gain_scheduled(self, results: List[StepTestResult]) -> Dict[int, WellModel]:
        """
        Create a gain-scheduled dictionary of models based on region boundaries.
        """
        regions_map: dict[int, list[StepTestResult]] = {}
        boundaries = self.config.region_boundaries
        
        # Bin results by region
        for res in results:
            idx = 0
            for i, bound in enumerate(boundaries):
                if res.u_start >= bound:
                    idx = i + 1
            if idx not in regions_map:
                regions_map[idx] = []
            regions_map[idx].append(res)
            
        return {idx: self.identify_well_model(tests) for idx, tests in regions_map.items()}

    def validate(self, model: FOPDTParams, result: StepTestResult, variable: str) -> dict:
        """
        Compare identified FOPDT predictions against actual transient response.
        """
        response = getattr(result, f"{variable}_response")
        if not response:
            return {"rmse": 0.0, "max_error": 0.0, "r_squared": 1.0, "residuals": []}

        # Simulate standard discrete FOPDT response
        predictions = []
        y_curr = getattr(result, f"{variable}_initial")
        
        for _ in response:
            y_curr = model.a * y_curr + model.b * result.u_end
            predictions.append(y_curr + model.bias)
            
        residuals = [y - p for y, p in zip(response, predictions)]
        
        rmse = math.sqrt(sum(r**2 for r in residuals) / len(residuals))
        max_error = max(abs(r) for r in residuals)
        
        y_mean = sum(response) / len(response)
        ss_tot = sum((y - y_mean)**2 for y in response)
        ss_res = sum(r**2 for r in residuals)
        r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 1e-6 else 1.0

        return {
            "rmse": rmse,
            "max_error": max_error,
            "r_squared": r_squared,
            "residuals": residuals
        }
