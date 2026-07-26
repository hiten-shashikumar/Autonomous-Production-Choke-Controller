# Autonomous Production Choke Controller

## Honeywell Hackathon Solution

Industrial-grade predictive controller for autonomous oil well choke management. Features a 6-module architecture with defense-in-depth safety, FOPDT process modeling, brute-force predictive search optimization, and a simplified 3-term cost function.

---

## Data Provenance & Compliance

| Data Source | Used For | Compliant? |
|-------------|----------|------------|
| **TestSimulator** (built-in) | System identification, controller tuning, validation | ✅ Primary data source |
| **Simulator step tests** | FOPDT model identification via 63.2% method | ✅ Self-generated experimental data |
| **Reference dataset** (`scratch/` only) | Post-hoc engineering consistency check | ✅ Never used for identification/tuning/design |

**The reference dataset is used only as a post-completion sanity check.** All model parameters, controller tuning, and validation results are derived exclusively from the Python simulator. The `scratch/` directory contains standalone analysis scripts that are never imported by any pipeline module.

---

## Architecture

```
 Measurements                     Control Output
     |                                  ^
     v                                  |
+--------------------+    +-------------------+
|  Process Monitor   |--->|  Target Manager   |
| - History buffers  |    | - Mode: STARTUP   |
| - Bias correction  |    |        TRACKING   |
| - Steady-state     |    |        INFEASIBLE |
| - Safety proximity |    +-------------------+
+--------------------+            |
     |                            v
     |    +------------------------------------------+
     +--->|            Predictor                     |
          | - Candidate generation (brute-force)     |
          | - FOPDT recursive prediction             |
          | - Gain-scheduled multi-region models     |
          +------------------------------------------+
                        |
                        v
          +------------------------------------------+
          |           Safety Gate                     |
          | - Tightened constraint boundaries         |
          | - Per-step trajectory checking            |
          | - Steady-state feasibility check          |
          | - Emergency override detection            |
          +------------------------------------------+
                        |
                        v
          +------------------------------------------+
          |            Selector                       |
          | - 3-term cost function                    |
          | - Deadband suppression                    |
          | - Infeasible target: max production       |
          | - Least-infeasible fallback               |
          +------------------------------------------+
                        |
                        v
                   u_next [%]
```

---

## Quick Start

```bash
cd honeywell_choke_controller
pip install -r requirements.txt
python run_scenarios.py
```

Plots are saved to the `output/` directory.

---

## Project Structure

| File | Lines | Description |
|------|-------|-------------|
| `config.py` | ~90 | All tuning parameters as dataclasses. Single source of truth. |
| `models.py` | ~260 | Core data structures: enums, FOPDT params, process state, predictions. |
| `process_monitor.py` | ~130 | Rolling history, bias correction, steady-state detection, safety proximity. |
| `target_manager.py` | ~55 | Operating mode transitions (STARTUP -> TRACKING -> INFEASIBLE). |
| `predictor.py` | ~115 | FOPDT recursive prediction, candidate generation, gain scheduling. |
| `safety_gate.py` | ~110 | Constraint evaluation with tightened margins, emergency override. |
| `selector.py` | ~95 | 3-term cost function, optimal candidate selection, deadband. |
| `controller.py` | ~250 | Main orchestrator wiring all 5 modules together. |
| `simulator_adapter.py` | ~110 | Built-in test simulator + adapter for the real hackathon simulator. |
| `step_test.py` | ~100 | Automated step test runner for model identification. |
| `model_identifier.py` | ~155 | FOPDT parameter identification from step test data. |
| `plotter.py` | ~220 | Multi-panel matplotlib plots for scenarios, step tests, validation. |
| `run_scenarios.py` | ~140 | Main entry point: identify -> control -> plot -> summarize. |
| `requirements.txt` | 2 | numpy, matplotlib |

---

## Configuration

Key parameters in `config.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `ts` | 1.0 h | Control interval |
| `ramp_limit` | 5.0% | Maximum choke movement per step |
| `prediction_horizon` | 3 | Steps to predict ahead |
| `candidate_step` | 1.0% | Resolution of candidate moves |
| `weight_effort` | 0.01 | Penalty on control effort |
| `weight_margin` | 0.005 | Reward for constraint distance |
| `safety_margin` | 0.05 | Fraction of range as safety buffer |

---

## Cost Function

The simplified 3-term cost function:

```
J = J_track + 0.01 * J_effort - 0.005 * J_margin
```

| Term | Formula | Purpose |
|------|---------|---------|
| J_track | ((Q_pred - Q_target) / Q_range)^2 | Minimize tracking error |
| J_effort | (delta_u / ramp_limit)^2 | Penalize aggressive moves |
| J_margin | -min_constraint_margin | Reward distance from limits |

In INFEASIBLE mode, J_track = -(Q_pred / Q_range) to maximize safe production.

---

## Safety Architecture

**Defense-in-depth with 4 layers:**

1. **Proximity Detection** — Process Monitor computes distance to constraints and sets safety status (NORMAL -> CAUTION -> WARNING -> EMERGENCY)
2. **Tightened Constraints** — Safety Gate uses limits + 5% margin buffer for candidate evaluation
3. **Trajectory Checking** — Every prediction step and steady-state is validated against tightened limits
4. **Emergency Override** — If measurements violate hard limits, immediate corrective action bypasses the optimizer

---

## Adapting to the Real Simulator

1. Import the real simulator object
2. Wrap it: `adapter = SimulatorAdapter(real_simulator)`
3. Discover real constraint limits from documentation or exploration
4. Update `ConstraintLimits` with real values
5. Run step tests: `StepTestRunner(config).run_exploration_suite(adapter)`
6. Identify models: `ModelIdentifier(config).identify_well_model(results)`
7. Create controller: `AutonomousChokeController(config, limits, model)`
8. Run: `controller.run(adapter, q_targets)`

---

## Output

The script generates:
- `output/scenario_a_constant_target.png` — Constant target tracking
- `output/scenario_b_target_change.png` — Setpoint transition
- `output/scenario_c_infeasible_target.png` — Constraint-limited operation
- `output/summary_dashboard.png` — All scenarios side-by-side

Each plot has 4 panels: choke position, oil flow rate vs target, pressures vs constraints, and operating mode/safety status.
