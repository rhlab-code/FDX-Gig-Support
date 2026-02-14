"""
Graph Display Panel

Panel for displaying interactive Plotly graphs using QWebEngineView.
"""

import os
import webbrowser
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QComboBox
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWebEngineWidgets import QWebEngineView


class GraphDisplayPanel(QWidget):
    """Panel for displaying graphs with navigation controls."""

    def __init__(self, parent=None):
        """Initialize the graph display panel."""
        super().__init__(parent)
        self.current_reports = []  # List of report file paths
        self.current_index = -1
        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI components."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Web view for Plotly HTML
        self.webview = QWebEngineView()
        self.webview.setHtml(self._get_placeholder_html())

        layout.addWidget(self.webview, 1)

        # Navigation controls
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(10, 5, 10, 5)
        controls_layout.setSpacing(8)

        # Report selector
        controls_layout.addWidget(QLabel("Report:"))
        self.report_combo = QComboBox()
        self.report_combo.setMinimumWidth(200)
        self.report_combo.currentIndexChanged.connect(self._on_report_selected)
        controls_layout.addWidget(self.report_combo, 1)

        # Previous button
        self.prev_btn = QPushButton("◄ Previous")
        self.prev_btn.clicked.connect(self._show_previous)
        self.prev_btn.setEnabled(False)
        controls_layout.addWidget(self.prev_btn)

        # Next button
        self.next_btn = QPushButton("Next ►")
        self.next_btn.clicked.connect(self._show_next)
        self.next_btn.setEnabled(False)
        controls_layout.addWidget(self.next_btn)

        controls_layout.addSpacing(20)

        # Open in browser button
        self.browser_btn = QPushButton("Open in Browser")
        self.browser_btn.clicked.connect(self._open_in_browser)
        self.browser_btn.setEnabled(False)
        controls_layout.addWidget(self.browser_btn)

        layout.addLayout(controls_layout)

        self.setLayout(layout)

    def _get_placeholder_html(self) -> str:
        """
        Get placeholder HTML when no reports are loaded.

        Returns:
            HTML string
        """
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    font-family: 'Segoe UI', Arial, sans-serif;
                    background-color: #f0f0f0;
                }
                .placeholder {
                    text-align: center;
                    color: #666;
                }
                .placeholder h1 {
                    color: #069de0;
                    font-size: 36px;
                    margin-bottom: 10px;
                }
                .placeholder p {
                    font-size: 18px;
                }
            </style>
        </head>
        <body>
            <div class="placeholder">
                <h1>📊 AmpPoll Dashboard</h1>
                <p>No reports to display yet.</p>
                <p>Execute tasks to generate interactive graphs.</p>
            </div>
        </body>
        </html>
        """

    def load_report(self, file_path: str):
        """
        Load a single report file.

        Args:
            file_path: Path to the HTML report file
        """
        if not os.path.exists(file_path):
            print(f"Report file not found: {file_path}")
            return

        # Add to reports list if not already present
        if file_path not in self.current_reports:
            self.current_reports.append(file_path)
            self._update_report_combo()

        # Set as current report
        self.current_index = self.current_reports.index(file_path)
        self._load_current_report()

    def load_reports(self, file_paths: list):
        """
        Load multiple report files.

        Args:
            file_paths: List of paths to HTML report files
        """
        self.current_reports = [f for f in file_paths if os.path.exists(f)]
        self._update_report_combo()

        if self.current_reports:
            self.current_index = 0
            self._load_current_report()

    def _update_report_combo(self):
        """Update the report selector combobox."""
        self.report_combo.clear()
        for path in self.current_reports:
            # Extract filename for display
            filename = os.path.basename(path)
            self.report_combo.addItem(filename, path)

        self._update_navigation_buttons()

    def _load_current_report(self):
        """Load the currently selected report."""
        if 0 <= self.current_index < len(self.current_reports):
            file_path = self.current_reports[self.current_index]
            url = QUrl.fromLocalFile(file_path)
            self.webview.setUrl(url)
            self.browser_btn.setEnabled(True)
            self._update_navigation_buttons()
        else:
            self.webview.setHtml(self._get_placeholder_html())
            self.browser_btn.setEnabled(False)

    def _on_report_selected(self, index: int):
        """
        Handle report selection from combobox.

        Args:
            index: Selected index
        """
        if index >= 0:
            self.current_index = index
            self._load_current_report()

    def _show_previous(self):
        """Show the previous report."""
        if self.current_index > 0:
            self.current_index -= 1
            self.report_combo.setCurrentIndex(self.current_index)
            self._load_current_report()

    def _show_next(self):
        """Show the next report."""
        if self.current_index < len(self.current_reports) - 1:
            self.current_index += 1
            self.report_combo.setCurrentIndex(self.current_index)
            self._load_current_report()

    def _update_navigation_buttons(self):
        """Update the enabled state of navigation buttons."""
        has_reports = len(self.current_reports) > 0
        self.prev_btn.setEnabled(has_reports and self.current_index > 0)
        self.next_btn.setEnabled(has_reports and self.current_index < len(self.current_reports) - 1)

    def _open_in_browser(self):
        """Open the current report in external browser."""
        if 0 <= self.current_index < len(self.current_reports):
            file_path = self.current_reports[self.current_index]
            webbrowser.open_new_tab(f"file://{os.path.abspath(file_path)}")

    def clear(self):
        """Clear all reports and reset to placeholder."""
        self.current_reports.clear()
        self.current_index = -1
        self.report_combo.clear()
        self.webview.setHtml(self._get_placeholder_html())
        self.browser_btn.setEnabled(False)
        self._update_navigation_buttons()
