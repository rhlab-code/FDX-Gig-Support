"""
Main Controller

Orchestrates all controllers and coordinates application logic.
"""

import sys
import os
import json
import importlib
import subprocess
import re
import ipaddress

from PyQt6.QtWidgets import QMessageBox

# Add lib directory to path
lib_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'lib')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

from ..models import (
    ApplicationState, AmplifierDevice, Task, TaskSequence,
    ConnectionState, TaskStatus
)
from ..workers.task_worker import TaskWorker


class MainController:
    """Main application controller."""

    def __init__(self, main_window, app_state):
        """
        Initialize the main controller.

        Args:
            main_window: MainWindow instance
            app_state: ApplicationState instance
        """
        self.main_window = main_window
        self.app_state = app_state
        self.current_worker = None

        # Load settings and constants
        self._load_settings()

        # Connect signals
        self._connect_signals()

    def _load_settings(self):
        """Load settings and constants from files."""
        try:
            # Load amp_settings.json
            settings_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                '.', 'amp_settings.json'
            )
            with open(settings_path, 'r') as f:
                self.settings = json.load(f)

            # Load constants
            from commands import generate_command_sequences
            import constants

            self.constants = constants
            self.command_sequences = generate_command_sequences(self.settings, constants)

        except Exception as e:
            print(f"Error loading settings: {e}")
            self.settings = {}
            self.command_sequences = {}
            self.constants = None

    def _connect_signals(self):
        """Connect UI signals to controller methods."""
        # Control panel signals
        self.main_window.control_panel.submit_clicked.connect(self.on_submit)
        self.main_window.control_panel.select_all_clicked.connect(self.on_select_all)
        self.main_window.control_panel.clear_clicked.connect(self.on_clear)

        # Application state signals
        self.app_state.report_generated.connect(self.on_report_generated)

    def _is_mac_address(self, address: str) -> bool:
        """Check if address is a MAC address."""
        mac_pattern = r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$'
        return re.match(mac_pattern, address) is not None

    def _is_ipv6_address(self, address: str) -> bool:
        """Check if address is an IPv6 address."""
        try:
            ipaddress.IPv6Address(address)
            return True
        except ValueError:
            return False

    def _get_ipv6_from_mac(self, mac_address: str, image: str) -> tuple:
        """
        Call amp_info.py to get IPv6 address from MAC.

        Args:
            mac_address: MAC address
            image: Image type (CC, CS, etc.)

        Returns:
            Tuple of (ipv6_address, parsed_data) or (None, None) on failure
        """
        try:
            # Path to amp_info.py
            amp_info_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                'amp_info.py'
            )

            # Run amp_info.py
            cmd = [sys.executable, amp_info_path, 'PROD', 'CPE', mac_address]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )

            if proc.returncode != 0:
                return None, None

            # Parse output
            raw_out = proc.stdout.strip()
            if not raw_out:
                return None, None

            # Try to parse as JSON
            try:
                parsed = json.loads(raw_out)
            except:
                try:
                    import ast
                    parsed = ast.literal_eval(raw_out)
                except:
                    return None, None

            # Extract IPv6 address
            if isinstance(parsed, dict):
                ipv6 = parsed.get('cpeIpv6Addr')
                if ipv6:
                    return ipv6, parsed

            return None, None

        except Exception as e:
            print(f"Error getting IPv6 from MAC: {e}")
            return None, None

    def on_submit(self):
        """Handle submit button click."""
        # Get input values
        image = self.main_window.device_input_panel.get_image()
        address = self.main_window.device_input_panel.get_address()
        selected_tasks = self.main_window.task_selection_panel.get_selected_tasks()

        # Validate
        if not address:
            QMessageBox.warning(
                self.main_window,
                "Validation Error",
                "Please enter a MAC or IPv6 address."
            )
            return

        if not self.main_window.device_input_panel.is_valid():
            QMessageBox.warning(
                self.main_window,
                "Validation Error",
                "Address must be a valid MAC or IPv6 address."
            )
            return

        if not selected_tasks:
            QMessageBox.warning(
                self.main_window,
                "Validation Error",
                "Please select at least one task."
            )
            return

        # Disable controls during execution
        self.main_window.control_panel.set_all_enabled(False)
        self.main_window.task_selection_panel.set_all_enabled(False)

        # Show status panel when execution starts
        self.main_window.show_status_panel()

        # Determine MAC and IPv6
        mac_address = address
        ipv6_address = address

        # If address is MAC, lookup IPv6 using amp_info.py
        if self._is_mac_address(address):
            self.main_window.log_panel.append_log(
                f"Looking up IPv6 for MAC: {address}",
                "INFO"
            )
            self.main_window.update_connection_status("Looking up IPv6...")

            ipv6, parsed_data = self._get_ipv6_from_mac(address, image)

            if ipv6:
                ipv6_address = ipv6
                self.main_window.log_panel.append_log(
                    f"Found IPv6: {ipv6}",
                    "INFO"
                )

                # Extract additional device info if available
                if parsed_data:
                    fn_name = parsed_data.get('fnName', '')
                    if fn_name:
                        self.main_window.log_panel.append_log(
                            f"Device: {fn_name}",
                            "INFO"
                        )
            else:
                self.main_window.log_panel.append_log(
                    "Failed to lookup IPv6 address",
                    "ERROR"
                )
                QMessageBox.warning(
                    self.main_window,
                    "Lookup Failed",
                    f"Could not find IPv6 address for MAC {address}.\nPlease verify the MAC address and try again."
                )
                # Re-enable controls
                self.main_window.control_panel.set_all_enabled(True)
                self.main_window.task_selection_panel.set_all_enabled(True)
                return

        elif self._is_ipv6_address(address):
            # IPv6 provided directly, use it
            ipv6_address = address
            # We don't have MAC, so use IPv6 as identifier
            mac_address = address
        else:
            # Should not happen due to validation, but handle it
            QMessageBox.warning(
                self.main_window,
                "Invalid Address",
                "Address must be a valid MAC or IPv6 address."
            )
            self.main_window.control_panel.set_all_enabled(True)
            self.main_window.task_selection_panel.set_all_enabled(True)
            return

        # Create device with proper MAC and IPv6
        device = AmplifierDevice(mac_address=mac_address, ipv6_address=ipv6_address, image=image)
        self.app_state.add_device(device)

        # Create task sequence
        task_sequence = TaskSequence(mac_address)
        for task_name in selected_tasks:
            task = Task(task_name)
            task_sequence.add_task(task)
        self.app_state.add_task_sequence(mac_address, task_sequence)

        # Add device and tasks to status panel
        self.main_window.status_panel.add_device(mac_address, ipv6_address)
        for task_name in selected_tasks:
            display_name = self.main_window.task_selection_panel.TASK_LABELS.get(
                task_name, task_name
            )
            self.main_window.status_panel.add_task(mac_address, task_name, display_name)

        # Log start
        self.main_window.log_panel.append_log(
            f"Starting execution for device {mac_address}",
            "INFO"
        )
        if mac_address != ipv6_address:
            self.main_window.log_panel.append_log(
                f"IPv6: {ipv6_address}",
                "INFO"
            )
        self.main_window.log_panel.append_log(
            f"Tasks: {', '.join(selected_tasks)}",
            "INFO"
        )

        # Create and start worker
        output_dir = "output"
        self.current_worker = TaskWorker(
            device=device,
            tasks=selected_tasks,
            settings=self.settings,
            constants=self.constants,
            command_sequences=self.command_sequences,
            output_dir=output_dir
        )

        # Connect worker signals
        self.current_worker.task_started.connect(self.on_task_started)
        self.current_worker.task_completed.connect(self.on_task_completed)
        self.current_worker.task_failed.connect(self.on_task_failed)
        self.current_worker.all_completed.connect(self.on_all_completed)

        # Start worker
        self.current_worker.start()

        # Update status
        self.main_window.update_connection_status("Connecting...")
        self.main_window.update_task_progress("Executing tasks...")

    def on_task_started(self, mac: str, task_name: str):
        """Handle task started signal."""
        self.main_window.status_panel.update_task_status(mac, task_name, "running")
        self.main_window.log_panel.append_log(f"Started task: {task_name}", "INFO")
        self.app_state.mark_task_started(mac, task_name)

    def on_task_completed(self, mac: str, task_name: str, result: dict):
        """Handle task completed signal."""
        self.main_window.status_panel.update_task_status(mac, task_name, "success")
        self.main_window.log_panel.append_log(f"Completed task: {task_name}", "INFO")

        # Check for report files in result
        if 'output_file' in result or 'report_file' in result:
            report_file = result.get('report_file')
            if report_file and os.path.exists(report_file):
                self.app_state.add_report(mac, task_name, report_file)

    def on_task_failed(self, mac: str, task_name: str, error: str):
        """Handle task failed signal."""
        self.main_window.status_panel.update_task_status(mac, task_name, "failed")
        self.main_window.log_panel.append_log(
            f"Failed task {task_name}: {error}",
            "ERROR"
        )
        self.app_state.mark_task_failed(mac, task_name, error)

    def on_all_completed(self, mac: str, results: dict):
        """Handle all tasks completed signal."""
        self.main_window.log_panel.append_log("All tasks completed", "INFO")
        self.main_window.update_connection_status("Completed")
        self.main_window.update_task_progress("Done")

        # Re-enable controls
        self.main_window.control_panel.set_all_enabled(True)
        self.main_window.task_selection_panel.set_all_enabled(True)

        # Update progress bar
        self.main_window.status_panel.update_progress(100)

    def on_report_generated(self, mac: str, report_type: str, file_path: str):
        """Handle report generated signal."""
        self.main_window.log_panel.append_log(
            f"Generated report: {os.path.basename(file_path)}",
            "INFO"
        )
        # Load report into graph panel
        self.main_window.graph_panel.load_report(file_path)

    def on_select_all(self):
        """Handle select all button click."""
        self.main_window.task_selection_panel.select_all(exclude_reset=True)

    def on_clear(self):
        """Handle clear button click."""
        self.main_window.device_input_panel.clear()
        self.main_window.task_selection_panel.deselect_all()
        self.main_window.status_panel.clear()
        # Don't clear log console or graph panel to preserve history
