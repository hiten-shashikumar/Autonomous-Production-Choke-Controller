# Autonomous Production Choke Controller

<p align="center">
  <img src="https://img.shields.io/badge/Honeywell-Hackathon%202026-E31837?style=flat-square" alt="Honeywell Hackathon 2026">
  <img src="https://img.shields.io/badge/Python-3.12-blue?style=flat-square&logo=python" alt="Python 3.12">
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="MIT License">
  <img src="https://img.shields.io/badge/Status-Complete-success?style=flat-square" alt="Complete">
</p>

**Industrial-grade predictive controller for autonomous oil well choke management.**

---

## Problem Statement

**Honeywell Problem Statement ID 1367** — *Autonomous Choke Control for a Single Naturally Flowing Oil Well*

An oil well production choke is the primary control actuator between the reservoir and surface facilities. Opening the choke increases production but decreases wellhead, flowline, and bottom-hole pressures — which must remain within safe operating limits. The operator must maximize oil production while respecting all pressure constraints. The control interval is 1 hour with a maximum choke movement of ±5% per step.

This project delivers a self-commissioning predictive controller that automatically identifies well dynamics from step tests and controls production autonomously.

---

## Key Features

- **Self-Commissioning** — Automated step testing and FOPDT model identification. No manual tuning required.
- **Predictive Control** — Brute-force candidate search over a 3-step prediction horizon with gain scheduling across three operating regions.
- **Defense-in-Depth Safety** — Four independent protection layers: proximity detection, tightened constraints, trajectory checking, and emergency override.
- **Offset-Free Tracking** — Exponential bias correction (EWMA, α = 0.3) eliminates steady-state error from model mismatch.
- **Graceful Degradation** — When the production target is physically infeasible, the controller maximizes safe production at the constraint boundary.
- **Interactive Dashboard** — 8-page Streamlit monitoring application with Plotly charts for scenario playback, constraint monitoring, and performance KPIs.

---

## Architecture

```
Measurements (Q, WHP, FLP, BHP)
    │
    ▼
┌─────────────────────┐     ┌─────────────────────┐
│ 1. Process Monitor  │────>│ 2. Target Manager   │
│    History buffers  │     │    STARTUP → TRACKING│
│    Bias correction  │     │    → INFEASIBLE     │
│    SS detection     │     └─────────────────────┘
│    Safety proximity │              │
└─────────────────────┘              │
         │                           ▼
         │         ┌─────────────────────────────────┐
         └────────>│ 3. Predictor                    │
                   │    Candidate grid (brute-force) │
                   │    FOPDT prediction (Np = 3)    │
                   │    Gain scheduling (3 regions)  │
                   └─────────────────────────────────┘
                                     │
                                     ▼
                   ┌─────────────────────────────────┐
                   │ 4. Safety Gate                  │
                   │    Tightened constraints (+5%)  │
                   │    Per-step trajectory check    │
                   │    Emergency override           │
                   └─────────────────────────────────┘
                                     │
                                     ▼
                   ┌─────────────────────────────────┐
                   │ 5. Selector                     │
                   │    J = J_track + λ₁·J_effort   │
                   │         + λ₂·J_margin          │
                   │    Deadband suppression         │
                   └─────────────────────────────────┘
                                     │
                                     ▼
                              u_next [%]
```

### Cost Function

```
J_track  = ((Q_pred − Q_target) / Q_range)²     [TRACKING]
         = −(Q_pred / Q_range)                   [INFEASIBLE: maximize production]

J_effort = (Δu / ramp_limit)²

J_margin = −min_constraint_margin

J = J_track + 0.01 × J_effort − 0.005 × J_margin
```

---

## Validation Scenarios

| Scenario | Target | Purpose | Result |
|----------|--------|---------|--------|
| **A** | Q = 80 bbl/hr (constant) | Steady-state tracking with noise | Final Q = 80.9 bbl/hr, error = 0.9 bbl/hr, 0 violations |
| **B** | Q = 60 → 120 bbl/hr (step change at k=25) | Setpoint transition, mode switching | Final Q = 120.9 bbl/hr, error = 0.9 bbl/hr, 0 violations |
| **C** | Q = 250 bbl/hr (infeasible) | Constraint-limited max production | Final Q = 185.9 bbl/hr at choke = 93%, 1 emergency override at BHP boundary |

**All scenarios are fully reproducible at seed = 42. Total: 243 simulator calls.**

---

## Technologies

| Category | Technology |
|----------|-----------|
| Language | Python 3.12 |
| Numerical | NumPy |
| Visualization | Matplotlib, Plotly |
| Dashboard | Streamlit |
| Process Model | First-Order Plus Dead Time (FOPDT) |
| Identification | 63.2% Graphical Method |
| Optimization | Brute-Force Grid Search |
| Safety | 4-Layer Defense-in-Depth |

---

## Installation

```bash
# Clone the repository
git clone https://github.com/hiten-shashikumar/Autonomous-Production-Choke-Controller.git
cd Autonomous-Production-Choke-Controller

# Install dependencies
pip install -r requirements.txt
```

**Requirements:** numpy ≥ 1.24.0, matplotlib ≥ 3.7.0, streamlit ≥ 1.28.0, plotly ≥ 5.17.0

---

## Usage

### Run the Control Pipeline

```bash
python run_scenarios.py
```

Performs three phases automatically:
1. **System Identification** — 6 open-loop step tests across the operating range
2. **Control Execution** — 3 validation scenarios, 50 control steps each
3. **Plot Generation** — 4 publication-quality PNGs saved to `output/`

### Launch the Dashboard

```bash
streamlit run dashboard.py
```

Opens an interactive monitoring application at `http://localhost:8501` with 8 pages:

| Page | Description |
|------|-------------|
| Home | Project overview, KPIs, engineering stack |
| Architecture | 5-phase pipeline + 4-layer safety visualization |
| Scenario Playback | Interactive 4-panel Plotly charts with step-level log |
| Performance KPIs | Per-scenario metrics: tracking error, violations, feasibility |
| Constraint Monitor | WHP/FLP/BHP safety margin bands with emergency thresholds |
| Model Summary | Per-variable FOPDT parameters + continuous transfer functions |
| Validation Report | Gate-by-gate pass/fail evaluation across all scenarios |
| Export Results | CSV download, PNG generation, model JSON export |

### Generate All Deliverables

```bash
python generate_artifacts.py    # Publication-quality figures
python generate_pdfs.py         # Professional PDF reports
python generate_presentation.py  # PowerPoint from SIH template
```

---

## Repository Structure

```
Autonomous-Production-Choke-Controller/
│
├── config.py                    # ControllerConfig + ConstraintLimits (single source of truth)
├── models.py                    # Core data structures: FOPDT, WellModel, enums
├── controller.py                # 5-phase orchestrator
├── process_monitor.py           # Phase 1: Perception, bias correction, SS detection
├── target_manager.py            # Phase 2: Mode management (STARTUP/TRACKING/INFEASIBLE)
├── predictor.py                 # Phase 3: Candidate generation, FOPDT prediction
├── safety_gate.py               # Phase 4: Tightened constraints, emergency override
├── selector.py                  # Phase 5: 3-term cost optimization, deadband
├── simulator_adapter.py         # TestSimulator + external simulator adapter
├── step_test.py                 # Automated step test runner
├── model_identifier.py          # 63.2% graphical FOPDT identification
├── plotter.py                   # Multi-panel matplotlib visualization
├── run_scenarios.py             # Main entry point
├── dashboard.py                 # 8-page Streamlit monitoring dashboard
├── generate_artifacts.py        # Publication-quality figure generator
├── generate_pdfs.py             # Professional PDF report generator
├── generate_presentation.py     # PowerPoint builder from SIH template
├── requirements.txt             # Python dependencies
├── README.md                    # Project documentation
│
├── Final_Deliverables/          # Complete submission package (18 folders)
│   ├── 01_Source_Code/          # All Python modules
│   ├── 02_Technical_Report/     # 12-page engineering PDF
│   ├── 03_Presentation/         # 21-slide SIH submission deck
│   ├── 04_Streamlit_Dashboard/  # Deployable dashboard files
│   ├── 05_Step_Test_Analysis/   # 9 step test plots
│   ├── 06_Model_Identification/ # FOPDT validation plots
│   ├── 07_Controller_Design/    # Architecture + safety PDF
│   ├── 08_Validation_Report/    # 5-gate evaluation results
│   ├── 09_Scenario_Results/     # 3 enhanced 6-panel scenario plots
│   ├── 10_Architecture_Diagrams/ # Pipeline + safety diagrams
│   ├── 11_Workflow_Diagrams/    # Engineering workflows PDF
│   ├── 12_Generated_Plots/      # Standard output figures
│   ├── 13_Reference_Comparison/ # Dataset consistency check PDF
│   ├── 14_Project_Documentation/# Combined documentation PDF
│   ├── 15_Execution_Guide/      # Quick-start instructions
│   ├── 16_Example_Outputs/      # Example outputs with guide
│   └── 17_Submission_Checklist/ # Deliverable verification
│
├── deliverables/                # Generated artifacts (figures, diagrams)
├── output/                      # Pipeline output (plots from run_scenarios.py)
├── scratch/                     # Post-hoc reference dataset analysis (standalone)
├── docs/                        # Source markdown for reports
├── .streamlit/                  # Streamlit theme configuration
└── .gitignore
```

---

## Configuration

Key parameters in `config.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `ts` | 1.0 h | Control interval |
| `ramp_limit` | 5.0% | Maximum choke movement per step |
| `prediction_horizon` | 3 | Steps to predict ahead (Np) |
| `candidate_step` | 1.0% | Coarse candidate resolution |
| `fine_step` | 0.5% | Fine resolution near target |
| `weight_effort` | 0.01 | Penalty on aggressive moves |
| `weight_margin` | 0.005 | Reward for constraint distance |
| `safety_margin` | 0.05 | Constraint tightening buffer (5%) |
| `bias_alpha` | 0.3 | EWMA smoothing factor |
| `deadband` | 0.01 | Micro-move suppression threshold |

Constraint limits in `run_scenarios.py`:

| Variable | Min | Max | Unit |
|----------|-----|-----|------|
| WHP | 200 | 600 | psi |
| FLP | 150 | 500 | psi |
| BHP | 2500 | 3500 | psi |

---

## Future Improvements

- Online model adaptation using recursive least squares
- Soft constraint formulation with exponential penalty functions
- Multi-well coordinated production optimization
- OPC-UA integration with Honeywell Experion DCS
- Reservoir pressure decline disturbance feedforward
- Sensor fault detection with redundant measurement validation

---

## Data Provenance

All model identification, controller tuning, and validation results are derived exclusively from the built-in Python `TestSimulator`. The Honeywell reference dataset was used only as a post-hoc engineering consistency check via standalone scripts in `scratch/` and was never imported by any pipeline module. This complies with the official problem statement requirement that students generate their own data using the simulator.

---

## License

MIT License — see [LICENSE](LICENSE) file for details.

---

<p align="center">
  <b>Honeywell Hackathon 2026 — Engineering Submission v2.0</b><br>
  PS 1367 — Smart Automation — Software
</p>
