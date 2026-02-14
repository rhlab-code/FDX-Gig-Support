"""
Amplifier Device Model

Represents an amplifier device with its properties and connection state.
"""

from typing import Optional
from enum import Enum


class ConnectionState(Enum):
    """Enumeration of possible connection states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"


class AmplifierDevice:
    """Model representing an amplifier device."""

    def __init__(
        self,
        mac_address: str,
        ipv6_address: Optional[str] = None,
        image: str = "CC"
    ):
        """
        Initialize an AmplifierDevice.

        Args:
            mac_address: MAC address of the device
            ipv6_address: IPv6 address of the device (optional)
            image: Software image type (CC, CS, SC, BC, CCs)
        """
        self.mac_address = mac_address
        self.ipv6_address = ipv6_address
        self.image = image

        # Device information (populated after connection)
        self.device_type: Optional[str] = None
        self.vendor: Optional[str] = None
        self.firmware_version: Optional[str] = None
        self.serial_number: Optional[str] = None

        # Connection state
        self.connection_state = ConnectionState.DISCONNECTED

        # Device-specific settings
        self.ds_profile: Optional[dict] = None  # Downstream profile
        self.us_profile: Optional[dict] = None  # Upstream profile
        self.rlsp: Optional[float] = None  # Upstream RLSP value

    def is_connected(self) -> bool:
        """Check if the device is currently connected."""
        return self.connection_state == ConnectionState.CONNECTED

    def set_device_info(
        self,
        device_type: str,
        vendor: str,
        firmware_version: str,
        serial_number: str
    ):
        """
        Set device information from showModuleInfo response.

        Args:
            device_type: Type of device (e.g., "CASA Systems CE4100")
            vendor: Vendor identifier (SC, CS, CC)
            firmware_version: Firmware version string
            serial_number: Serial number
        """
        self.device_type = device_type
        self.vendor = vendor
        self.firmware_version = firmware_version
        self.serial_number = serial_number

    def update_connection_state(self, state: ConnectionState):
        """
        Update the connection state of the device.

        Args:
            state: New connection state
        """
        self.connection_state = state

    def __repr__(self) -> str:
        """String representation of the device."""
        return f"AmplifierDevice(mac={self.mac_address}, ip={self.ipv6_address}, image={self.image}, state={self.connection_state.value})"

    def __str__(self) -> str:
        """Human-readable string representation."""
        return f"{self.mac_address} ({self.connection_state.value})"
