# Project Reference: Autonomous Production Choke Controller

> **Honeywell Hackathon Solution** — Industrial-grade predictive controller for autonomous oil well choke management.
>
> Generated: 2026-07-25 | Python 3.12 | Dependencies: `numpy>=1.24.0`, `matplotlib>=3.7.0`

---

## 1. WHAT THIS PROJECT IS

An **autonomous model-predictive-like controller** for an oil well production choke (a variable-opening valve controlling flow from the wellbore to surface facilities). The controller receives measurements of 4 process variables every hour, computes the optimal choke opening, and enforces pressure constraints through a defense-in-depth safety architecture.

**Input:** Measurements (Q, WHP, FLP, BHP) + production target (Q_target)  
**Output:** Choke valve position u ∈ [0, 100]%  

---

## 2. ARCHITECTURE: 5-PHASE CONTROL PIPELINE

```
Measurements → Process Monitor → Target Manager ─┐
                 ↓                                 │
              Predictor (candidate generation)      │
                 ↓                                 │
              Safety Gate (constraint filtering)    │
                 ↓                                 │
              Selector (cost optimization) ←────────┘
                 ↓
              u_next [%]
```

### Phase 1: Perception (Process Monitor)
- **File:** `process_monitor.py` (~153 lines)
- Maintains rolling deque buffers (maxlen=20) for all 4 outputs + choke position
- **Bias correction:** Exponentially smoothed prediction error — `bias = α·(y_measured - y_predicted) + (1-α)·bias_prev` where α=0.3
- **Steady-state detection:** Consecutive steps where max-min span / |current| < 0.5% for 3 consecutive steps
- **Safety proximity:** Computes normalized distance to constraint boundaries for WHP, FLP, BHP. Maps to 4 levels:
  - NORMAL: margin ≥ 20% of range
  - CAUTION: margin < 20%
  - WARNING: margin < 10%
  - EMERGENCY: margin < 5%

### Phase 2: Targeting (Target Manager)
- **File:** `target_manager.py` (~54 lines)
- Three operating modes with transitions:
  - **STARTUP:** Initial mode; transitions to TRACKING when |Q - Q_target| < 2%·Q_target for 3+ steady steps
  - **TRACKING:** Normal operation; transitions to INFEASIBLE when all feasible candidates' steady-state Q miss the target for 3+ steady steps
  - **INFEASIBLE:** Constraint-limited; effective target = current Q (drives max safe production)
- Detects target changes to reset mode to TRACKING

### Phase 3: Prediction (Predictor)
- **File:** `predictor.py` (~114 lines)
- **Candidate generation:** Brute-force grid of Δu values from -ramp_limit to +ramp_limit at candidate_step resolution (1.0%), clipped to [choke_min, choke_max]
- In WARNING safety status: ramp limit reduced from 5% to 2%
- Fine resolution (0.5%) when tracking error is within 5% of Q_range
- **FOPDT recursive prediction:**
  ```
  y(k+1) = a·y(k) + b·u(k-d) + (1-a)·bias_offset
  y_ss = K·u_new + bias_offset
  ```
  Applied over Np=3 prediction steps. All predictions include bias correction.
- **Gain scheduling:** 3 operating regions defined by region_boundaries [35, 65]:
  - Region 0: choke ≤ 35% (low range)
  - Region 1: 35% < choke ≤ 65% (mid range)
  - Region 2: choke > 65% (high range)
  - Each region has its own WellModel (4 FOPDT models). Falls back to single model if no gain scheduling.

### Phase 4: Safety (Safety Gate)
- **File:** `safety_gate.py` (~106 lines)
- **Tightened constraints:** Applies 5% margin buffer to constraint limits:
  - `tightened_min = limit_min + 0.05·(limit_max - limit_min)`
  - `tightened_max = limit_max - 0.05·(limit_max - limit_min)`
- **Trajectory checking:** Every predicted step AND steady-state is validated against tightened limits
- Records violation_type, violation_step, and min_margin for each candidate
- **Emergency override:** If current measurements violate HARD limits → immediate corrective action (±ramp_limit) bypassing the optimizer entirely

### Phase 5: Selection (Selector)
- **File:** `selector.py` (~95 lines)
- **3-term cost function:**
  ```
  J = J_track + 0.01·J_effort - 0.005·J_margin
  ```
  | Term | Formula | Purpose |
  |------|---------|---------|
  | J_track | ((Q_pred - Q_target) / Q_range)² | Minimize tracking error |
  | J_effort | (Δu / ramp_limit)² | Penalize aggressive moves |
  | J_margin | -min_constraint_margin | Reward distance from constraints |
- **Deadband:** J_track = 0 when |Q_pred - Q_target| < 1% of Q_range (suppresses micro-moves)
- **INFEASIBLE mode:** J_track = -(Q_pred / Q_range) → maximizes production
- **No feasible candidates:** Selects least-infeasible (highest min_margin)

---

## 3. MODULE INVENTORY

| # | File | Lines | Role |
|---|------|-------|------|
| 1 | `config.py` | 95 | Two dataclasses: `ConstraintLimits` and `ControllerConfig` — single source of truth for all tuning params |
| 2 | `models.py` | 298 | Core data structures: enums (OperatingMode, SafetyStatus), FOPDTParams, WellModel, Measurements, ProcessState, Prediction, CandidateResult, ControlAction, StepTestResult |
| 3 | `process_monitor.py` | 153 | Rolling history, bias correction, steady-state detection, safety proximity |
| 4 | `target_manager.py` | 54 | Mode transitions (STARTUP→TRACKING→INFEASIBLE) |
| 5 | `predictor.py` | 114 | Candidate generation, FOPDT recursive prediction, gain scheduling |
| 6 | `safety_gate.py` | 106 | Tightened constraint evaluation, emergency override |
| 7 | `selector.py` | 95 | 3-term cost function, optimal candidate selection, deadband |
| 8 | `controller.py` | 248 | **Orchestrator** — wires all 5 phases, manages state, logs actions |
| 9 | `simulator_adapter.py` | 115 | `SimulatorAdapter` (wraps any simulator) + `TestSimulator` (built-in FOPDT process) |
| 10 | `step_test.py` | 103 | Automated step test execution for system identification |
| 11 | `model_identifier.py` | 155 | FOPDT parameter identification (graphical 63.2% method) + model validation |
| 12 | `plotter.py` | 222 | Multi-panel matplotlib plots for scenarios, step tests, model validation |
| 13 | `run_scenarios.py` | 140 | Main entry point: identify → control → plot → summarize |
| 14 | `__init__.py` | 24 | Public API re-exports |
| 15 | `requirements.txt` | 2 | numpy, matplotlib |

### Scratch Analysis Scripts (Post-Hoc Consistency Check Only)

These scripts are **NOT part of the control pipeline.** They are standalone tools for comparing simulator-generated results against the reference dataset AFTER all engineering work is complete. They are never imported by any pipeline module.

| File | Purpose |
|------|---------|
| `scratch/analyze_dataset.py` | Statistical analysis of reference CSV (choke events, regime SS, gains, noise) |
| `scratch/full_analysis.py` | Comprehensive 7-section analysis (stats, regimes, transitions, nonlinearity, noise, correlation, SS mapping) |

### Data Provenance Compliance

| Data Source | Role | Pipeline Dependency |
|-------------|------|---------------------|
| TestSimulator | Primary — system ID, tuning, validation | All identification and control |
| Simulator step tests | FOPDT model identification | ModelIdentifier input |
| Reference dataset | Post-hoc sanity check only | NONE — scratch/ only |

---

## 4. DATA MODEL REFERENCE

### FOPDTParams
Discrete First-Order Plus Dead Time model.
- Continuous: `G(s) = K·e^(-θs) / (τs + 1)`
- Discrete: `y(k+1) = a·y(k) + b·u(k-d) + c`
- Key attributes: `gain (K)`, `time_constant (τ)`, `dead_time (d)`, `a = e^(-Ts/τ)`, `b = K·(1-a)`, `bias`
- a is clamped to [-0.999, 0.999] for numerical stability
- Two constructors: `from_continuous()` and `from_discrete()`

### WellModel
Collection of 4 independent FOPDT models: `q`, `whp`, `flp`, `bhp`

### Measurements
Raw sensor snapshot: `q`, `whp`, `flp`, `bhp` (all floats)

### ProcessState
Enriched state with history buffers, bias dict, steady-state flag, safety_status enum

### Prediction
Per-candidate trajectories and steady-state predictions for all 4 outputs

### CandidateResult
Prediction + safety evaluation (is_feasible, violation_type, violation_step, min_margin, margins)

### ControlAction
Final controller decision with full metadata (step, u_prev, u_next, delta_u, cost, reason, mode, safety, measurements, n_candidates, n_feasible)

### StepTestResult
Open-loop step test data (start/end positions, time-series responses, initial/final SS values)

---

## 5. CONFIGURATION PARAMETERS (ControllerConfig)

### Process Parameters
| Param | Default | Unit | Description |
|-------|---------|------|-------------|
| ts | 1.0 | hours | Control interval |
| ramp_limit | 5.0 | % | Max choke movement per step |
| choke_min/max | 0/100 | % | Choke hard limits |

### Prediction
| Param | Default | Description |
|-------|---------|-------------|
| prediction_horizon (Np) | 3 | Steps to predict ahead |
| candidate_step | 1.0% | Resolution of Δu candidates |
| fine_step | 0.5% | Fine resolution near target |
| fine_threshold | 0.05 | Switch to fine when |e|/Q_range < 5% |

### Cost Weights
| Param | Default | Description |
|-------|---------|-------------|
| weight_effort (λ_effort) | 0.01 | Penalty on |Δu|² |
| weight_margin (λ_margin) | 0.005 | Reward for constraint distance |

### Safety
| Param | Default | Unit | Description |
|-------|---------|------|-------------|
| safety_margin | 0.05 | fraction | Tightening buffer for constraints |
| proximity_caution | 0.20 | fraction | CAUTION threshold |
| proximity_warning | 0.10 | fraction | WARNING threshold |
| proximity_emergency | 0.05 | fraction | EMERGENCY threshold |
| warning_ramp_limit | 2.0 | % | Restricted ramp in WARNING |

### Other
| Param | Default | Description |
|-------|---------|-------------|
| bias_alpha | 0.3 | EWMA smoothing factor for bias correction |
| steady_state_tol | 0.005 | Relative change threshold |
| steady_state_steps | 3 | Consecutive steps for SS detection |
| history_size | 20 | Rolling buffer depth |
| target_tolerance | 0.02 | Fraction of Q_range for "target reached" |
| deadband | 0.01 | Fraction of Q_range to suppress micro-moves |
| region_boundaries | [35.0, 65.0] | Gain-scheduling region borders in choke % |

---

## 6. CONSTRAINT LIMITS (ConstraintLimits)

| Variable | Min | Max | Unit | Description |
|----------|-----|-----|------|-------------|
| whp | 200 | 600 | psi | Wellhead pressure |
| flp | 150 | 500 | psi | Flowline pressure |
| bhp | 2500 | 3500 | psi | Bottom-hole pressure |

These are the test-simulator defaults. Real values must be discovered from the actual simulator.

---

## 7. TEST SIMULATOR DYNAMICS

Built-in `TestSimulator` models a naturally flowing oil well:

```
Q_ss   = 2.0 * u           K_q   = +2.0 (bbl/hr per %)
WHP_ss = 500 - 3.0 * u     K_whp = -3.0 (psi per %)
FLP_ss = 400 - 2.0 * u     K_flp = -2.0 (psi per %)
BHP_ss = 3000 - 4.0 * u    K_bhp = -4.0 (psi per %)
```

Time constants: Q=1.5h, WHP=1.0h, FLP=1.0h, BHP=2.0h  
10 sub-steps per control interval for smooth dynamics  
Gaussian measurement noise added at each step

---

## 8. KEY WORKFLOWS

### Full Pipeline (run_scenarios.py)
1. Create TestSimulator(seed=42)
2. StepTestRunner runs exploration suite at choke positions [10,20,30,50,70,80] with +10% steps
3. ModelIdentifier identifies single WellModel from averaged step test results
4. Run 3 scenarios (50 steps each):
   - **A:** Constant target Q=80 bbl/hr
   - **B:** Target change Q=60→120 at step 25
   - **C:** Infeasible target Q=250 bbl/hr (beyond simulator capability)
5. ScenarioPlotter generates 4 output PNGs

### Adapting to Real Simulator
1. Wrap: `adapter = SimulatorAdapter(real_simulator)`
2. Discover constraint limits from documentation
3. Run step tests: `StepTestRunner(config).run_exploration_suite(adapter)`
4. Identify: `ModelIdentifier(config).identify_well_model(results)`
5. Control: `controller.run(adapter, q_targets)`

---

## 9. PUBLIC API (__init__.py)

Exports:
- `AutonomousChokeController` — main controller class
- `ControllerConfig` — tuning parameters dataclass
- `ConstraintLimits` — pressure constraint limits
- `WellModel` — FOPDT model collection
- `FOPDTParams` — discrete FOPDT parameters
- `Measurements` — raw sensor snapshot
- `OperatingMode` — enum (STARTUP, TRACKING, INFEASIBLE)
- `SafetyStatus` — enum (NORMAL, CAUTION, WARNING, EMERGENCY)
- `SimulatorAdapter` — external simulator wrapper
- `TestSimulator` — built-in test process
- `StepTestRunner` — system identification test runner
- `ModelIdentifier` — FOPDT identification engine

---

## 10. FILE ORGANIZATION

```
honeywell_choke_controller/
├── __init__.py             # Public API
├── config.py               # Dataclass configuration
├── models.py               # All data structures
├── controller.py           # Main orchestrator
├── process_monitor.py      # Phase 1: Perception
├── target_manager.py       # Phase 2: Mode management
├── predictor.py            # Phase 3: Prediction
├── safety_gate.py          # Phase 4: Safety filtering
├── selector.py             # Phase 5: Cost optimization
├── simulator_adapter.py    # Simulator wrappers
├── step_test.py            # System identification
├── model_identifier.py     # FOPDT parameter estimation
├── plotter.py              # Visualization
├── run_scenarios.py        # Entry point
├── requirements.txt        # Dependencies
├── scratch/                # Analysis scripts
│   ├── analyze_dataset.py
│   └── full_analysis.py
└── output/                 # Generated plots
    ├── scenario_a_constant_target.png
    ├── scenario_b_target_change.png
    ├── scenario_c_infeasible_target.png
    └── summary_dashboard.png
```

---

## 11. DESIGN DECISIONS & RATIONALE

1. **FOPDT models** chosen for simplicity — industrial standard, easy to identify from step tests
2. **Brute-force candidate search** instead of gradient optimization — robust to non-convex constraints, bounded search space (max 11 candidates at 1% resolution)
3. **Gain scheduling** with hard region boundaries — handles process nonlinearity without complex models
4. **Defense-in-depth safety** with 4 layers — no single point of failure. Emergency override is the last-resort hardware-level safety
5. **Bias correction** with exponential smoothing — mandatory for offset-free tracking in presence of model mismatch and disturbances
6. **Q_range normalization** — makes cost function dimensionless and robust
7. **Deadband** — prevents hunting/chattering when near target
8. **INFEASIBLE mode** — graceful degradation when target is physically impossible under constraints

---

## 12. POTENTIAL EXTENSION POINTS

- Replace brute-force search with more efficient optimization (e.g., Nelder-Mead or SQP)
- Soft constraints (`max(0, violation)²`) instead of hard infeasibility filtering
- Online model adaptation (recursive least squares)
- Multi-well coordination
- Integration with Honeywell Experion DCS via OPC-UA
- Real-time data validation (sensor fault detection)
- Adaptive constraint limits based on well conditions
