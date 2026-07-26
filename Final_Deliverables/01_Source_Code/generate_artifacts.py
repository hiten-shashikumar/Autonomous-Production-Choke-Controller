"""
Generate all publication-quality engineering artifacts.

Produces:
  deliverable 1 — step test response plots (6 tests, 4 variables each)
  deliverable 2 — architecture diagram (5-phase pipeline)
  deliverable 3 — safety layer diagram
  deliverable 4 — enhanced scenario plots with all required subplots
  deliverable 5 — model validation plots

Usage:
    python generate_artifacts.py
"""

import logging
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

# Ensure local imports work
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import ControllerConfig, ConstraintLimits
from models import SafetyStatus, OperatingMode, StepTestResult
from simulator_adapter import TestSimulator
from step_test import StepTestRunner
from model_identifier import ModelIdentifier
from controller import AutonomousChokeController

logger = logging.getLogger(__name__)

# ── Styling ──────────────────────────────────────────────────
plt.rcParams.update({
    "figure.dpi": 150,
    "savefig.dpi": 200,
    "font.family": "sans-serif",
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.titlesize": 14,
})

COLORS = {
    "Q":       "#2563EB",
    "WHP":     "#EA580C",
    "FLP":     "#16A34A",
    "BHP":     "#DC2626",
    "Choke":   "#7C3AED",
    "Target":  "#DB2777",
    "Const":   "#94A3B8",
}

VARIABLE_LABELS = {
    "Q":   ("Oil Flow Rate", "bbl/hr"),
    "WHP": ("Wellhead Pressure", "psi"),
    "FLP": ("Flowline Pressure", "psi"),
    "BHP": ("Bottom-Hole Pressure", "psi"),
}

OUTPUT_ROOT = Path("deliverables")


# ═══════════════════════════════════════════════════════════════
# 1. STEP TEST RESPONSE PLOTS
# ═══════════════════════════════════════════════════════════════

def generate_step_test_plots() -> None:
    """Generate 6 individual step-test response plots + 1 summary."""
    out_dir = OUTPUT_ROOT / "step_tests"
    out_dir.mkdir(parents=True, exist_ok=True)

    config = ControllerConfig()
    sim = TestSimulator(seed=42)
    runner = StepTestRunner(config)

    # Default exploration suite
    test_points = [(10.0, 10.0), (20.0, 10.0), (30.0, 10.0),
                   (50.0, 10.0), (70.0, 10.0), (80.0, 10.0)]

    results = []
    for u_start, delta_u in test_points:
        sim.reset(seed=42)
        res = runner.run_single_test(sim, u_start, delta_u)
        results.append(res)

    # ── Individual test plots ──
    for idx, res in enumerate(results):
        fig, axes = plt.subplots(2, 2, figsize=(12, 8))
        fig.suptitle(
            f"Step Test {idx+1}: Choke {res.u_start:.0f}% \u2192 {res.u_end:.0f}% "
            f"(\u0394u = {res.delta_u:+.0f}%)",
            fontweight="bold",
        )

        variables = [
            ("q_response", "Q", COLORS["Q"], 0, 0),
            ("whp_response", "WHP", COLORS["WHP"], 0, 1),
            ("flp_response", "FLP", COLORS["FLP"], 1, 0),
            ("bhp_response", "BHP", COLORS["BHP"], 1, 1),
        ]

        for resp_attr, var, color, row, col in variables:
            ax = axes[row][col]
            y = getattr(res, resp_attr)
            y_init = getattr(res, f"{var.lower()}_initial" if var != "Q" else "q_initial")
            y_final = getattr(res, f"{var.lower()}_final" if var != "Q" else "q_final")
            label, unit = VARIABLE_LABELS[var]

            ax.plot(res.time, y, "o-", color=color, linewidth=2, markersize=4,
                    label="Response")
            ax.axhline(y_init, color="#94A3B8", linestyle="--", linewidth=1,
                       label=f"Initial: {y_init:.1f}")
            ax.axhline(y_final, color=color, linestyle=":", linewidth=1,
                       label=f"Final: {y_final:.1f}")

            # Mark 63.2% point for time constant identification
            if abs(y_final - y_init) > 0.1:
                y_63 = y_init + 0.632 * (y_final - y_init)
                ax.axhline(y_63, color="#F59E0B", linestyle="-.", linewidth=1, alpha=0.7)
                ax.annotate("63.2%", xy=(res.time[0], y_63),
                            xytext=(res.time[0] + 0.5, y_63 + (y_final - y_init) * 0.05),
                            fontsize=8, color="#F59E0B")

            ax.set_ylabel(f"{label} [{unit}]")
            ax.set_xlabel("Time [hours]")
            ax.legend(loc="best", fontsize=7)
            ax.grid(True, alpha=0.3)

        plt.tight_layout()
        path = out_dir / f"step_test_{idx+1:02d}_choke_{res.u_start:.0f}_to_{res.u_end:.0f}.png"
        fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        logger.info("  Saved: %s", path.name)

    # ── Summary overlay plot ──
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle("Step Test Summary — All 6 Experiments Overlaid", fontweight="bold")

    for idx, (res, (u_s, du)) in enumerate(zip(results, test_points)):
        alpha_val = 0.6 + 0.08 * idx
        for (resp_attr, var, color, row, col) in [
            ("q_response", "Q", COLORS["Q"], 0, 0),
            ("whp_response", "WHP", COLORS["WHP"], 0, 1),
            ("flp_response", "FLP", COLORS["FLP"], 1, 0),
            ("bhp_response", "BHP", COLORS["BHP"], 1, 1),
        ]:
            ax = axes[row][col]
            y = getattr(res, resp_attr)
            label, unit = VARIABLE_LABELS[var]
            ax.plot(res.time, y, "o-", color=color, linewidth=1.5, markersize=3,
                    alpha=alpha_val, label=f"{u_s:.0f}%\u2192{u_s+du:.0f}%")
            ax.set_ylabel(f"{label} [{unit}]")
            ax.set_xlabel("Time [hours]")
            ax.legend(loc="best", fontsize=6, ncol=2)
            ax.grid(True, alpha=0.3)

    plt.tight_layout()
    path = out_dir / "step_test_summary_all_6_tests.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    logger.info("  Saved: %s", path.name)

    print(f"\n  [Step Tests] {len(results)+1} plots saved to {out_dir}/")


# ═══════════════════════════════════════════════════════════════
# 2. ARCHITECTURE DIAGRAM
# ═══════════════════════════════════════════════════════════════

def generate_architecture_diagram() -> None:
    """Generate professional architecture & safety diagrams."""
    out_dir = OUTPUT_ROOT / "architecture"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Pipeline diagram ──
    fig, ax = plt.subplots(figsize=(14, 8))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 10)
    ax.axis("off")
    ax.set_facecolor("white")

    phases = [
        ("Phase 1\nPERCEPTION", "Process Monitor", "History buffers\nBias correction\nSteady-state detection\nSafety proximity", "#2563EB", 1.5),
        ("Phase 2\nTARGETING", "Target Manager", "STARTUP → TRACKING\n→ INFEASIBLE\ntransitions", "#7C3AED", 4.0),
        ("Phase 3\nPREDICTION", "Predictor", "Brute-force candidates\nFOPDT recursive prediction\nGain scheduling (3 regions)", "#EA580C", 6.5),
        ("Phase 4\nSAFETY", "Safety Gate", "Tightened constraints\nTrajectory checking\nEmergency override", "#DC2626", 9.0),
        ("Phase 5\nSELECTION", "Selector", "3-term cost function\nDeadband suppression\nLeast-infeasible fallback", "#16A34A", 11.5),
    ]

    # Draw boxes
    for title, module, desc, color, x in phases:
        box = plt.Rectangle((x - 1.0, 2.5), 2.0, 4.5, linewidth=2, edgecolor=color,
                            facecolor="white", zorder=3, linestyle="-")
        ax.add_patch(box)
        ax.text(x, 6.4, title, ha="center", va="top", fontsize=10, fontweight="bold", color=color)
        ax.text(x, 5.0, module, ha="center", va="center", fontsize=9, fontweight="bold",
                color="#1A1A2E")
        ax.text(x, 3.2, desc, ha="center", va="top", fontsize=7, color="#64748B",
                linespacing=1.3)

    # Draw arrows between boxes
    for i in range(len(phases) - 1):
        x1 = phases[i][4] + 1.0
        x2 = phases[i + 1][4] - 1.0
        y_mid = 4.75
        ax.annotate("", xy=(x2, y_mid), xytext=(x1, y_mid),
                    arrowprops=dict(arrowstyle="->", color="#E31837", lw=2.5))

    # Input/Output labels
    ax.text(0.5, 7.2, "Measurements\n(Q, WHP, FLP, BHP)", ha="center", fontsize=9,
            fontweight="bold", color="#1A1A2E",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#F1F5F9", edgecolor="#2563EB"))
    ax.annotate("", xy=(0.5, y_mid), xytext=(0.5, 6.4),
                arrowprops=dict(arrowstyle="->", color="#2563EB", lw=2))

    ax.text(13.5, 7.2, "u_next [%]\nChoke Position", ha="center", fontsize=9,
            fontweight="bold", color="#1A1A2E",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#F1F5F9", edgecolor="#16A34A"))
    ax.annotate("", xy=(13.5, 6.4), xytext=(13.5, y_mid),
                arrowprops=dict(arrowstyle="->", color="#16A34A", lw=2))

    # Title
    ax.text(7, 8.5, "5-Phase Control Pipeline Architecture",
            ha="center", fontsize=16, fontweight="bold", color="#E31837")
    ax.text(7, 7.8, "Autonomous Production Choke Controller — Honeywell Hackathon 2026",
            ha="center", fontsize=10, color="#64748B")

    # Gain scheduling annotation
    ax.annotate("Gain-Scheduled\n3 Operating Regions\n[0-35%] [35-65%] [65-100%]",
                xy=(6.5, 1.5), fontsize=7, color="#EA580C", ha="center",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="#FFF7ED", edgecolor="#EA580C", alpha=0.8))

    path = out_dir / "controller_pipeline_architecture.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    logger.info("  Saved: %s", path.name)

    # ── Safety layer diagram ──
    fig, axes = plt.subplots(1, 4, figsize=(16, 5))
    fig.suptitle("4-Layer Defense-in-Depth Safety Architecture", fontsize=14, fontweight="bold",
                 color="#E31837")

    layers = [
        ("Layer 1", "Proximity\nDetection",
         "Process Monitor computes\ndistance to constraints:\nNORMAL → CAUTION →\nWARNING → EMERGENCY",
         "#10B981", "Margin ≥ 20%"),
        ("Layer 2", "Tightened\nConstraints",
         "Safety Gate applies\n5% margin buffer:\ntightened min = min + 5%\ntightened max = max − 5%",
         "#F59E0B", "5% buffer"),
        ("Layer 3", "Trajectory\nChecking",
         "Every prediction step\nAND steady-state\nvalidated against\ntightened limits",
         "#F97316", "Per-step"),
        ("Layer 4", "Emergency\nOverride",
         "Hard limit violation\n→ immediate corrective\naction ±5%, bypassing\nthe optimizer entirely",
         "#EF4444", "±5% correction"),
    ]

    for ax, (title, name, desc, color, tag) in zip(axes, layers):
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 10)
        ax.axis("off")

        # Shield/box
        shield = plt.Rectangle((1, 1), 8, 8, linewidth=3, edgecolor=color,
                               facecolor="white", zorder=2, joinstyle="round")
        ax.add_patch(shield)

        ax.text(5, 8.5, title, ha="center", fontsize=11, fontweight="bold", color=color)
        ax.text(5, 6.8, name, ha="center", fontsize=10, fontweight="bold", color="#1A1A2E")
        ax.text(5, 4.2, desc, ha="center", fontsize=8, color="#64748B", linespacing=1.3)
        ax.text(5, 1.8, tag, ha="center", fontsize=7, color=color, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor=color, alpha=0.7))

        # Arrow between layers
        if title != "Layer 4":
            ax.annotate("→", xy=(10.8, 5), xytext=(10.2, 5), fontsize=20, color="#E31837",
                        ha="center", va="center", annotation_clip=False)

    plt.tight_layout()
    path = out_dir / "safety_defense_in_depth.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    logger.info("  Saved: %s", path.name)

    print(f"  [Architecture] 2 diagrams saved to {out_dir}/")


# ═══════════════════════════════════════════════════════════════
# 3. ENHANCED SCENARIO PLOTS
# ═══════════════════════════════════════════════════════════════

def generate_scenario_plots() -> None:
    """Generate publication-quality scenario plots with all 6 subplots."""
    out_dir = OUTPUT_ROOT / "scenarios"
    out_dir.mkdir(parents=True, exist_ok=True)

    config = ControllerConfig()
    limits = ConstraintLimits(
        whp_min=200.0, whp_max=600.0,
        flp_min=150.0, flp_max=500.0,
        bhp_min=2500.0, bhp_max=3500.0,
    )

    scenarios = {
        "scenario_a_constant_target": ("Scenario A: Constant Target (Q=80 bbl/hr)", [80.0] * 50),
        "scenario_b_target_change": ("Scenario B: Target Change (60 → 120 bbl/hr)", [60.0] * 25 + [120.0] * 25),
        "scenario_c_infeasible_target": ("Scenario C: Infeasible Target (Q=250 bbl/hr)", [250.0] * 50),
    }

    sim = TestSimulator(seed=42)
    runner = StepTestRunner(config)
    step_results = runner.run_exploration_suite(sim)
    identifier = ModelIdentifier(config)
    model = identifier.identify_well_model(step_results)

    controller = AutonomousChokeController(config, limits, model)

    for key, (title, targets) in scenarios.items():
        controller.reset()
        sim.reset(seed=42)
        log = controller.run(sim, targets, initial_choke=10.0)

        steps = [a.step for a in log]

        # 6-panel figure
        fig, axes = plt.subplots(3, 2, figsize=(16, 12))
        fig.suptitle(title, fontsize=14, fontweight="bold", color="#1A1A2E")

        # Panel 1: Choke Position
        ax = axes[0][0]
        ax.step(steps, [a.u_next for a in log], where="post", color=COLORS["Choke"], linewidth=2)
        ax.set_ylabel("Choke Position [%]")
        ax.set_ylim(0, 100)
        ax.grid(True, alpha=0.3)
        ax.set_title("Choke Position [%]", fontsize=10, color="#64748B")

        # Panel 2: Oil Rate
        ax = axes[0][1]
        ax.plot(steps, [a.q for a in log], color=COLORS["Q"], linewidth=2, label="Actual Q")
        ax.plot(steps, [a.q_target for a in log], color=COLORS["Target"], linewidth=2,
                linestyle="--", label="Target Q")
        ax.fill_between(steps, [a.q for a in log], [a.q_target for a in log],
                        color=COLORS["Target"], alpha=0.08)
        ax.set_ylabel("Oil Flow Rate [bbl/hr]")
        ax.legend(loc="best", fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.set_title("Oil Flow Rate [bbl/hr]", fontsize=10, color="#64748B")

        # Panel 3: WHP
        ax = axes[1][0]
        ax.plot(steps, [a.whp for a in log], color=COLORS["WHP"], linewidth=2)
        ax.axhline(limits.whp_min, color=COLORS["Const"], linestyle="--", linewidth=1, alpha=0.5)
        ax.axhline(limits.whp_max, color=COLORS["Const"], linestyle="--", linewidth=1, alpha=0.5)
        ax.set_ylabel("Wellhead Pressure [psi]")
        ax.grid(True, alpha=0.3)
        ax.set_title("Wellhead Pressure [psi]", fontsize=10, color="#64748B")

        # Panel 4: FLP
        ax = axes[1][1]
        ax.plot(steps, [a.flp for a in log], color=COLORS["FLP"], linewidth=2)
        ax.axhline(limits.flp_min, color=COLORS["Const"], linestyle="--", linewidth=1, alpha=0.5)
        ax.axhline(limits.flp_max, color=COLORS["Const"], linestyle="--", linewidth=1, alpha=0.5)
        ax.set_ylabel("Flowline Pressure [psi]")
        ax.grid(True, alpha=0.3)
        ax.set_title("Flowline Pressure [psi]", fontsize=10, color="#64748B")

        # Panel 5: BHP
        ax = axes[2][0]
        ax.plot(steps, [a.bhp for a in log], color=COLORS["BHP"], linewidth=2)
        ax.axhline(limits.bhp_min, color=COLORS["Const"], linestyle="--", linewidth=1, alpha=0.5)
        ax.axhline(limits.bhp_max, color=COLORS["Const"], linestyle="--", linewidth=1, alpha=0.5)
        ax.set_ylabel("Bottom-Hole Pressure [psi]")
        ax.set_xlabel("Time Step [hours]")
        ax.grid(True, alpha=0.3)
        ax.set_title("Bottom-Hole Pressure [psi]", fontsize=10, color="#64748B")

        # Panel 6: Mode & Safety timeline
        ax = axes[2][1]
        mode_map = {OperatingMode.STARTUP: 0, OperatingMode.TRACKING: 1, OperatingMode.INFEASIBLE: 2}
        safety_map = {SafetyStatus.NORMAL: 0, SafetyStatus.CAUTION: 1,
                      SafetyStatus.WARNING: 2, SafetyStatus.EMERGENCY: 3}

        ax.step(steps, [mode_map[a.mode] for a in log], where="post",
                color="#F59E0B", linewidth=2, label="Operating Mode")
        ax.step(steps, [safety_map[a.safety_status] for a in log], where="post",
                color="#EF4444", linewidth=2, linestyle="--", label="Safety Status")
        ax.set_yticks([0, 1, 2, 3])
        ax.set_yticklabels(["STARTUP\nNORMAL", "TRACKING\nCAUTION",
                            "INFEASIBLE\nWARNING", "—\nEMERGENCY"], fontsize=7)
        ax.set_xlabel("Time Step [hours]")
        ax.legend(loc="best", fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.set_title("Operating Mode & Safety Status", fontsize=10, color="#64748B")

        plt.tight_layout()
        path = out_dir / f"{key}.png"
        fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        logger.info("  Saved: %s", path.name)

    print(f"  [Scenarios] 3 enhanced plots saved to {out_dir}/")


# ═══════════════════════════════════════════════════════════════
# 4. MODEL VALIDATION PLOTS
# ═══════════════════════════════════════════════════════════════

def generate_model_validation_plots() -> None:
    """Generate model identification validation plots."""
    out_dir = OUTPUT_ROOT / "step_tests"
    out_dir.mkdir(parents=True, exist_ok=True)

    config = ControllerConfig()
    sim = TestSimulator(seed=42)
    runner = StepTestRunner(config)
    identifier = ModelIdentifier(config)
    results = runner.run_exploration_suite(sim)

    variables = ["q", "whp", "flp", "bhp"]
    var_colors = {"q": COLORS["Q"], "whp": COLORS["WHP"],
                  "flp": COLORS["FLP"], "bhp": COLORS["BHP"]}

    fig, axes = plt.subplots(4, 1, figsize=(12, 14))
    fig.suptitle("Model Identification Validation — All Step Tests", fontsize=14, fontweight="bold")

    for var_idx, var in enumerate(variables):
        ax = axes[var_idx]
        label, unit = VARIABLE_LABELS[var.upper()]

        all_actual = []
        all_predicted = []

        for test_idx, res in enumerate(results):
            fopdt = identifier.identify_fopdt(res, var)
            actual = getattr(res, f"{var}_response")
            y_curr = getattr(res, f"{var}_initial")

            predicted = []
            for _ in actual:
                y_curr = fopdt.a * y_curr + fopdt.b * res.u_end
                predicted.append(y_curr + fopdt.bias)

            all_actual.extend(actual)
            all_predicted.extend(predicted)

            alpha_val = 0.4 + 0.1 * test_idx
            t_offset = test_idx * 15
            t_vals = [t_offset + t for t in res.time]

            ax.plot(t_vals, actual, "-", color=var_colors[var], linewidth=1.5,
                    alpha=alpha_val)
            ax.plot(t_vals, predicted, "--", color="#64748B", linewidth=1, alpha=alpha_val)

            # RMSE annotation per test
            residuals = [a - p for a, p in zip(actual, predicted)]
            rmse = np.sqrt(np.mean(np.square(residuals)))
            ax.text(t_offset + 0.5, min(actual) - (max(actual) - min(actual)) * 0.15,
                    f"RMSE={rmse:.2f}", fontsize=6, color="#64748B", alpha=alpha_val)

        ax.set_ylabel(f"{label} [{unit}]")
        ax.grid(True, alpha=0.3)
        ax.legend(["Actual", "Predicted (FOPDT)"], loc="upper right", fontsize=8)

    axes[-1].set_xlabel("Time [hours]")
    plt.tight_layout()
    path = out_dir / "model_identification_validation.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    logger.info("  Saved: %s", path.name)

    # ── Gain comparison bar chart ──
    fig, ax = plt.subplots(figsize=(8, 5))
    fig.suptitle("Average Identified Gains Across 6 Step Tests", fontsize=12, fontweight="bold")

    for var in variables:
        gains = []
        for res in results:
            fopdt = identifier.identify_fopdt(res, var)
            gains.append(fopdt.gain)
        avg_gain = np.mean(gains)
        std_gain = np.std(gains)
        color = var_colors[var]
        ax.bar(var.upper(), avg_gain, color=color, alpha=0.8, edgecolor="white", linewidth=1)
        ax.errorbar(var.upper(), avg_gain, yerr=std_gain, fmt="none", color="#1A1A2E",
                    capsize=6, linewidth=1.5)

    ax.axhline(y=0, color="#1A1A2E", linewidth=0.5)
    ax.set_ylabel("Gain K")
    ax.grid(True, alpha=0.3, axis="y")

    # Annotate with numeric values
    for var in variables:
        gains = []
        for res in results:
            fopdt = identifier.identify_fopdt(res, var)
            gains.append(fopdt.gain)
        avg_gain = np.mean(gains)
        offset = 0.05 if avg_gain >= 0 else -0.15
        ax.text(var.upper(), avg_gain + offset, f"{avg_gain:+.3f}", ha="center", fontsize=9,
                fontweight="bold")

    plt.tight_layout()
    path = out_dir / "gain_comparison.png"
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    logger.info("  Saved: %s", path.name)

    print(f"  [Validation] 2 plots saved to {out_dir}/")


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)

    print("\n" + "=" * 65)
    print("  GENERATING ENGINEERING DELIVERABLES")
    print("  Honeywell Autonomous Choke Controller")
    print("=" * 65)

    print("\n[1/4] Step Test Response Plots")
    generate_step_test_plots()

    print("\n[2/4] Architecture Diagrams")
    generate_architecture_diagram()

    print("\n[3/4] Enhanced Scenario Plots")
    generate_scenario_plots()

    print("\n[4/4] Model Validation Plots")
    generate_model_validation_plots()

    print("\n" + "=" * 65)
    print(f"  ALL DELIVERABLES GENERATED")
    print(f"  Output: {OUTPUT_ROOT.resolve()}")
    print("=" * 65)


if __name__ == "__main__":
    main()
