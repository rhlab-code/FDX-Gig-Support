"""
Task Execution Models

Represents tasks, their execution state, and results.
"""

from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime


class TaskStatus(Enum):
    """Enumeration of possible task statuses."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task:
    """Model representing a single task to be executed."""

    def __init__(self, name: str, task_type: str = "get"):
        """
        Initialize a Task.

        Args:
            name: Task name (e.g., "get_wbfft", "get_eq")
            task_type: Type of task (get, show, configure, adjust)
        """
        self.name = name
        self.task_type = task_type
        self.status = TaskStatus.PENDING
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.result: Optional['TaskResult'] = None
        self.error_message: Optional[str] = None

    def start(self):
        """Mark the task as started."""
        self.status = TaskStatus.RUNNING
        self.start_time = datetime.now()

    def complete(self, result: 'TaskResult'):
        """
        Mark the task as completed successfully.

        Args:
            result: Task execution result
        """
        self.status = TaskStatus.SUCCESS
        self.end_time = datetime.now()
        self.result = result

    def fail(self, error_message: str):
        """
        Mark the task as failed.

        Args:
            error_message: Description of the failure
        """
        self.status = TaskStatus.FAILED
        self.end_time = datetime.now()
        self.error_message = error_message

    def cancel(self):
        """Mark the task as cancelled."""
        self.status = TaskStatus.CANCELLED
        self.end_time = datetime.now()

    @property
    def duration(self) -> Optional[float]:
        """Get task duration in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None

    def __repr__(self) -> str:
        """String representation of the task."""
        return f"Task(name={self.name}, status={self.status.value})"


class TaskResult:
    """Model representing the result of a task execution."""

    def __init__(self, task_name: str):
        """
        Initialize a TaskResult.

        Args:
            task_name: Name of the task that produced this result
        """
        self.task_name = task_name
        self.success = False
        self.details: str = ""
        self.task_results: List[Dict[str, Any]] = []  # List of command step results
        self.output_files: List[str] = []  # Paths to generated JSON files
        self.report_files: List[str] = []  # Paths to generated HTML reports
        self.raw_output: str = ""

    def add_output_file(self, filepath: str):
        """Add an output file path."""
        self.output_files.append(filepath)

    def add_report_file(self, filepath: str):
        """Add a report file path."""
        self.report_files.append(filepath)

    def set_success(self, details: str = ""):
        """Mark the result as successful."""
        self.success = True
        self.details = details

    def set_failure(self, details: str):
        """Mark the result as failed."""
        self.success = False
        self.details = details

    def __repr__(self) -> str:
        """String representation of the result."""
        status = "SUCCESS" if self.success else "FAILED"
        return f"TaskResult(task={self.task_name}, status={status})"


class TaskSequence:
    """Model representing a sequence of tasks for a device."""

    def __init__(self, device_mac: str):
        """
        Initialize a TaskSequence.

        Args:
            device_mac: MAC address of the device
        """
        self.device_mac = device_mac
        self.tasks: List[Task] = []

    def add_task(self, task: Task):
        """Add a task to the sequence."""
        self.tasks.append(task)

    def get_task(self, task_name: str) -> Optional[Task]:
        """
        Get a task by name.

        Args:
            task_name: Name of the task to find

        Returns:
            Task if found, None otherwise
        """
        for task in self.tasks:
            if task.name == task_name:
                return task
        return None

    def get_pending_tasks(self) -> List[Task]:
        """Get all pending tasks."""
        return [t for t in self.tasks if t.status == TaskStatus.PENDING]

    def get_completed_tasks(self) -> List[Task]:
        """Get all completed (success or failed) tasks."""
        return [t for t in self.tasks if t.status in (TaskStatus.SUCCESS, TaskStatus.FAILED)]

    @property
    def total_tasks(self) -> int:
        """Get total number of tasks."""
        return len(self.tasks)

    @property
    def completed_count(self) -> int:
        """Get number of completed tasks."""
        return len(self.get_completed_tasks())

    @property
    def progress_percentage(self) -> float:
        """Get progress as a percentage (0-100)."""
        if self.total_tasks == 0:
            return 0.0
        return (self.completed_count / self.total_tasks) * 100

    def __repr__(self) -> str:
        """String representation of the task sequence."""
        return f"TaskSequence(device={self.device_mac}, tasks={self.total_tasks}, completed={self.completed_count})"
