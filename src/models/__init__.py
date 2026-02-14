"""
Models package

Domain models for the AmpPoll application.
"""

from .amplifier import AmplifierDevice, ConnectionState
from .task import Task, TaskStatus, TaskResult, TaskSequence
from .measurement import (
    WBFFTMeasurement,
    EqualizerData,
    ShapingFilterData,
    EchoCancellerData,
    USPSDData,
    MeasurementCollection
)
from .app_state import ApplicationState
from .configuration import AppConfiguration, DeviceProfile, RFComponents

__all__ = [
    # Amplifier models
    'AmplifierDevice',
    'ConnectionState',

    # Task models
    'Task',
    'TaskStatus',
    'TaskResult',
    'TaskSequence',

    # Measurement models
    'WBFFTMeasurement',
    'EqualizerData',
    'ShapingFilterData',
    'EchoCancellerData',
    'USPSDData',
    'MeasurementCollection',

    # Application state
    'ApplicationState',

    # Configuration models
    'AppConfiguration',
    'DeviceProfile',
    'RFComponents',
]
