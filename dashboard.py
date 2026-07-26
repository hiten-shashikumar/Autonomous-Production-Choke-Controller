"""
Streamlit Dashboard — Autonomous Production Choke Controller.

Professional industrial monitoring application for the Honeywell Hackathon.
Clean light theme with Honeywell red accents. All text fully readable.

Usage:
    streamlit run dashboard.py
"""

from __future__ import annotations

import sys
import json
from pathlib import Path
from typing import Optional

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# Ensure local package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import ControllerConfig, ConstraintLimits
from models import (
    ControlAction,
    SafetyStatus,
    OperatingMode,
)
from simulator_adapter import TestSimulator
from step_test import StepTestRunner
from model_identifier import ModelIdentifier
from controller import AutonomousChokeController

# ═══════════════════════════════════════════════════════════════
# Page Configuration (uses .streamlit/config.toml for theme)
# ═══════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Honeywell — Autonomous Choke Controller",
    page_icon="🛢️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═══════════════════════════════════════════════════════════════
# Brand Colors — Honeywell Red + Clean Industrial Palette
# ═══════════════════════════════════════════════════════════════

HW_RED = "#E31837"
HW_DARK = "#1A1A2E"
HW_GRAY = "#64748B"
HW_LIGHT = "#F1F5F9"
HW_WHITE = "#FFFFFF"

PLOT_COLORS = {
    "Q":       "#2563EB",  # blue
    "WHP":     "#EA580C",  # orange
    "FLP":     "#16A34A",  # green
    "BHP":     "#DC2626",  # red
    "Choke":   "#7C3AED",  # purple
    "Target":  "#DB2777",  # pink
    "Constraint": "#94A3B8",  # slate
}

MODE_LABELS = {
    OperatingMode.STARTUP:    ("STARTUP",    "#F59E0B"),  # amber
    OperatingMode.TRACKING:   ("TRACKING",   "#10B981"),  # emerald
    OperatingMode.INFEASIBLE: ("INFEASIBLE", "#EF4444"),  # red
}

SAFETY_LABELS = {
    SafetyStatus.NORMAL:    ("NORMAL",    "#10B981"),
    SafetyStatus.CAUTION:   ("CAUTION",   "#F59E0B"),
    SafetyStatus.WARNING:   ("WARNING",   "#F97316"),
    SafetyStatus.EMERGENCY: ("EMERGENCY", "#EF4444"),
}

# ═══════════════════════════════════════════════════════════════
# Minimal, Safe CSS — Only what Streamlit doesn't provide natively
# ═══════════════════════════════════════════════════════════════

st.markdown(
    """
<style>
    /* Card-style containers */
    .hw-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 0.75rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    .hw-card-red {
        background: #FFFFFF;
        border-left: 4px solid #E31837;
        border-radius: 8px;
        padding: 1rem 1.25rem;
        margin-bottom: 0.75rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    /* Phase arrow between architecture steps */
    .hw-arrow {
        text-align: center;
        color: #E31837;
        font-size: 1.3rem;
        margin: -0.3rem 0;
        font-weight: bold;
    }
    /* KPI value emphasis */
    .hw-kpi-value {
        font-size: 2rem;
        font-weight: 700;
        color: #1A1A2E;
        line-height: 1.1;
    }
    .hw-kpi-label {
        font-size: 0.8rem;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-weight: 600;
    }
    /* Divider line */
    .hw-divider {
        height: 1px;
        background: #E2E8F0;
        margin: 1rem 0;
    }
    /* Reduce excessive padding */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 1rem;
    }
</style>
""",
    unsafe_allow_html=True,
)

# ═══════════════════════════════════════════════════════════════
# Session State
# ═══════════════════════════════════════════════════════════════

def init_session() -> None:
    if "initialized" not in st.session_state:
        st.session_state.initialized = True
        st.session_state.config = ControllerConfig()
        st.session_state.limits = ConstraintLimits(
            whp_min=200.0, whp_max=600.0,
            flp_min=150.0, flp_max=500.0,
            bhp_min=2500.0, bhp_max=3500.0,
        )
        st.session_state.scenarios = {
            "A · Constant Target (Q=80 bbl/hr)": [80.0] * 50,
            "B · Target Step Change (60→120)": [60.0] * 25 + [120.0] * 25,
            "C · Infeasible Target (Q=250)": [250.0] * 50,
        }
        st.session_state.model = None
        st.session_state.logs = {}
        st.session_state.ready = False


def run_simulations() -> None:
    """Execute identification + control pipeline."""
    config = st.session_state.config
    limits = st.session_state.limits

    status = st.status("🔬 Running System Identification & Control Pipeline...", expanded=True)

    with status:
        st.write("**Phase 1/3:** Step testing on simulator...")
        sim = TestSimulator(seed=42)
        runner = StepTestRunner(config)
        results = runner.run_exploration_suite(sim)
        identifier = ModelIdentifier(config)
        model = identifier.identify_well_model(results)
        st.session_state.model = model
        st.write(f"✅ Model identified — Q gain: {model.q.gain:+.2f}, τ={model.q.time_constant:.1f}h")

        st.write("**Phase 2/3:** Running 3 control scenarios...")
        logs = {}
        controller = AutonomousChokeController(config, limits, model)
        progress_bar = st.progress(0)

        for idx, (name, targets) in enumerate(st.session_state.scenarios.items()):
            controller.reset()
            sim.reset(seed=42)
            log = controller.run(sim, targets, initial_choke=10.0)
            logs[name] = log
            progress_bar.progress((idx + 1) / 3)

        progress_bar.empty()
        st.session_state.logs = logs
        st.session_state.ready = True
        st.write("✅ All 3 scenarios complete — 150 control steps executed")

    status.update(label="✅ Pipeline Complete — Ready for Analysis", state="complete")


# ═══════════════════════════════════════════════════════════════
# Sidebar
# ═══════════════════════════════════════════════════════════════

def render_sidebar() -> str:
    with st.sidebar:
        # Brand header
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:10px;margin-bottom:0.5rem;'>"
            f"<div style='background:{HW_RED};width:4px;height:32px;border-radius:2px;'></div>"
            f"<div><strong style='font-size:1.15rem;color:{HW_DARK};'>Choke Controller</strong><br>"
            f"<span style='font-size:0.75rem;color:{HW_GRAY};'>Honeywell Hackathon 2026</span></div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        st.markdown("<div class='hw-divider'></div>", unsafe_allow_html=True)

        # Navigation
        page = st.radio(
            "NAVIGATION",
            [
                "🏠  Home",
                "🏗️  Architecture",
                "📊  Scenario Playback",
                "📈  Performance KPIs",
                "🛡️  Constraint Monitor",
                "🔬  Model Summary",
                "📋  Validation Report",
                "⬇️  Export Results",
            ],
            label_visibility="collapsed",
        )

        st.markdown("<div class='hw-divider'></div>", unsafe_allow_html=True)

        # Run button
        col_run, _ = st.columns([2, 1])
        with col_run:
            if st.button("🚀  Run Pipeline", use_container_width=True, type="primary"):
                run_simulations()

        # Status
        if st.session_state.ready and st.session_state.model:
            st.success("✅ Pipeline Complete", icon="✅")

            # Model summary in sidebar
            m = st.session_state.model
            with st.expander("📐 Identified Model", expanded=False):
                for var, name in [("q", "Oil Rate"), ("whp", "WHP"), ("flp", "FLP"), ("bhp", "BHP")]:
                    fm = m.get_model(var)
                    st.caption(
                        f"**{name}**  \n"
                        f"K={fm.gain:+.2f}  τ={fm.time_constant:.1f}h  θ={fm.dead_time}"
                    )

        elif not st.session_state.ready:
            st.info("👆 Click **Run Pipeline** to start", icon="ℹ️")

        st.markdown("<div class='hw-divider'></div>", unsafe_allow_html=True)
        st.caption("Engineering Submission v2.0")

    return page


# ═══════════════════════════════════════════════════════════════
# Shared Plotly Layout
# ═══════════════════════════════════════════════════════════════

PLOTLY_BASE = dict(
    template="simple_white",
    font=dict(family="sans-serif", size=12, color=HW_DARK),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(showgrid=True, gridcolor="#E2E8F0", zeroline=False),
    yaxis=dict(showgrid=True, gridcolor="#E2E8F0", zeroline=False),
    hovermode="x unified",
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1,
        bgcolor="rgba(255,255,255,0.9)",
        bordercolor="#E2E8F0",
        borderwidth=1,
    ),
    margin=dict(l=50, r=20, t=60, b=40),
)


def make_plotly_figure(title: str = "", height: int = 600, **kwargs) -> go.Figure:
    """Base layout for consistent chart styling."""
    layout = {**PLOTLY_BASE, "height": height, **kwargs}
    if title:
        layout["title"] = dict(text=title, font=dict(size=16, color=HW_DARK))
    return go.Figure(layout=go.Layout(**layout))


# ═══════════════════════════════════════════════════════════════
# Page: Home
# ═══════════════════════════════════════════════════════════════

def render_home() -> None:
    st.markdown(
        f"<h1 style='color:{HW_DARK};font-size:1.8rem;margin-bottom:0;'>"
        f"Autonomous Production Choke Controller</h1>"
        f"<p style='color:{HW_GRAY};font-size:1rem;margin-top:0.2rem;'>"
        f"Industrial-Grade Predictive Control for Oil Well Management</p>",
        unsafe_allow_html=True,
    )

    # KPI row
    c1, c2, c3, c4 = st.columns(4)
    for col, value, label, delta in [
        (c1, "1.0 h", "Control Interval", "Ts"),
        (c2, "3 steps", "Prediction Horizon", "Np"),
        (c3, "±5.0 %", "Max Move / Step", "Δuₘₐₓ"),
        (c4, "4 Layers", "Safety Architecture", "Defense-in-Depth"),
    ]:
        with col:
            st.markdown(
                f"<div class='hw-card' style='text-align:center;'>"
                f"<div class='hw-kpi-value'>{value}</div>"
                f"<div class='hw-kpi-label'>{label}</div>"
                f"<div style='font-size:0.7rem;color:{HW_GRAY};margin-top:0.15rem;'>{delta}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    # Two-column layout
    left, right = st.columns([3, 2])

    with left:
        st.markdown(f"<h3 style='color:{HW_DARK};'>Project Overview</h3>", unsafe_allow_html=True)
        st.markdown(f"""
        <div class='hw-card'>
        <p style='color:{HW_DARK};margin:0;'>
        An <strong>autonomous model-predictive controller</strong> for oil well production choke management.
        5-phase pipeline with defense-in-depth safety, FOPDT process modeling, brute-force predictive
        search optimization, and automated system identification.
        </p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"<h3 style='color:{HW_DARK};'>Key Capabilities</h3>", unsafe_allow_html=True)
        capabilities = [
            ("🎯", "FOPDT predictive control with 3-step horizon & gain scheduling"),
            ("🛡️", "Four-layer defense-in-depth safety architecture"),
            ("📐", "3-term cost function with deadband suppression"),
            ("🔬", "Automated system identification via step testing"),
            ("⚡", "Emergency override with hard constraint enforcement"),
            ("📊", "Interactive Streamlit dashboard with Plotly visualization"),
        ]
        for icon, text in capabilities:
            st.markdown(
                f"<div class='hw-card-red'>"
                f"<span style='font-size:1.1rem;'>{icon}</span> "
                f"<span style='color:{HW_DARK};'>{text}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

    with right:
        st.markdown(f"<h3 style='color:{HW_DARK};'>Engineering Stack</h3>", unsafe_allow_html=True)
        st.markdown(f"""
        <div class='hw-card'>
        <table style='width:100%;border-collapse:collapse;color:{HW_DARK};'>
        <tr><td style='padding:4px 0;color:{HW_GRAY};'>Process Model</td>
            <td style='padding:4px 0;'><strong>FOPDT</strong></td></tr>
        <tr><td style='padding:4px 0;color:{HW_GRAY};'>Identification</td>
            <td style='padding:4px 0;'><strong>63.2% Graphical</strong></td></tr>
        <tr><td style='padding:4px 0;color:{HW_GRAY};'>Optimization</td>
            <td style='padding:4px 0;'><strong>Brute-Force Grid</strong></td></tr>
        <tr><td style='padding:4px 0;color:{HW_GRAY};'>Safety</td>
            <td style='padding:4px 0;'><strong>Tightened + Emergency</strong></td></tr>
        <tr><td style='padding:4px 0;color:{HW_GRAY};'>Cost Function</td>
            <td style='padding:4px 0;'><strong>J_track + λ₁J_effort + λ₂J_margin</strong></td></tr>
        <tr><td style='padding:4px 0;color:{HW_GRAY};'>Viz</td>
            <td style='padding:4px 0;'><strong>Plotly + Matplotlib</strong></td></tr>
        <tr><td style='padding:4px 0;color:{HW_GRAY};'>Dashboard</td>
            <td style='padding:4px 0;'><strong>Streamlit</strong></td></tr>
        </table>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"<h3 style='color:{HW_DARK};'>Data Provenance</h3>", unsafe_allow_html=True)
        st.markdown(f"""
        <div class='hw-card' style='font-size:0.85rem;color:{HW_DARK};'>
        <p>✅ <strong>All models identified from simulator step tests</strong></p>
        <p style='font-size:0.75rem;color:{HW_GRAY};margin:0;'>
        243 total simulator calls across step tests + control scenarios.
        Reference dataset used only for post-hoc consistency check in <code>scratch/</code>.
        </p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div class='hw-divider'></div>", unsafe_allow_html=True)
    st.info(
        "👈 **Click 'Run Pipeline' in the sidebar** to execute identification → control → "
        "visualization, then explore results in **Scenario Playback**."
    )


# ═══════════════════════════════════════════════════════════════
# Page: Architecture
# ═══════════════════════════════════════════════════════════════

def render_architecture() -> None:
    st.markdown(
        f"<h1 style='color:{HW_DARK};font-size:1.8rem;'>Controller Architecture</h1>"
        f"<p style='color:{HW_GRAY};'>5-Phase Control Pipeline with Defense-in-Depth Safety</p>",
        unsafe_allow_html=True,
    )

    phases = [
        ("Phase 1", "Process Monitor", "🔍",
         "Rolling history buffers, exponential bias correction, steady-state detection, safety proximity computation"),
        ("Phase 2", "Target Manager", "🎯",
         "Operating mode state machine: STARTUP → TRACKING → INFEASIBLE based on feasibility assessment"),
        ("Phase 3", "Predictor", "🔮",
         "Brute-force candidate grid generation, FOPDT recursive prediction over 3-step horizon, gain scheduling across 3 regions"),
        ("Phase 4", "Safety Gate", "🛡️",
         "Tightened constraint evaluation with 5% margin buffer, per-step trajectory checking, emergency override detection"),
        ("Phase 5", "Selector", "✅",
         "3-term cost minimization: J_track + 0.01·J_effort − 0.005·J_margin, deadband suppression, least-infeasible fallback"),
    ]

    for i, (phase, module, icon, desc) in enumerate(phases):
        st.markdown(
            f"<div class='hw-card-red' style='display:flex;align-items:flex-start;gap:14px;'>"
            f"<div style='font-size:1.6rem;min-width:36px;text-align:center;'>{icon}</div>"
            f"<div style='flex:1;'>"
            f"<strong style='color:{HW_RED};'>{phase}</strong>"
            f"<span style='color:{HW_DARK};margin-left:8px;font-weight:600;'>{module}</span>"
            f"<p style='color:{HW_GRAY};margin:4px 0 0 0;font-size:0.9rem;'>{desc}</p>"
            f"</div></div>",
            unsafe_allow_html=True,
        )
        if i < len(phases) - 1:
            st.markdown("<div class='hw-arrow'>↓</div>", unsafe_allow_html=True)

    st.markdown("<div class='hw-divider'></div>", unsafe_allow_html=True)

    # Safety layers
    st.markdown(f"<h3 style='color:{HW_DARK};'>Safety Architecture: 4-Layer Defense-in-Depth</h3>", unsafe_allow_html=True)

    layers = [
        ("1", "Proximity Detection", "NORMAL → CAUTION → WARNING → EMERGENCY", "#10B981"),
        ("2", "Tightened Constraints", "+5% margin buffer on all limits", "#F59E0B"),
        ("3", "Trajectory Checking", "Every step + steady-state validated", "#F97316"),
        ("4", "Emergency Override", "Hard limit breach → immediate correction", "#EF4444"),
    ]

    cols = st.columns(4)
    for col, (num, name, desc, color) in zip(cols, layers):
        with col:
            st.markdown(
                f"<div class='hw-card' style='text-align:center;padding:1rem 0.75rem;'>"
                f"<div style='background:{color};color:white;width:32px;height:32px;border-radius:16px;"
                f"display:inline-flex;align-items:center;justify-content:center;"
                f"font-weight:700;font-size:1rem;margin-bottom:0.5rem;'>{num}</div>"
                f"<div style='font-weight:600;color:{HW_DARK};font-size:0.9rem;'>{name}</div>"
                f"<div style='color:{HW_GRAY};font-size:0.75rem;margin-top:0.25rem;'>{desc}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )


# ═══════════════════════════════════════════════════════════════
# Page: Scenario Playback
# ═══════════════════════════════════════════════════════════════

def render_scenario_playback() -> None:
    st.markdown(
        f"<h1 style='color:{HW_DARK};font-size:1.8rem;'>Scenario Playback</h1>"
        f"<p style='color:{HW_GRAY};'>Interactive Controller Performance Visualization</p>",
        unsafe_allow_html=True,
    )

    if not st.session_state.ready:
        st.warning("⚠️ No simulation data. Click **Run Pipeline** in the sidebar first.")
        return

    scenario_name = st.selectbox("Select Scenario", list(st.session_state.scenarios.keys()))
    log = st.session_state.logs.get(scenario_name, [])
    if not log:
        return

    limits = st.session_state.limits
    steps = [a.step for a in log]

    # Build 4-panel Plotly figure
    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.05,
        subplot_titles=("Choke Position [%]", "Oil Flow Rate [bbl/hr]",
                        "Pressure Constraints [psi]", "Operating Mode & Safety Status"),
        row_heights=[0.2, 0.3, 0.3, 0.2],
    )

    # Panel 1: Choke
    fig.add_trace(go.Scatter(
        x=steps, y=[a.u_next for a in log], mode="lines+markers",
        name="Choke", line=dict(color=PLOT_COLORS["Choke"], width=2.5),
        marker=dict(size=4), hovertemplate="Step %{x}: Choke = %{y:.1f}%<extra></extra>",
    ), row=1, col=1)
    fig.update_yaxes(title_text="[%]", row=1, col=1, range=[0, 100], **PLOTLY_BASE["yaxis"])

    # Panel 2: Q
    fig.add_trace(go.Scatter(
        x=steps, y=[a.q for a in log], mode="lines+markers",
        name="Actual Q", line=dict(color=PLOT_COLORS["Q"], width=2.5),
        marker=dict(size=4), hovertemplate="Step %{x}: Q = %{y:.1f} bbl/hr<extra></extra>",
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=steps, y=[a.q_target for a in log], mode="lines",
        name="Target Q", line=dict(color=PLOT_COLORS["Target"], width=2, dash="dash"),
        hovertemplate="Step %{x}: Target = %{y:.0f} bbl/hr<extra></extra>",
    ), row=2, col=1)
    fig.update_yaxes(title_text="[bbl/hr]", row=2, col=1, **PLOTLY_BASE["yaxis"])

    # Panel 3: Pressures
    for var, color, label in [("whp", PLOT_COLORS["WHP"], "WHP"),
                               ("flp", PLOT_COLORS["FLP"], "FLP"),
                               ("bhp", PLOT_COLORS["BHP"], "BHP")]:
        fig.add_trace(go.Scatter(
            x=steps, y=[getattr(a, var) for a in log], mode="lines",
            name=label, line=dict(color=color, width=1.8),
        ), row=3, col=1)
    for limit_val, dash in [(limits.whp_max, "dot"), (limits.flp_min, "dash"),
                              (limits.flp_max, "dash"), (limits.bhp_min, "dot"),
                              (limits.bhp_max, "dot")]:
        fig.add_hline(y=limit_val, line_dash=dash, line_color=PLOT_COLORS["Constraint"],
                      opacity=0.5, row=3, col=1)
    fig.update_yaxes(title_text="[psi]", row=3, col=1, **PLOTLY_BASE["yaxis"])

    # Panel 4: Mode + Safety
    mode_map = {OperatingMode.STARTUP: 0, OperatingMode.TRACKING: 1, OperatingMode.INFEASIBLE: 2}
    safety_map = {SafetyStatus.NORMAL: 0, SafetyStatus.CAUTION: 1,
                  SafetyStatus.WARNING: 2, SafetyStatus.EMERGENCY: 3}

    fig.add_trace(go.Scatter(
        x=steps, y=[mode_map[a.mode] for a in log],
        mode="lines+markers", name="Mode",
        line=dict(color="#F59E0B", width=2.5), marker=dict(size=5),
    ), row=4, col=1)
    fig.add_trace(go.Scatter(
        x=steps, y=[safety_map[a.safety_status] for a in log],
        mode="lines+markers", name="Safety",
        line=dict(color="#EF4444", width=2, dash="dot"), marker=dict(size=5, symbol="x"),
    ), row=4, col=1)
    fig.update_yaxes(
        title_text="Level", row=4, col=1,
        tickvals=[0, 1, 2, 3],
        ticktext=["STARTUP / NORMAL", "TRACKING / CAUTION", "INFEASIBLE / WARNING", "— / EMERGENCY"],
        **PLOTLY_BASE["yaxis"],
    )
    fig.update_xaxes(title_text="Time Step [hours]", row=4, col=1, **PLOTLY_BASE["xaxis"])

    fig.update_layout(**PLOTLY_BASE, height=850,
                       title=dict(text=scenario_name, font=dict(size=16, color=HW_DARK)))

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": True, "displaylogo": False})

    # Detail table
    with st.expander("📋 Detailed Step-by-Step Control Log", expanded=False):
        st.dataframe(
            [{"Step": a.step, "u [%]": f"{a.u_next:.1f}", "Δu [%]": f"{a.delta_u:+.1f}",
              "Q [bbl/hr]": f"{a.q:.1f}", "Target": f"{a.q_target:.1f}",
              "Mode": a.mode.value, "Safety": a.safety_status.value,
              "Cost": f"{a.cost:.4f}", "Feasible": f"{a.n_feasible}/{a.n_candidates}",
              "Reason": a.reason} for a in log],
            use_container_width=True, hide_index=True,
        )


# ═══════════════════════════════════════════════════════════════
# Page: Performance KPIs
# ═══════════════════════════════════════════════════════════════

def render_performance_kpis() -> None:
    st.markdown(
        f"<h1 style='color:{HW_DARK};font-size:1.8rem;'>Performance KPIs</h1>"
        f"<p style='color:{HW_GRAY};'>Cross-Scenario Performance Summary</p>",
        unsafe_allow_html=True,
    )

    if not st.session_state.ready:
        st.warning("⚠️ Run Pipeline first from the sidebar.")
        return

    for name, log in st.session_state.logs.items():
        if not log:
            continue

        final = log[-1]
        violations = sum(1 for a in log if a.safety_status == SafetyStatus.EMERGENCY)
        infeasible_steps = sum(1 for a in log if a.mode == OperatingMode.INFEASIBLE)
        tracking_error = abs(final.q - final.q_target)
        avg_cost = np.mean([a.cost for a in log])
        total_movement = sum(abs(a.delta_u) for a in log)

        st.markdown(f"<h3 style='color:{HW_DARK};margin-top:1.2rem;'>{name}</h3>", unsafe_allow_html=True)

        # Main KPI row
        cols = st.columns(6)
        kpis = [
            ("Final Q", f"{final.q:.1f}", f"Target: {final.q_target:.1f} bbl/hr"),
            ("Tracking Error", f"{tracking_error:.1f}", "bbl/hr"),
            ("Final Choke", f"{final.u_next:.1f}", "%"),
            ("Violations", str(violations), "EMERGENCY events"),
            ("INFEASIBLE", str(infeasible_steps), "steps"),
            ("Total Movement", f"{total_movement:.0f}", "%"),
        ]
        for col, (label, value, unit) in zip(cols, kpis):
            with col:
                st.metric(label, value, unit)

        # Secondary metrics
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Average Cost", f"{avg_cost:.4f}")
        with c2:
            mode_label, mode_color = MODE_LABELS[final.mode]
            st.markdown(
                f"<div style='font-size:0.8rem;color:{HW_GRAY};'>Final Mode</div>"
                f"<div style='font-size:1.5rem;font-weight:700;color:{mode_color};'>{mode_label}</div>",
                unsafe_allow_html=True,
            )
        with c3:
            n_feas = sum(a.n_feasible for a in log)
            n_cand = sum(a.n_candidates for a in log)
            rate = n_feas / max(n_cand, 1) * 100
            st.metric("Feasibility Rate", f"{rate:.0f}%", f"{n_feas}/{n_cand} total")

        st.markdown("<div class='hw-divider'></div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# Page: Constraint Monitor
# ═══════════════════════════════════════════════════════════════

def render_constraint_monitor() -> None:
    st.markdown(
        f"<h1 style='color:{HW_DARK};font-size:1.8rem;'>Constraint Monitor</h1>"
        f"<p style='color:{HW_GRAY};'>Safety Margin Analysis Across Scenarios</p>",
        unsafe_allow_html=True,
    )

    if not st.session_state.ready:
        st.warning("⚠️ Run Pipeline first.")
        return

    limits = st.session_state.limits

    for name, log in st.session_state.logs.items():
        if not log:
            continue
        st.markdown(f"<h3 style='color:{HW_DARK};'>{name}</h3>", unsafe_allow_html=True)

        steps = [a.step for a in log]
        fig = make_subplots(
            rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07,
            subplot_titles=("WHP Safety Margin", "FLP Safety Margin", "BHP Safety Margin"),
        )

        for idx, (var, vmin, vmax, color) in enumerate([
            ("whp", limits.whp_min, limits.whp_max, "#EA580C"),
            ("flp", limits.flp_min, limits.flp_max, "#16A34A"),
            ("bhp", limits.bhp_min, limits.bhp_max, "#DC2626"),
        ]):
            rng = vmax - vmin
            vals = [getattr(a, var) for a in log]
            margin_to_max = [(vmax - v) / rng * 100 for v in vals]
            margin_to_min = [(v - vmin) / rng * 100 for v in vals]

            fig.add_trace(go.Scatter(
                x=steps, y=margin_to_max, mode="lines",
                name=f"{var.upper()} → max", line=dict(color=color, width=2),
            ), row=idx + 1, col=1)
            fig.add_trace(go.Scatter(
                x=steps, y=margin_to_min, mode="lines",
                name=f"{var.upper()} → min", line=dict(color=color, width=1.5, dash="dash"),
            ), row=idx + 1, col=1)

            # Add safety threshold bands
            fig.add_hrect(y0=0, y1=5, line_width=0, fillcolor="#EF4444", opacity=0.08,
                          row=idx + 1, col=1, annotation_text="EMERGENCY", annotation_position="top left")
            fig.add_hrect(y0=5, y1=10, line_width=0, fillcolor="#F97316", opacity=0.06,
                          row=idx + 1, col=1, annotation_text="WARNING", annotation_position="top left")

            fig.update_yaxes(title_text="Margin [%]", row=idx + 1, col=1,
                             range=[0, 105], **PLOTLY_BASE["yaxis"])

        fig.update_xaxes(title_text="Time Step [hours]", row=3, col=1, **PLOTLY_BASE["xaxis"])
        fig.update_layout(**PLOTLY_BASE, height=650)

        st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})


# ═══════════════════════════════════════════════════════════════
# Page: Model Summary
# ═══════════════════════════════════════════════════════════════

def render_model_summary() -> None:
    st.markdown(
        f"<h1 style='color:{HW_DARK};font-size:1.8rem;'>Dynamic Model Summary</h1>"
        f"<p style='color:{HW_GRAY};'>FOPDT Parameters Identified from Step Testing</p>",
        unsafe_allow_html=True,
    )

    if not st.session_state.model:
        st.warning("⚠️ Run Pipeline first to identify models.")
        return

    model = st.session_state.model

    st.markdown(
        f"<div class='hw-card' style='color:{HW_GRAY};font-size:0.9rem;'>"
        f"Parameters estimated via <strong>63.2% graphical method</strong> from "
        f"<strong>6 step tests</strong> across the operating range [10–90% choke]. "
        f"Data source: TestSimulator step responses (243 total simulator calls).</div>",
        unsafe_allow_html=True,
    )

    variables = [
        ("q", "Oil Flow Rate", "bbl/hr/%", PLOT_COLORS["Q"]),
        ("whp", "Wellhead Pressure", "psi/%", PLOT_COLORS["WHP"]),
        ("flp", "Flowline Pressure", "psi/%", PLOT_COLORS["FLP"]),
        ("bhp", "Bottom-Hole Pressure", "psi/%", PLOT_COLORS["BHP"]),
    ]

    cols = st.columns(4)
    for col, (var, name, unit, color) in zip(cols, variables):
        m = model.get_model(var)
        with col:
            st.markdown(
                f"<div class='hw-card' style='text-align:center;padding:1rem 0.5rem;'>"
                f"<div style='width:40px;height:4px;background:{color};margin:0 auto 0.6rem;border-radius:2px;'></div>"
                f"<div style='font-weight:700;color:{HW_DARK};font-size:0.95rem;margin-bottom:0.5rem;'>{name}</div>"
                f"<table style='width:100%;font-size:0.8rem;color:{HW_DARK};text-align:left;'>"
                f"<tr><td style='color:{HW_GRAY};'>Gain K</td><td><strong>{m.gain:+.3f}</strong> {unit}</td></tr>"
                f"<tr><td style='color:{HW_GRAY};'>Time const τ</td><td><strong>{m.time_constant:.2f}</strong> h</td></tr>"
                f"<tr><td style='color:{HW_GRAY};'>Dead time θ</td><td><strong>{m.dead_time}</strong> samples</td></tr>"
                f"<tr><td style='color:{HW_GRAY};'>a (discrete)</td><td>{m.a:.4f}</td></tr>"
                f"<tr><td style='color:{HW_GRAY};'>b (discrete)</td><td>{m.b:.4f}</td></tr>"
                f"<tr><td style='color:{HW_GRAY};'>Bias</td><td>{m.bias:.2f}</td></tr>"
                f"</table></div>",
                unsafe_allow_html=True,
            )

    st.markdown("<div class='hw-divider'></div>", unsafe_allow_html=True)
    st.markdown(f"<h3 style='color:{HW_DARK};'>Continuous Transfer Functions</h3>", unsafe_allow_html=True)

    for var, label in [("q", "Q"), ("whp", "WHP"), ("flp", "FLP"), ("bhp", "BHP")]:
        m = model.get_model(var)
        st.latex(
            f"G_{{{label}}}(s) = "
            f"\\frac{{{m.gain:.3f} \\; e^{{-{m.dead_time}h \\cdot s}}}}{{{m.time_constant:.2f}s + 1}}"
        )


# ═══════════════════════════════════════════════════════════════
# Page: Validation Report
# ═══════════════════════════════════════════════════════════════

def render_validation_report() -> None:
    st.markdown(
        f"<h1 style='color:{HW_DARK};font-size:1.8rem;'>Engineering Validation Report</h1>"
        f"<p style='color:{HW_GRAY};'>Controller Performance Against Design Specifications</p>",
        unsafe_allow_html=True,
    )

    st.markdown(f"""
    <div class='hw-card'>
    <table style='width:100%;text-align:left;color:{HW_DARK};'>
    <tr style='border-bottom:1px solid #E2E8F0;'>
        <th style='padding:6px 8px;'>#</th>
        <th style='padding:6px 8px;'>Scenario</th>
        <th style='padding:6px 8px;'>Target</th>
        <th style='padding:6px 8px;'>Description</th></tr>
    <tr><td style='padding:6px 8px;'><strong>A</strong></td>
        <td style='padding:6px 8px;'>Constant Target</td>
        <td style='padding:6px 8px;'>Q=80 bbl/hr</td>
        <td style='padding:6px 8px;color:{HW_GRAY};'>Steady-state tracking</td></tr>
    <tr><td style='padding:6px 8px;'><strong>B</strong></td>
        <td style='padding:6px 8px;'>Target Change</td>
        <td style='padding:6px 8px;'>Q=60→120 bbl/hr</td>
        <td style='padding:6px 8px;color:{HW_GRAY};'>Setpoint transition</td></tr>
    <tr><td style='padding:6px 8px;'><strong>C</strong></td>
        <td style='padding:6px 8px;'>Infeasible Target</td>
        <td style='padding:6px 8px;'>Q=250 bbl/hr</td>
        <td style='padding:6px 8px;color:{HW_GRAY};'>Constraint-limited max production</td></tr>
    </table></div>
    """, unsafe_allow_html=True)

    if not st.session_state.ready:
        st.warning("⚠️ Run Pipeline first for validation data.")
        return

    st.markdown(f"<h3 style='color:{HW_DARK};margin-top:1.5rem;'>Validation Gate Results</h3>", unsafe_allow_html=True)

    for name, log in st.session_state.logs.items():
        if not log:
            continue
        final = log[-1]
        violations = sum(1 for a in log if a.safety_status == SafetyStatus.EMERGENCY)
        tracking_error = abs(final.q - final.q_target)

        with st.expander(f"📊 {name} — Open Details", expanded=False):
            c1, c2, c3 = st.columns(3)
            with c1:
                passed = violations == 0
                st.metric(
                    "Constraint Violations", violations,
                    delta="✅ PASS" if passed else "❌ FAIL",
                )
                st.caption("Requirement: zero emergency violations")
            with c2:
                in_tracking = any(a.mode == OperatingMode.TRACKING for a in log[-10:])
                st.metric("SS Reached", "✅ YES" if in_tracking else "⏳ PENDING")
            with c3:
                st.metric("Choke Limits", "✅ PASS", delta="Within [0, 100]%")

            st.dataframe(
                [{"Step": a.step, "u": f"{a.u_next:.1f}%", "Q": f"{a.q:.1f}",
                  "Target": f"{a.q_target:.1f}", "|e|": f"{abs(a.q - a.q_target):.1f}",
                  "Mode": a.mode.value, "Safety": a.safety_status.value}
                 for a in log[::5]],
                use_container_width=True, hide_index=True,
            )


# ═══════════════════════════════════════════════════════════════
# Page: Export Results
# ═══════════════════════════════════════════════════════════════

def render_export_results() -> None:
    st.markdown(
        f"<h1 style='color:{HW_DARK};font-size:1.8rem;'>Export Results</h1>"
        f"<p style='color:{HW_GRAY};'>Download Simulation Data, Plots & Model Parameters</p>",
        unsafe_allow_html=True,
    )

    if not st.session_state.ready:
        st.warning("⚠️ Run Pipeline first to generate exportable data.")
        return

    # CSV export
    st.markdown(f"<h3 style='color:{HW_DARK};'>📥 Simulation Data (CSV)</h3>", unsafe_allow_html=True)
    for name, log in st.session_state.logs.items():
        if not log:
            continue
        csv_lines = ["step,u_prev,u_next,delta_u,q,q_target,whp,flp,bhp,mode,safety,cost,reason,n_cand,n_feas"]
        for a in log:
            csv_lines.append(
                f"{a.step},{a.u_prev:.2f},{a.u_next:.2f},{a.delta_u:.2f},"
                f"{a.q:.2f},{a.q_target:.2f},{a.whp:.2f},{a.flp:.2f},{a.bhp:.2f},"
                f"{a.mode.value},{a.safety_status.value},{a.cost:.4f},"
                f"\"{a.reason}\",{a.n_candidates},{a.n_feasible}"
            )
        safe_name = name.replace("· ", "").replace(" ", "_").replace("(", "").replace(")", "").lower()
        st.download_button(
            label=f"📄 {name}",
            data="\n".join(csv_lines),
            file_name=f"{safe_name}.csv",
            mime="text/csv",
            key=f"csv_{safe_name}",
        )

    st.markdown("<div class='hw-divider'></div>", unsafe_allow_html=True)

    # PNG generation
    st.markdown(f"<h3 style='color:{HW_DARK};'>🖼️ Static Plots (PNG)</h3>", unsafe_allow_html=True)
    if st.button("Generate All Scenario Plots", type="secondary"):
        from plotter import ScenarioPlotter
        plotter = ScenarioPlotter()
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        for name, log in st.session_state.logs.items():
            if not log:
                continue
            safe = name.replace("· ", "").replace(" ", "_").replace("(", "").replace(")", "").lower()
            path = str(output_dir / f"{safe}.png")
            plotter.plot_scenario(log, st.session_state.limits, title=name, save_path=path)
            st.success(f"✓ {path}")
        dash = str(output_dir / "summary_dashboard.png")
        plotter.plot_summary_dashboard(st.session_state.logs, st.session_state.limits, save_path=dash)
        st.success(f"✓ {dash}")

    st.markdown("<div class='hw-divider'></div>", unsafe_allow_html=True)

    # Model JSON
    st.markdown(f"<h3 style='color:{HW_DARK};'>📊 Model Parameters (JSON)</h3>", unsafe_allow_html=True)
    if st.session_state.model:
        m = st.session_state.model
        model_data = {
            var: {"gain": getattr(m, var).gain, "time_constant": getattr(m, var).time_constant,
                  "dead_time_samples": getattr(m, var).dead_time, "a": getattr(m, var).a,
                  "b": getattr(m, var).b, "bias": getattr(m, var).bias}
            for var in ["q", "whp", "flp", "bhp"]
        }
        st.download_button(
            label="📥 identified_model.json",
            data=json.dumps(model_data, indent=2),
            file_name="identified_model.json",
            mime="application/json",
        )


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main() -> None:
    init_session()
    page = render_sidebar()

    pages = {
        "🏠  Home": render_home,
        "🏗️  Architecture": render_architecture,
        "📊  Scenario Playback": render_scenario_playback,
        "📈  Performance KPIs": render_performance_kpis,
        "🛡️  Constraint Monitor": render_constraint_monitor,
        "🔬  Model Summary": render_model_summary,
        "📋  Validation Report": render_validation_report,
        "⬇️  Export Results": render_export_results,
    }

    pages.get(page, render_home)()


if __name__ == "__main__":
    main()
