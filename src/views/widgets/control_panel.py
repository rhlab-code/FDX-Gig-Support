"""
Control Panel

Panel with action buttons (Submit, Select All, Clear).
"""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton
from PyQt6.QtCore import pyqtSignal


class ControlPanel(QWidget):
    """Panel with control buttons."""

    # Signals
    submit_clicked = pyqtSignal()
    select_all_clicked = pyqtSignal()
    clear_clicked = pyqtSignal()

    def __init__(self, parent=None):
        """Initialize the control panel."""
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI components."""
        layout = QHBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 0)

        # Submit button (green)
        self.submit_btn = QPushButton("Submit")
        self.submit_btn.setObjectName("submitButton")
        self.submit_btn.setMinimumHeight(26)
        self.submit_btn.setToolTip("Execute selected tasks (Ctrl+Return)")
        self.submit_btn.clicked.connect(self.submit_clicked.emit)

        # Select All button (blue)
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.setObjectName("selectAllButton")
        self.select_all_btn.setMinimumHeight(26)
        self.select_all_btn.setToolTip("Select all tasks except reset")
        self.select_all_btn.clicked.connect(self.select_all_clicked.emit)

        # Clear button (orange)
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setObjectName("clearButton")
        self.clear_btn.setMinimumHeight(26)
        self.clear_btn.setToolTip("Clear all inputs and selections (Ctrl+R)")
        self.clear_btn.clicked.connect(self.clear_clicked.emit)

        # Add buttons to layout
        layout.addWidget(self.submit_btn, 2)
        layout.addWidget(self.select_all_btn, 1)
        layout.addWidget(self.clear_btn, 1)

        self.setLayout(layout)

    def set_submit_enabled(self, enabled: bool):
        """
        Enable or disable the submit button.

        Args:
            enabled: True to enable, False to disable
        """
        self.submit_btn.setEnabled(enabled)

    def set_all_enabled(self, enabled: bool):
        """
        Enable or disable all buttons.

        Args:
            enabled: True to enable, False to disable
        """
        self.submit_btn.setEnabled(enabled)
        self.select_all_btn.setEnabled(enabled)
        self.clear_btn.setEnabled(enabled)
