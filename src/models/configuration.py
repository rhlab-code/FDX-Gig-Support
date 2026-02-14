"""
Configuration Models

Represents application configuration, device profiles, and settings.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class AppConfiguration:
    """Application-wide configuration settings."""

    # Connection settings
    jumpbox_hostname: str = "jump.autobahn.comcast.com"
    jumpbox_username: str = "svcAutobahn"
    target_username: str = "admin"
    target_password: str = "AMPadmin"

    # General settings
    output_directory: str = "output"
    log_level: str = "INFO"
    timeout: int = 60

    # WBFFT settings
    wbfft_start_freq: int = 0
    wbfft_end_freq: int = 1250000000
    wbfft_fft_size: int = 16384
    wbfft_window_mode: str = "Blackman-Harris"
    wbfft_sampling_rate: int = 1647000000

    # Device-specific settings by image type
    device_configs: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def get_device_config(self, image_type: str) -> Dict[str, Any]:
        """
        Get device-specific configuration.

        Args:
            image_type: Image type (CC, CS, SC, BC, CCs)

        Returns:
            Device configuration dictionary
        """
        return self.device_configs.get(image_type, {})

    def update_setting(self, key: str, value: Any):
        """
        Update a configuration setting.

        Args:
            key: Setting key
            value: New value
        """
        if hasattr(self, key):
            setattr(self, key, value)


@dataclass
class DeviceProfile:
    """Device profile settings (DS/US profiles, spectrum, RF components)."""

    mac_address: str

    # Downstream profile
    ds_profile: Optional[Dict[str, Any]] = None  # {start_freq, end_freq, start_power, end_power}

    # Upstream profile
    us_profile: Optional[Dict[str, Any]] = None  # {rlsp, ...}
    us_rlsp: Optional[float] = None

    # Spectrum configuration
    spectrum_config: Optional[Dict[str, Any]] = None

    # RF Components
    rf_components: Optional[Dict[str, Any]] = None  # {attenuation, equalization, backoff}

    # Alignment settings
    alignment_status: Optional[Dict[str, str]] = None

    def update_ds_profile(self, start_freq: float, end_freq: float,
                         start_power: float, end_power: float):
        """
        Update downstream profile.

        Args:
            start_freq: Start frequency in Hz
            end_freq: End frequency in Hz
            start_power: Start power in dBmV
            end_power: End power in dBmV
        """
        self.ds_profile = {
            'start_freq': start_freq,
            'end_freq': end_freq,
            'start_power': start_power,
            'end_power': end_power
        }

    def update_us_profile(self, rlsp: float, **kwargs):
        """
        Update upstream profile.

        Args:
            rlsp: Upstream RLSP value
            **kwargs: Additional profile parameters
        """
        self.us_rlsp = rlsp
        self.us_profile = {'rlsp': rlsp, **kwargs}

    def calculate_ds_power_at_freq(self, frequency: float) -> Optional[float]:
        """
        Calculate downstream power at a given frequency using linear interpolation.

        Args:
            frequency: Frequency in Hz

        Returns:
            Power in dBmV, or None if profile not set
        """
        if not self.ds_profile:
            return None

        x1 = self.ds_profile['start_freq']
        x2 = self.ds_profile['end_freq']
        y1 = self.ds_profile['start_power']
        y2 = self.ds_profile['end_power']

        if x2 == x1:
            return y1

        # Linear interpolation: y = mx + b
        m = (y2 - y1) / (x2 - x1)
        b = y1 - m * x1
        return m * frequency + b

    def has_ds_profile(self) -> bool:
        """Check if downstream profile is set."""
        return self.ds_profile is not None

    def has_us_profile(self) -> bool:
        """Check if upstream profile is set."""
        return self.us_profile is not None or self.us_rlsp is not None


@dataclass
class RFComponents:
    """RF component settings (attenuation, equalization, backoff)."""

    # Attenuation settings
    upstream_attenuation: Optional[float] = None
    downstream_attenuation: Optional[float] = None

    # Equalization settings
    upstream_equalization: Optional[float] = None
    downstream_equalization: Optional[float] = None

    # AFE backoff settings
    north_afe_backoff: Optional[Dict[str, float]] = None  # {Rx, Tx, Nc}

    def update_north_afe_backoff(self, rx: float, tx: float, nc: float):
        """
        Update North AFE backoff values.

        Args:
            rx: Rx backoff in dB
            tx: Tx backoff in dB
            nc: Nc backoff in dB
        """
        self.north_afe_backoff = {'Rx': rx, 'Tx': tx, 'Nc': nc}

    def get_total_attenuation(self, direction: str) -> Optional[float]:
        """
        Get total attenuation for a direction.

        Args:
            direction: 'upstream' or 'downstream'

        Returns:
            Total attenuation in dB
        """
        if direction == 'upstream':
            return self.upstream_attenuation
        elif direction == 'downstream':
            return self.downstream_attenuation
        return None
