"""
Main entry point — runs all three hackathon scenarios and produces plots.

Scenarios:
  A: Constant production target (steady tracking)
  B: Target change mid-run (setpoint transition)
  C: Infeasible target (constraint-limited production)

Usage:
    cd honeywell_choke_controller
    python run_scenarios.py
"""

import logging
import sys
from pathlib import Path

from config import ControllerConfig, ConstraintLimits
from models import SafetyStatus, OperatingMode, Measurements
from simulator_adapter import TestSimulator
from step_test import StepTestRunner
from model_identifier import ModelIdentifier
from controller import AutonomousChokeController
from plotter import ScenarioPlotter

logger = logging.getLogger(__name__)


def main() -> None:
    """Run the complete hackathon pipeline: identify → control → plot."""

    # ── Logging setup ─────────────────────────────────────
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)-25s | %(levelname)-7s | %(message)s",
        stream=sys.stdout,
    )

    # ── Output directory ──────────────────────────────────
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    # ── Configuration ─────────────────────────────────────
    config = ControllerConfig()
    limits = ConstraintLimits(
        whp_min=200.0, whp_max=600.0,
        flp_min=150.0, flp_max=500.0,
        bhp_min=2500.0, bhp_max=3500.0,
    )

    # ── Step 1: Create simulator ──────────────────────────
    simulator = TestSimulator(seed=42)

    # ── Step 2: Run step tests for model identification ───
    logger.info("=" * 50)
    logger.info("PHASE 1: Step Testing & Model Identification")
    logger.info("=" * 50)

    runner = StepTestRunner(config)
    results = runner.run_exploration_suite(simulator)

    # -- Step 3: Identify FOPDT model ----------------------
    identifier = ModelIdentifier(config)
    model = identifier.identify_well_model(results)
    logger.info(
        "Model identified -- Q: K=%.3f, tau=%.3f h | WHP: K=%.3f | FLP: K=%.3f | BHP: K=%.3f",
        model.q.gain, model.q.time_constant,
        model.whp.gain, model.flp.gain, model.bhp.gain,
    )

    # -- Step 4: Define scenarios --------------------------
    n_steps = 50

    scenarios = {
        "Scenario A: Constant Target": [80.0] * n_steps,
        "Scenario B: Target Change": [60.0] * 25 + [120.0] * 25,
        "Scenario C: Infeasible Target": [250.0] * n_steps,
    }

    # -- Step 5: Run each scenario -------------------------
    logger.info("=" * 50)
    logger.info("PHASE 2: Running Control Scenarios")
    logger.info("=" * 50)

    controller = AutonomousChokeController(config, limits, model)
    all_logs = {}

    for name, targets in scenarios.items():
        logger.info("--- %s ---", name)
        controller.reset()
        simulator.reset(seed=42)  # Same initial conditions per scenario
        log = controller.run(simulator, targets, initial_choke=10.0)
        all_logs[name] = log
        logger.info("%s complete: %d steps", name, len(log))

    # ── Step 6: Generate plots ────────────────────────────
    logger.info("=" * 50)
    logger.info("PHASE 3: Generating Plots")
    logger.info("=" * 50)

    plotter = ScenarioPlotter()

    for name, log in all_logs.items():
        safe_name = name.replace(":", "").replace(" ", "_").lower()
        path = str(output_dir / f"{safe_name}.png")
        plotter.plot_scenario(log, limits, title=name, save_path=path)

    plotter.plot_summary_dashboard(
        all_logs, limits, save_path=str(output_dir / "summary_dashboard.png")
    )

    # ── Step 7: Performance summary ───────────────────────
    print("\n" + "=" * 65)
    print("   PERFORMANCE SUMMARY")
    print("=" * 65)

    for name, log in all_logs.items():
        if not log:
            continue
        print(f"\n  {name}:")

        violations = sum(1 for a in log if a.safety_status == SafetyStatus.EMERGENCY)
        final = log[-1]
        tracking_error = abs(final.q - final.q_target)
        infeasible_steps = sum(1 for a in log if a.mode == OperatingMode.INFEASIBLE)

        print(f"    Final Q: {final.q:>8.1f} bbl/hr   (target: {final.q_target:.1f})")
        print(f"    Final choke: {final.u_next:>5.1f}%")
        print(f"    Tracking error: {tracking_error:>8.1f} bbl/hr")
        print(f"    Constraint violations: {violations}")
        print(f"    Final mode: {final.mode.value}")
        print(f"    Steps in INFEASIBLE: {infeasible_steps}")

    print(f"\n  Plots saved to: {output_dir.resolve()}")
    print("=" * 65)


if __name__ == "__main__":
    main()
