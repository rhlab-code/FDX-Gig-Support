"""
Execution Status Panel

Panel showing hierarchical task execution status with tree view.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem,
    QProgressBar, QLabel, QGroupBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor


class ExecutionStatusPanel(QGroupBox):
    """Panel displaying task execution status in a tree view."""

    def __init__(self, parent=None):
        """Initialize the execution status panel."""
        super().__init__("Execution Status", parent)
        self.device_items = {}  # MAC address → QTreeWidgetItem
        self.task_items = {}  # (MAC, task_name) → QTreeWidgetItem
        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI components."""
        layout = QVBoxLayout()

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% Complete")
        layout.addWidget(self.progress_bar)

        # Tree widget
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Task", "Status"])
        self.tree.setColumnWidth(0, 250)
        self.tree.setAlternatingRowColors(True)
        layout.addWidget(self.tree)

        self.setLayout(layout)

    def add_device(self, mac_address: str, ipv6_address: str = ""):
        """
        Add a device to the status tree.

        Args:
            mac_address: MAC address of the device
            ipv6_address: Optional IPv6 address
        """
        if mac_address in self.device_items:
            return

        device_item = QTreeWidgetItem(self.tree)
        device_text = f"{mac_address}"
        if ipv6_address:
            device_text += f" ({ipv6_address})"
        device_item.setText(0, device_text)
        device_item.setText(1, "Ready")
        device_item.setExpanded(True)

        self.device_items[mac_address] = device_item

    def add_task(self, mac_address: str, task_name: str, display_name: str = None):
        """
        Add a task under a device.

        Args:
            mac_address: MAC address of the device
            task_name: Task identifier
            display_name: Optional display name for the task
        """
        if mac_address not in self.device_items:
            self.add_device(mac_address)

        device_item = self.device_items[mac_address]
        task_item = QTreeWidgetItem(device_item)
        task_item.setText(0, display_name or task_name)
        task_item.setText(1, "Pending")
        self._set_status_color(task_item, "pending")

        self.task_items[(mac_address, task_name)] = task_item

    def update_task_status(self, mac_address: str, task_name: str, status: str):
        """
        Update the status of a task.

        Args:
            mac_address: MAC address of the device
            task_name: Task identifier
            status: Status string (pending, running, success, failed, etc.)
        """
        key = (mac_address, task_name)
        if key not in self.task_items:
            return

        task_item = self.task_items[key]
        status_text = self._format_status(status)
        task_item.setText(1, status_text)
        self._set_status_color(task_item, status.lower())

        # Update device status
        if mac_address in self.device_items:
            device_item = self.device_items[mac_address]
            if status.lower() in ('running', 'in_progress'):
                device_item.setText(1, "Working...")
                self._set_status_color(device_item, "running")

    def update_progress(self, percentage: int):
        """
        Update the progress bar.

        Args:
            percentage: Progress percentage (0-100)
        """
        self.progress_bar.setValue(percentage)

    def _format_status(self, status: str) -> str:
        """
        Format status text with icon.

        Args:
            status: Raw status string

        Returns:
            Formatted status string
        """
        status_lower = status.lower()
        if status_lower in ('success', 'completed', 'pass'):
            return "✓ Success"
        elif status_lower in ('failed', 'error'):
            return "✗ Failed"
        elif status_lower in ('running', 'in_progress'):
            return "● Running"
        elif status_lower in ('waiting', 'pending'):
            return "○ Waiting"
        elif status_lower == 'skip':
            return "⊘ Skipped"
        elif status_lower == 'stop':
            return "■ Stopped"
        else:
            return status

    def _set_status_color(self, item: QTreeWidgetItem, status: str):
        """
        Set the color for a status item.

        Args:
            item: Tree widget item
            status: Status string
        """
        status_lower = status.lower()
        if status_lower in ('success', 'completed', 'pass'):
            color = QColor("#05ac3f")  # Green
        elif status_lower in ('failed', 'error', 'stop'):
            color = QColor("#ef1541")  # Red
        elif status_lower in ('running', 'in_progress'):
            color = QColor("#ff7112")  # Orange
        elif status_lower in ('waiting', 'pending'):
            color = QColor("#707070")  # Gray
        elif status_lower == 'skip':
            color = QColor("#cccccc")  # Light gray
        else:
            color = QColor("#1a1a1a")  # Dark gray

        item.setForeground(1, color)

    def clear(self):
        """Clear all status information."""
        self.tree.clear()
        self.device_items.clear()
        self.task_items.clear()
        self.progress_bar.setValue(0)
