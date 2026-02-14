"""
AmpPoll Application Entry Point

Modern PyQt6-based dashboard for amplifier diagnostics and testing.
"""

import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

# Add src directory to path
src_path = os.path.join(os.path.dirname(__file__), 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from src.views.main_window import MainWindow
from src.views.styles.theme_manager import ThemeManager
from src.models import ApplicationState
from src.controllers.main_controller import MainController


def main():
    """Main application entry point."""
    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("AmpPoll")
    app.setOrganizationName("Comcast")

    # Apply Comcast theme
    ThemeManager.apply_comcast_theme(app)

    # Create application state
    app_state = ApplicationState()

    # Create main window
    window = MainWindow()

    # Create main controller
    controller = MainController(window, app_state)

    # Show window in fullscreen
    window.showFullScreen()

    # Log startup
    window.log_panel.append_log("AmpPoll Dashboard started", "INFO")
    window.log_panel.append_log(f"Output directory: output/", "INFO")

    # Run application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
