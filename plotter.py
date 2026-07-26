import logging
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

from models import ControlAction, StepTestResult, SafetyStatus, OperatingMode
from config import ConstraintLimits

logger = logging.getLogger(__name__)

class ScenarioPlotter:
    """
    Professional plotting module using matplotlib for all deliverables.
    Generates multi-panel figures for scenario results, step tests, and model validation.
    """
    def __init__(self, style: str = 'seaborn-v0_8-darkgrid'):
        """
        Initializes the plotter, setting style and color palette.
        """
        self.style = style if style in plt.style.available else 'default'
        self.colors = {
            'Q': '#2196F3',       # blue
            'WHP': '#FF9800',     # orange
            'FLP': '#4CAF50',     # green
            'BHP': '#F44336',     # red
            'Choke': '#9C27B0',   # purple
            'Target': '#E91E63',  # pink
            'Constraints': '#757575', # gray
        }

    def plot_scenario(self, log: list[ControlAction], limits: ConstraintLimits, title: str = '', save_path: str | None = None) -> None:
        """
        Plots a multi-panel figure summarizing a control scenario.
        """
        if not log:
            logger.warning("Empty log provided to plot_scenario. Skipping.")
            return

        steps = [a.step for a in log]
        u_next = [a.u_next for a in log]
        q = [a.q for a in log]
        q_target = [a.q_target for a in log]
        whp = [a.whp for a in log]
        flp = [a.flp for a in log]
        bhp = [a.bhp for a in log]
        modes = [a.mode for a in log]
        safety = [a.safety_status for a in log]

        with plt.style.context(self.style):
            fig, axs = plt.subplots(4, 1, figsize=(10, 12), sharex=True)
            if title:
                fig.suptitle(title, fontsize=16)

            # Panel 1: Choke Position
            axs[0].step(steps, u_next, where='post', color=self.colors['Choke'], linestyle='-', linewidth=2)
            axs[0].set_ylabel('Choke Position [%]')
            axs[0].set_ylim(0, 100)
            axs[0].grid(True)

            # Panel 2: Oil Flow Rate
            axs[1].plot(steps, q, color=self.colors['Q'], label='Q')
            axs[1].plot(steps, q_target, color=self.colors['Target'], linestyle='--', label='Target')
            axs[1].fill_between(steps, q, q_target, color=self.colors['Target'], alpha=0.1)
            axs[1].set_ylabel('Oil Flow Rate [bbl/hr]')
            axs[1].legend(loc='upper right')
            axs[1].grid(True)

            # Panel 3: Pressures
            axs[2].plot(steps, whp, color=self.colors['WHP'], label='WHP')
            axs[2].plot(steps, flp, color=self.colors['FLP'], label='FLP')
            axs[2].plot(steps, bhp, color=self.colors['BHP'], label='BHP')

            # Add constraints
            axs[2].axhline(limits.whp_max, color=self.colors['Constraints'], linestyle='--', alpha=0.5)
            axs[2].axhline(limits.flp_min, color=self.colors['Constraints'], linestyle='--', alpha=0.5)
            axs[2].axhline(limits.flp_max, color=self.colors['Constraints'], linestyle='--', alpha=0.5)
            axs[2].axhline(limits.bhp_min, color=self.colors['Constraints'], linestyle='--', alpha=0.5)
            axs[2].axhline(limits.bhp_max, color=self.colors['Constraints'], linestyle='--', alpha=0.5)

            axs[2].set_ylabel('Pressure [psi]')
            axs[2].legend(loc='upper right')
            axs[2].grid(True)

            # Panel 4: Mode & Safety
            mode_colors = {OperatingMode.STARTUP: 'yellow', OperatingMode.TRACKING: 'green', OperatingMode.INFEASIBLE: 'red'}
            safety_colors = {SafetyStatus.NORMAL: 'green', SafetyStatus.CAUTION: 'yellow', SafetyStatus.WARNING: 'orange', SafetyStatus.EMERGENCY: 'red'}

            for i in range(len(steps) - 1):
                axs[3].axvspan(steps[i], steps[i+1], color=mode_colors[modes[i]], alpha=0.3)

            axs[3].scatter(steps, [1]*len(steps), c=[safety_colors[s] for s in safety], marker='o')
            axs[3].set_yticks([])
            axs[3].set_ylabel('Mode & Safety')
            axs[3].set_xlabel('Time Step [hours]')

            plt.tight_layout()
            if save_path:
                plt.savefig(save_path, dpi=200)
                logger.info(f"Saved plot to {save_path}")
            else:
                plt.show()
            plt.close(fig)

    def plot_step_test(self, result: StepTestResult, title: str = '', save_path: str | None = None) -> None:
        """
        Plots the result of a step test experiment.
        """
        with plt.style.context(self.style):
            fig, axs = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
            if title:
                fig.suptitle(title, fontsize=14)

            # Top: Input (Choke)
            u_traj = [result.u_start if t < result.duration/2 else result.u_end for t in result.time]
            axs[0].step(result.time, u_traj, where='post', color=self.colors['Choke'], linewidth=2)
            axs[0].set_ylabel('Choke Position [%]')
            axs[0].grid(True)

            # Bottom: Outputs
            axs[1].plot(result.time, result.q_response, color=self.colors['Q'], label='Q')
            axs[1].plot(result.time, result.whp_response, color=self.colors['WHP'], label='WHP')
            axs[1].plot(result.time, result.flp_response, color=self.colors['FLP'], label='FLP')
            axs[1].plot(result.time, result.bhp_response, color=self.colors['BHP'], label='BHP')
            axs[1].set_ylabel('Process Outputs')
            axs[1].set_xlabel('Time')
            axs[1].legend(loc='best')
            axs[1].grid(True)

            plt.tight_layout()
            if save_path:
                plt.savefig(save_path, dpi=200)
            else:
                plt.show()
            plt.close(fig)

    def plot_model_validation(self, actual: list[float], predicted: list[float], variable: str, title: str = '', save_path: str | None = None) -> None:
        """
        Plots validation of predicted outputs against actual measurements.
        """
        if len(actual) != len(predicted) or not actual:
            return

        steps = list(range(len(actual)))
        with plt.style.context(self.style):
            fig, axs = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
            if title:
                fig.suptitle(title, fontsize=14)

            axs[0].plot(steps, actual, label='Actual', marker='o')
            axs[0].plot(steps, predicted, label='Predicted', linestyle='--')
            axs[0].set_ylabel(variable)
            axs[0].legend()
            axs[0].grid(True)

            residuals = [a - p for a, p in zip(actual, predicted)]
            axs[1].plot(steps, residuals, color='gray')
            axs[1].axhline(0, color='black', linestyle='--')
            axs[1].set_ylabel('Residual')
            axs[1].set_xlabel('Time Step')
            axs[1].grid(True)

            rmse = np.sqrt(np.mean(np.square(residuals)))
            axs[1].text(0.05, 0.9, f'RMSE: {rmse:.2f}', transform=axs[1].transAxes, bbox=dict(facecolor='white', alpha=0.5))

            plt.tight_layout()
            if save_path:
                plt.savefig(save_path, dpi=200)
            else:
                plt.show()
            plt.close(fig)

    def plot_summary_dashboard(self, logs: dict[str, list[ControlAction]], limits: ConstraintLimits, save_path: str | None = None) -> None:
        """
        Creates a large dashboard figure summarizing multiple scenarios.
        """
        if not logs:
            return

        scenario_names = list(logs.keys())
        n_cols = len(scenario_names)
        
        with plt.style.context(self.style):
            fig, axs = plt.subplots(3, n_cols, figsize=(5 * n_cols, 10), sharey='row', sharex=True)
            fig.suptitle('Autonomous Choke Controller — All Scenarios', fontsize=18)
            
            if n_cols == 1:
                axs = np.expand_dims(axs, axis=1)

            for col, name in enumerate(scenario_names):
                log = logs[name]
                steps = [a.step for a in log]
                
                axs[0, col].set_title(name)
                
                # Row 0: Choke
                axs[0, col].step(steps, [a.u_next for a in log], where='post', color=self.colors['Choke'])
                axs[0, col].grid(True)
                if col == 0: axs[0, col].set_ylabel('Choke [%]')
                
                # Row 1: Q
                axs[1, col].plot(steps, [a.q for a in log], color=self.colors['Q'])
                axs[1, col].plot(steps, [a.q_target for a in log], color=self.colors['Target'], linestyle='--')
                axs[1, col].grid(True)
                if col == 0: axs[1, col].set_ylabel('Q [bbl/hr]')
                
                # Row 2: Pressures
                axs[2, col].plot(steps, [a.whp for a in log], color=self.colors['WHP'])
                axs[2, col].plot(steps, [a.flp for a in log], color=self.colors['FLP'])
                axs[2, col].plot(steps, [a.bhp for a in log], color=self.colors['BHP'])
                axs[2, col].axhline(limits.whp_max, color=self.colors['Constraints'], linestyle='--', alpha=0.5)
                axs[2, col].axhline(limits.bhp_min, color=self.colors['Constraints'], linestyle='--', alpha=0.5)
                axs[2, col].grid(True)
                axs[2, col].set_xlabel('Time Step')
                if col == 0: axs[2, col].set_ylabel('Pressures [psi]')

            plt.tight_layout()
            if save_path:
                plt.savefig(save_path, dpi=200)
            else:
                plt.show()
            plt.close(fig)
