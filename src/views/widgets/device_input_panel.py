"""
Device Input Panel

Panel for selecting device image type and entering MAC/IPv6 address.
"""

import re
import ipaddress
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QComboBox, QLineEdit
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QValidator


class AddressValidator(QValidator):
    """Validator for MAC and IPv6 addresses."""

    def validate(self, text: str, pos: int):
        """
        Validate the input text.

        Args:
            text: Input text
            pos: Cursor position

        Returns:
            Tuple of (state, text, pos)
        """
        if not text:
            return (QValidator.State.Intermediate, text, pos)

        # Check for MAC address format
        mac_pattern = r'^([0-9A-Fa-f]{2}[:-]){0,5}([0-9A-Fa-f]{0,2})$'
        if re.match(mac_pattern, text):
            # Count complete octets
            complete_octets = len([x for x in re.split(r'[:-]', text) if len(x) == 2])
            if complete_octets == 6:
                return (QValidator.State.Acceptable, text, pos)
            return (QValidator.State.Intermediate, text, pos)

        # Check for IPv6 address format
        try:
            ipaddress.IPv6Address(text)
            return (QValidator.State.Acceptable, text, pos)
        except ValueError:
            # Partial IPv6 might be valid
            if ':' in text or any(c in '0123456789abcdefABCDEF:' for c in text):
                return (QValidator.State.Intermediate, text, pos)

        return (QValidator.State.Invalid, text, pos)


class DeviceInputPanel(QGroupBox):
    """Panel for device configuration input."""

    # Signals
    image_changed = pyqtSignal(str)  # Emits image type
    address_changed = pyqtSignal(str)  # Emits address
    address_validated = pyqtSignal(bool)  # Emits True if valid

    def __init__(self, parent=None):
        """Initialize the device input panel."""
        super().__init__("Device Configuration", parent)
        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI components."""
        layout = QVBoxLayout()
        layout.setSpacing(10)

        # Image selector
        image_layout = QHBoxLayout()
        image_label = QLabel("Amp Software:")
        image_label.setMinimumWidth(120)
        self.image_combo = QComboBox()
        self.image_combo.addItems(['CC', 'CS', 'SC', 'BC', 'CCs'])
        self.image_combo.setCurrentText('CC')
        self.image_combo.currentTextChanged.connect(self._on_image_changed)

        image_layout.addWidget(image_label)
        image_layout.addWidget(self.image_combo, 1)
        layout.addLayout(image_layout)

        # Address entry
        addr_layout = QHBoxLayout()
        addr_label = QLabel("Address:")
        addr_label.setMinimumWidth(120)
        addr_label.setToolTip("Enter MAC address (e.g., 24:a1:86:1f:f3:ac) or IPv6 address")

        self.addr_entry = QLineEdit()
        self.addr_entry.setPlaceholderText("MAC (24:a1:86:1f:f3:ac) or IPv6")
        self.addr_entry.setValidator(AddressValidator())
        self.addr_entry.textChanged.connect(self._on_address_changed)

        addr_layout.addWidget(addr_label)
        addr_layout.addWidget(self.addr_entry, 1)
        layout.addLayout(addr_layout)

        # Validation indicator
        self.validation_label = QLabel("")
        self.validation_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.validation_label)

        self.setLayout(layout)

    def _on_image_changed(self, text: str):
        """
        Handle image selection change.

        Args:
            text: Selected image type
        """
        self.image_changed.emit(text)

    def _on_address_changed(self, text: str):
        """
        Handle address input change.

        Args:
            text: Input address text
        """
        self.address_changed.emit(text)

        # Validate address
        is_valid = self._validate_address(text)
        self.address_validated.emit(is_valid)

        # Update validation indicator
        if not text:
            self.validation_label.setText("")
            self.validation_label.setStyleSheet("")
        elif is_valid:
            self.validation_label.setText("✓ Valid address")
            self.validation_label.setStyleSheet("color: #05ac3f; font-weight: bold;")
        else:
            self.validation_label.setText("✗ Invalid address")
            self.validation_label.setStyleSheet("color: #ef1541; font-weight: bold;")

    def _validate_address(self, address: str) -> bool:
        """
        Validate if the address is a valid MAC or IPv6.

        Args:
            address: Address string to validate

        Returns:
            True if valid MAC or IPv6
        """
        if not address:
            return False

        # Try MAC address
        mac_pattern = r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$'
        if re.match(mac_pattern, address):
            return True

        # Try IPv6 address
        try:
            ipaddress.IPv6Address(address)
            return True
        except ValueError:
            pass

        return False

    def get_image(self) -> str:
        """
        Get the selected image type.

        Returns:
            Image type string
        """
        return self.image_combo.currentText()

    def get_address(self) -> str:
        """
        Get the entered address.

        Returns:
            Address string
        """
        return self.addr_entry.text().strip()

    def set_address(self, address: str):
        """
        Set the address value.

        Args:
            address: Address to set
        """
        self.addr_entry.setText(address)

    def clear(self):
        """Clear the address input."""
        self.addr_entry.clear()
        self.validation_label.setText("")
        self.validation_label.setStyleSheet("")

    def is_valid(self) -> bool:
        """
        Check if current input is valid.

        Returns:
            True if address is valid
        """
        return self._validate_address(self.get_address())
