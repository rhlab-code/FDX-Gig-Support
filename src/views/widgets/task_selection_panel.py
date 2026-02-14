"""
Task Selection Panel

Panel for selecting tasks to execute on the device.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QGroupBox, QCheckBox
)
from PyQt6.QtCore import pyqtSignal
from typing import List, Dict


class TaskSelectionPanel(QGroupBox):
    """Panel for task selection with checkboxes."""

    # Signal emitted when task selection changes
    selection_changed = pyqtSignal(list)  # Emits list of selected task names

    # Available tasks
    AVAILABLE_TASKS = [
        'get_wbfft',
        'get_eq',
        'get_sf',
        'get_ec',
        'get_us_psd',
        'reset'
    ]

    # Task display names
    TASK_LABELS = {
        'get_wbfft': 'WBFFT',
        'get_eq': 'Equalizer',
        'get_sf': 'Shape Filter',
        'get_ec': 'Echo Canceller',
        'get_us_psd': 'Upstream Power Spectral Density',
        'reset': 'Reset'
    }

    # Task descriptions for tooltips
    TASK_DESCRIPTIONS = {
        'get_wbfft': 'Wideband FFT power spectrum measurement',
        'get_eq': 'Upstream/Downstream equalizer coefficients',
        'get_sf': 'Downstream shaping filter coefficients',
        'get_ec': 'Echo canceller coefficients and PSD metrics',
        'get_us_psd': 'Upstream power spectral density analysis',
        'reset': 'Reset the device'
    }

    def __init__(self, parent=None):
        """Initialize the task selection panel."""
        super().__init__("Task Selection", parent)
        self.task_checkboxes: Dict[str, QCheckBox] = {}
        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI components."""
        layout = QVBoxLayout()

        # Create grid layout for checkboxes
        grid = QGridLayout()
        grid.setSpacing(8)

        # Number of columns for task layout
        num_cols = 2

        # Create checkboxes for each task
        for i, task in enumerate(self.AVAILABLE_TASKS):
            row = i // num_cols
            col = i % num_cols

            checkbox = QCheckBox(self.TASK_LABELS.get(task, task))
            checkbox.setToolTip(self.TASK_DESCRIPTIONS.get(task, ""))
            checkbox.stateChanged.connect(self._on_selection_changed)

            # Special styling for reset task
            if task == 'reset':
                checkbox.setStyleSheet("QCheckBox { color: #ff7112; font-weight: bold; }")

            grid.addWidget(checkbox, row, col)
            self.task_checkboxes[task] = checkbox

        layout.addLayout(grid)
        self.setLayout(layout)

    def _on_selection_changed(self):
        """Handle checkbox selection change."""
        selected = self.get_selected_tasks()
        self.selection_changed.emit(selected)

    def get_selected_tasks(self) -> List[str]:
        """
        Get list of selected tasks.

        Returns:
            List of task names
        """
        return [task for task, checkbox in self.task_checkboxes.items()
                if checkbox.isChecked()]

    def select_all(self, exclude_reset: bool = True):
        """
        Select all tasks.

        Args:
            exclude_reset: If True, don't select the reset task
        """
        for task, checkbox in self.task_checkboxes.items():
            if exclude_reset and task == 'reset':
                checkbox.setChecked(False)
            else:
                checkbox.setChecked(True)

    def deselect_all(self):
        """Deselect all tasks."""
        for checkbox in self.task_checkboxes.values():
            checkbox.setChecked(False)

    def set_task_enabled(self, task: str, enabled: bool):
        """
        Enable or disable a specific task.

        Args:
            task: Task name
            enabled: True to enable, False to disable
        """
        if task in self.task_checkboxes:
            self.task_checkboxes[task].setEnabled(enabled)

    def set_all_enabled(self, enabled: bool):
        """
        Enable or disable all tasks.

        Args:
            enabled: True to enable, False to disable
        """
        for checkbox in self.task_checkboxes.values():
            checkbox.setEnabled(enabled)
