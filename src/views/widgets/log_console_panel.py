"""
Log Console Panel

Panel for displaying application logs with filtering and search.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QComboBox, QLineEdit, QLabel, QGroupBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor, QColor, QTextCharFormat


class LogConsolePanel(QGroupBox):
    """Panel for displaying and filtering log messages."""

    def __init__(self, parent=None):
        """Initialize the log console panel."""
        super().__init__("Log Console", parent)
        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI components."""
        layout = QVBoxLayout()

        # Filter and controls
        controls_layout = QHBoxLayout()

        # Log level filter
        controls_layout.addWidget(QLabel("Level:"))
        self.level_combo = QComboBox()
        self.level_combo.addItems(["ALL", "DEBUG", "INFO", "WARNING", "ERROR"])
        self.level_combo.setCurrentText("INFO")
        self.level_combo.currentTextChanged.connect(self._apply_filter)
        controls_layout.addWidget(self.level_combo)

        controls_layout.addSpacing(10)

        # Search
        controls_layout.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search logs...")
        self.search_input.textChanged.connect(self._on_search)
        controls_layout.addWidget(self.search_input, 1)

        # Auto-scroll checkbox
        # self.autoscroll_check = QCheckBox("Auto-scroll")
        # self.autoscroll_check.setChecked(True)
        # controls_layout.addWidget(self.autoscroll_check)

        controls_layout.addSpacing(10)

        # Clear button
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear)
        controls_layout.addWidget(clear_btn)

        layout.addLayout(controls_layout)

        # Text edit for logs
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.text_edit)

        self.setLayout(layout)

        # Store all log entries for filtering
        self.all_logs = []

    def append_log(self, message: str, level: str = "INFO"):
        """
        Append a log message.

        Args:
            message: Log message text
            level: Log level (DEBUG, INFO, WARNING, ERROR)
        """
        # Store log entry
        self.all_logs.append((level, message))

        # Check if should display based on filter
        current_filter = self.level_combo.currentText()
        if not self._should_display(level, current_filter):
            return

        # Format and display
        self._append_formatted(message, level)

    def _append_formatted(self, message: str, level: str):
        """
        Append formatted message to text edit.

        Args:
            message: Message text
            level: Log level
        """
        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # Set format based on level
        fmt = QTextCharFormat()
        if level == "DEBUG":
            fmt.setForeground(QColor("#707070"))  # Gray
        elif level == "INFO":
            fmt.setForeground(QColor("#1a1a1a"))  # Dark gray
        elif level == "WARNING":
            fmt.setForeground(QColor("#ff7112"))  # Orange
        elif level == "ERROR":
            fmt.setForeground(QColor("#ef1541"))  # Red

        cursor.setCharFormat(fmt)
        cursor.insertText(f"[{level}] {message}\n")

        # Auto-scroll
        # if self.autoscroll_check.isChecked():
        self.text_edit.moveCursor(QTextCursor.MoveOperation.End)

    def _should_display(self, level: str, filter_level: str) -> bool:
        """
        Check if log should be displayed based on filter.

        Args:
            level: Log level
            filter_level: Current filter setting

        Returns:
            True if should display
        """
        if filter_level == "ALL":
            return True

        level_priority = {
            "DEBUG": 0,
            "INFO": 1,
            "WARNING": 2,
            "ERROR": 3
        }

        return level_priority.get(level, 0) >= level_priority.get(filter_level, 0)

    def _apply_filter(self):
        """Reapply filter to all logs."""
        self.text_edit.clear()
        current_filter = self.level_combo.currentText()

        for level, message in self.all_logs:
            if self._should_display(level, current_filter):
                self._append_formatted(message, level)

    def _on_search(self, text: str):
        """
        Handle search input change.

        Args:
            text: Search text
        """
        if not text:
            # Clear highlighting
            cursor = self.text_edit.textCursor()
            cursor.select(QTextCursor.SelectionType.Document)
            fmt = QTextCharFormat()
            cursor.mergeCharFormat(fmt)
            return

        # Simple search highlighting (could be improved)
        # For now, just scroll to first occurrence
        self.text_edit.find(text)

    def clear(self):
        """Clear all logs."""
        self.text_edit.clear()
        self.all_logs.clear()

    def export_logs(self, file_path: str):
        """
        Export logs to a file.

        Args:
            file_path: Path to save logs
        """
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                for level, message in self.all_logs:
                    f.write(f"[{level}] {message}\n")
        except Exception as e:
            print(f"Error exporting logs: {e}")
