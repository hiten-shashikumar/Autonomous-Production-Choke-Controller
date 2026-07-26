"""
Simulator adapters for the Autonomous Choke Controller.

Provides SimulatorAdapter (wraps any external simulator) and
TestSimulator (built-in test process for development and validation).
The TestSimulator models a naturally flowing oil well with FOPDT dynamics
on all four outputs and physically motivated gain signs.
"""

import logging
import math
import random

logger = logging.getLogger(__name__)

__all__ = ["SimulatorAdapter", "TestSimulator"]


class SimulatorAdapter:
    """Adapter that wraps any simulator exposing a step() interface.

    Usage::

        # With the real hackathon simulator
        adapter = SimulatorAdapter(real_simulator)
        q, whp, flp, bhp = adapter.step(50.0)

        # With the built-in test simulator
        adapter = SimulatorAdapter()  # uses TestSimulator
    """

    def __init__(self, simulator_object=None) -> None:
        if simulator_object is None:
            self.simulator = TestSimulator()
            logger.info("Using built-in TestSimulator.")
        else:
            self.simulator = simulator_object

    def step(self, choke_position: float) -> tuple[float, float, float, float]:
        """Advance one control interval and return (Q, WHP, FLP, BHP)."""
        return self.simulator.step(choke_position)


class TestSimulator:
    """Built-in test simulator with FOPDT dynamics.

    Models a naturally flowing oil well where:
      - Opening the choke INCREASES flow rate Q
      - Opening the choke DECREASES wellhead pressure WHP
      - Opening the choke DECREASES flowline pressure FLP
      - Opening the choke DECREASES bottom-hole pressure BHP

    Each output follows first-order dynamics with independent time constants.
    The control interval is 1 hour. Internal sub-stepping (10 steps per hour)
    provides smooth dynamics.

    Constraint-safe ranges (for testing):
      WHP: [200, 600] psi
      FLP: [150, 500] psi
      BHP: [2500, 3500] psi
    """

    # Number of internal sub-steps per 1-hour control interval
    _SUB_STEPS = 10

    def __init__(self, seed: int | None = 42) -> None:
        self._rng = random.Random(seed)

        # Internal state
        self._q = 20.0
        self._whp = 450.0
        self._flp = 370.0
        self._bhp = 2960.0

    def step(self, choke_position: float) -> tuple[float, float, float, float]:
        """Simulate one 1-hour control interval.

        Args:
            choke_position: Choke opening in [0, 100] %.

        Returns:
            Tuple of (Q, WHP, FLP, BHP) at the end of the interval.
        """
        u = max(0.0, min(100.0, choke_position))
        dt = 1.0 / self._SUB_STEPS  # hours per sub-step

        for _ in range(self._SUB_STEPS):
            # Steady-state targets
            q_ss = 2.0 * u                      # gain = +2.0 bbl/hr per %
            whp_ss = 500.0 - 3.0 * u            # gain = -3.0 psi per %
            flp_ss = 400.0 - 2.0 * u            # gain = -2.0 psi per %
            bhp_ss = 3000.0 - 4.0 * u           # gain = -4.0 psi per %

            # First-order dynamics: y += (y_ss - y) * (1 - exp(-dt/tau))
            self._q += (q_ss - self._q) * (1.0 - math.exp(-dt / 1.5))
            self._whp += (whp_ss - self._whp) * (1.0 - math.exp(-dt / 1.0))
            self._flp += (flp_ss - self._flp) * (1.0 - math.exp(-dt / 1.0))
            self._bhp += (bhp_ss - self._bhp) * (1.0 - math.exp(-dt / 2.0))

        # Add small measurement noise
        q = max(0.0, self._q + self._rng.gauss(0, 0.3))
        whp = self._whp + self._rng.gauss(0, 0.5)
        flp = self._flp + self._rng.gauss(0, 0.5)
        bhp = self._bhp + self._rng.gauss(0, 1.0)

        return q, whp, flp, bhp

    def reset(self, seed: int | None = 42) -> None:
        """Reset simulator to initial conditions."""
        self._rng = random.Random(seed)
        self._q = 20.0
        self._whp = 450.0
        self._flp = 370.0
        self._bhp = 2960.0
