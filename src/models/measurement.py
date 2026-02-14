"""
Measurement Data Models

Represents different types of measurement data collected from amplifier devices.
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import numpy as np


@dataclass
class WBFFTMeasurement:
    """Wideband FFT measurement data."""

    measurement_name: str  # e.g., "north_port_input", "south_port_output"
    frequencies: List[float]  # Frequency values in Hz
    amplitudes: List[float]  # Amplitude values in dBmV/100kHz
    channel_power: Optional[List[Dict[str, float]]] = None  # Channel power calculations

    def __post_init__(self):
        """Validate data after initialization."""
        if len(self.frequencies) != len(self.amplitudes):
            raise ValueError("Frequencies and amplitudes must have the same length")


@dataclass
class EqualizerData:
    """Equalizer coefficient data."""

    us_coefficients: Optional[List[complex]] = None  # Upstream pre-equalizer coefficients
    ds_coefficients: Optional[List[complex]] = None  # Downstream line equalizer coefficients
    freq_resolution_mhz: float = 0.8042  # Frequency resolution in MHz

    @property
    def us_amplitude_db(self) -> Optional[np.ndarray]:
        """Get upstream equalizer amplitude in dB."""
        if self.us_coefficients:
            return 20 * np.log10(np.abs(self.us_coefficients), where=(np.abs(self.us_coefficients) > 0),
                                out=np.full(len(self.us_coefficients), -np.inf))
        return None

    @property
    def ds_amplitude_db(self) -> Optional[np.ndarray]:
        """Get downstream equalizer amplitude in dB."""
        if self.ds_coefficients:
            return 20 * np.log10(np.abs(self.ds_coefficients), where=(np.abs(self.ds_coefficients) > 0),
                                out=np.full(len(self.ds_coefficients), -np.inf))
        return None


@dataclass
class ShapingFilterData:
    """Shaping filter coefficient data."""

    taps_data: List[float]  # Time-domain filter taps
    freq_axis: Optional[List[float]] = None  # Frequency axis from FFT
    freq_magnitude: Optional[List[float]] = None  # Frequency magnitude from FFT
    sample_rate_mhz: float = 3294.0  # Sample rate in MHz

    @property
    def num_taps(self) -> int:
        """Get number of filter taps."""
        return len(self.taps_data)


@dataclass
class EchoCancellerData:
    """Echo canceller coefficient and PSD data."""

    time_domain_coefficients: Dict[int, List[float]]  # Sub-band ID → time-domain coeffs
    freq_domain_coefficients: Dict[int, List[complex]]  # Sub-band ID → freq-domain coeffs
    psd_metrics: Optional[Dict[str, Any]] = None  # PSD measurements (echo, residual, etc.)

    def get_subband_data(self, subband_id: int) -> Optional[Dict[str, Any]]:
        """
        Get data for a specific sub-band.

        Args:
            subband_id: Sub-band identifier (0, 1, 2)

        Returns:
            Dictionary with time and frequency domain data
        """
        return {
            'time_domain': self.time_domain_coefficients.get(subband_id),
            'freq_domain': self.freq_domain_coefficients.get(subband_id)
        }


@dataclass
class USPSDData:
    """Upstream PSD (Power Spectral Density) data."""

    frequencies: List[float]  # Frequency values in MHz
    measured_psd: List[float]  # Measured PSD values
    target_psd: float  # Target PSD level
    subband_data: Dict[int, Dict[str, List[float]]]  # Sub-band specific data
    analysis: Optional[Dict[str, float]] = None  # Analysis results (EQ adjust, atten adjust)

    @property
    def delta(self) -> List[float]:
        """Calculate delta between measured and target PSD."""
        return [m - self.target_psd for m in self.measured_psd]

    def get_adjustment_suggestions(self) -> Optional[Dict[str, float]]:
        """Get suggested EQ and attenuation adjustments."""
        return self.analysis if self.analysis else None


@dataclass
class MeasurementCollection:
    """Collection of all measurements for a device."""

    device_mac: str
    wbfft: Optional[List[WBFFTMeasurement]] = None  # Multiple WBFFT measurements
    equalizer: Optional[EqualizerData] = None
    shaping_filter: Optional[ShapingFilterData] = None
    echo_canceller: Optional[EchoCancellerData] = None
    upstream_psd: Optional[USPSDData] = None

    def has_measurement(self, measurement_type: str) -> bool:
        """
        Check if a specific measurement type is available.

        Args:
            measurement_type: Type of measurement (wbfft, equalizer, shaping_filter, etc.)

        Returns:
            True if measurement is available
        """
        return getattr(self, measurement_type, None) is not None

    def get_measurement(self, measurement_type: str) -> Any:
        """
        Get a specific measurement.

        Args:
            measurement_type: Type of measurement to retrieve

        Returns:
            Measurement data or None
        """
        return getattr(self, measurement_type, None)
