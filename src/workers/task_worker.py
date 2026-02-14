"""
Task Worker

QThread worker for executing SSH tasks in the background.
"""

import sys
import os
from PyQt6.QtCore import QThread, pyqtSignal

# Add lib directory to path for imports
lib_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'lib')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)


class TaskWorker(QThread):
    """Worker thread for executing SSH tasks."""

    # Signals
    task_started = pyqtSignal(str, str)  # (MAC, task_name)
    task_progress = pyqtSignal(str, str, int)  # (MAC, task_name, progress%)
    task_completed = pyqtSignal(str, str, dict)  # (MAC, task_name, result)
    task_failed = pyqtSignal(str, str, str)  # (MAC, task_name, error)
    all_completed = pyqtSignal(str, dict)  # (MAC, all_results)

    def __init__(self, device, tasks, settings, constants, command_sequences, output_dir):
        """
        Initialize the task worker.

        Args:
            device: AmplifierDevice object
            tasks: List of task names to execute
            settings: Settings dictionary
            constants: Constants module
            command_sequences: Command sequences dictionary
            output_dir: Output directory path
        """
        super().__init__()
        self.device = device
        self.tasks = tasks
        self.settings = settings
        self.constants = constants
        self.command_sequences = command_sequences
        self.output_dir = output_dir

    def run(self):
        """Execute SSH tasks in background thread."""
        try:
            # Import here to avoid issues with module loading
            from ssh_manager import connect_and_run_tasks

            mac = self.device.mac_address
            ip = self.device.ipv6_address

            # Emit started signals for all tasks
            for task_name in self.tasks:
                self.task_started.emit(mac, task_name)

            # Execute tasks
            result_mac, result_data = connect_and_run_tasks(
                mac,
                ip,
                self.tasks,
                self.command_sequences,
                self.device.image,
                self.settings,
                self.constants,
                device_index=1,
                total_devices=1,
                output_dir=self.output_dir
            )

            # Process results and emit signals
            if result_data and isinstance(result_data, dict):
                tasks_results = result_data.get('tasks', {})

                for task_name in self.tasks:
                    task_result = tasks_results.get(task_name, {})
                    task_status = task_result.get('task_status', 'Unknown')

                    if task_status == 'Success':
                        self.task_completed.emit(mac, task_name, task_result)
                    else:
                        error_msg = task_result.get('details', 'Unknown error')
                        self.task_failed.emit(mac, task_name, error_msg)

            # Emit all completed
            self.all_completed.emit(mac, result_data or {})

        except Exception as e:
            # Emit failure for all tasks
            for task_name in self.tasks:
                self.task_failed.emit(self.device.mac_address, task_name, str(e))
