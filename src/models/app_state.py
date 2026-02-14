"""
Application State Model

Central application state management with observable properties using Qt signals.
This serves as the single source of truth for the application's runtime state.
"""

from typing import Dict, List, Optional
from PyQt6.QtCore import QObject, pyqtSignal

from .amplifier import AmplifierDevice
from .task import Task, TaskSequence, TaskResult
from .measurement import MeasurementCollection


class ApplicationState(QObject):
    """Central application state with observable properties."""

    # Signals for state changes
    device_added = pyqtSignal(object)  # Emits AmplifierDevice
    device_removed = pyqtSignal(str)  # Emits MAC address
    device_updated = pyqtSignal(object)  # Emits AmplifierDevice

    task_sequence_added = pyqtSignal(str, object)  # Emits (MAC, TaskSequence)
    task_started = pyqtSignal(str, str)  # Emits (MAC, task_name)
    task_status_changed = pyqtSignal(str, str, str)  # Emits (MAC, task_name, status)
    task_completed = pyqtSignal(str, str, object)  # Emits (MAC, task_name, TaskResult)
    task_failed = pyqtSignal(str, str, str)  # Emits (MAC, task_name, error_message)

    measurement_added = pyqtSignal(str, object)  # Emits (MAC, MeasurementCollection)

    report_generated = pyqtSignal(str, str, str)  # Emits (MAC, report_type, file_path)

    settings_changed = pyqtSignal(dict)  # Emits settings dictionary

    def __init__(self):
        """Initialize the application state."""
        super().__init__()

        # Device management
        self._devices: Dict[str, AmplifierDevice] = {}

        # Task management
        self._active_tasks: Dict[str, TaskSequence] = {}

        # Measurement data
        self._measurements: Dict[str, MeasurementCollection] = {}

        # Report files
        self._reports: Dict[str, List[Dict[str, str]]] = {}  # MAC → [{type, path}, ...]

        # Application settings
        self._selected_image = "CC"
        self._output_dir = "output"

    # Device management methods
    def add_device(self, device: AmplifierDevice):
        """
        Add or update a device in the state.

        Args:
            device: AmplifierDevice to add
        """
        self._devices[device.mac_address] = device
        self.device_added.emit(device)

    def get_device(self, mac_address: str) -> Optional[AmplifierDevice]:
        """
        Retrieve a device by MAC address.

        Args:
            mac_address: MAC address of the device

        Returns:
            AmplifierDevice if found, None otherwise
        """
        return self._devices.get(mac_address)

    def remove_device(self, mac_address: str):
        """
        Remove a device from the state.

        Args:
            mac_address: MAC address of the device to remove
        """
        if mac_address in self._devices:
            del self._devices[mac_address]
            self.device_removed.emit(mac_address)

    def update_device(self, device: AmplifierDevice):
        """
        Update an existing device.

        Args:
            device: Updated AmplifierDevice
        """
        if device.mac_address in self._devices:
            self._devices[device.mac_address] = device
            self.device_updated.emit(device)

    @property
    def devices(self) -> List[AmplifierDevice]:
        """Get all devices."""
        return list(self._devices.values())

    # Task management methods
    def add_task_sequence(self, mac_address: str, task_sequence: TaskSequence):
        """
        Add a task sequence for a device.

        Args:
            mac_address: MAC address of the device
            task_sequence: TaskSequence to add
        """
        self._active_tasks[mac_address] = task_sequence
        self.task_sequence_added.emit(mac_address, task_sequence)

    def get_task_sequence(self, mac_address: str) -> Optional[TaskSequence]:
        """
        Get the task sequence for a device.

        Args:
            mac_address: MAC address of the device

        Returns:
            TaskSequence if found, None otherwise
        """
        return self._active_tasks.get(mac_address)

    def update_task_status(self, mac_address: str, task_name: str, status: str):
        """
        Update the status of a specific task.

        Args:
            mac_address: MAC address of the device
            task_name: Name of the task
            status: New status string
        """
        task_sequence = self._active_tasks.get(mac_address)
        if task_sequence:
            task = task_sequence.get_task(task_name)
            if task:
                self.task_status_changed.emit(mac_address, task_name, status)

    def mark_task_started(self, mac_address: str, task_name: str):
        """
        Mark a task as started.

        Args:
            mac_address: MAC address of the device
            task_name: Name of the task
        """
        task_sequence = self._active_tasks.get(mac_address)
        if task_sequence:
            task = task_sequence.get_task(task_name)
            if task:
                task.start()
                self.task_started.emit(mac_address, task_name)

    def add_task_result(self, mac_address: str, task_name: str, result: TaskResult):
        """
        Add a task result and mark task as completed.

        Args:
            mac_address: MAC address of the device
            task_name: Name of the task
            result: TaskResult object
        """
        task_sequence = self._active_tasks.get(mac_address)
        if task_sequence:
            task = task_sequence.get_task(task_name)
            if task:
                task.complete(result)
                self.task_completed.emit(mac_address, task_name, result)

    def mark_task_failed(self, mac_address: str, task_name: str, error_message: str):
        """
        Mark a task as failed.

        Args:
            mac_address: MAC address of the device
            task_name: Name of the task
            error_message: Error description
        """
        task_sequence = self._active_tasks.get(mac_address)
        if task_sequence:
            task = task_sequence.get_task(task_name)
            if task:
                task.fail(error_message)
                self.task_failed.emit(mac_address, task_name, error_message)

    # Measurement management
    def add_measurement(self, mac_address: str, measurement: MeasurementCollection):
        """
        Add measurement data for a device.

        Args:
            mac_address: MAC address of the device
            measurement: MeasurementCollection object
        """
        self._measurements[mac_address] = measurement
        self.measurement_added.emit(mac_address, measurement)

    def get_measurement(self, mac_address: str) -> Optional[MeasurementCollection]:
        """
        Get measurement data for a device.

        Args:
            mac_address: MAC address of the device

        Returns:
            MeasurementCollection if found, None otherwise
        """
        return self._measurements.get(mac_address)

    # Report management
    def add_report(self, mac_address: str, report_type: str, file_path: str):
        """
        Add a generated report file.

        Args:
            mac_address: MAC address of the device
            report_type: Type of report (wbfft, eq, sf, ec, us_psd)
            file_path: Path to the HTML report file
        """
        if mac_address not in self._reports:
            self._reports[mac_address] = []

        self._reports[mac_address].append({
            'type': report_type,
            'path': file_path
        })
        self.report_generated.emit(mac_address, report_type, file_path)

    def get_reports(self, mac_address: str) -> List[Dict[str, str]]:
        """
        Get all reports for a device.

        Args:
            mac_address: MAC address of the device

        Returns:
            List of report dictionaries
        """
        return self._reports.get(mac_address, [])

    def get_latest_report(self, mac_address: str, report_type: Optional[str] = None) -> Optional[str]:
        """
        Get the latest report file path for a device.

        Args:
            mac_address: MAC address of the device
            report_type: Optional filter by report type

        Returns:
            File path to the latest report, or None
        """
        reports = self.get_reports(mac_address)
        if not reports:
            return None

        if report_type:
            filtered = [r for r in reports if r['type'] == report_type]
            return filtered[-1]['path'] if filtered else None

        return reports[-1]['path']

    # Settings management
    @property
    def selected_image(self) -> str:
        """Get the selected image type."""
        return self._selected_image

    @selected_image.setter
    def selected_image(self, value: str):
        """Set the selected image type."""
        self._selected_image = value
        self.settings_changed.emit({'selected_image': value})

    @property
    def output_dir(self) -> str:
        """Get the output directory."""
        return self._output_dir

    @output_dir.setter
    def output_dir(self, value: str):
        """Set the output directory."""
        self._output_dir = value
        self.settings_changed.emit({'output_dir': value})

    def clear_all(self):
        """Clear all state (useful for reset)."""
        self._devices.clear()
        self._active_tasks.clear()
        self._measurements.clear()
        self._reports.clear()
