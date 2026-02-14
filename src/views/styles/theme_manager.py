"""
Theme Manager

Manages application theming including Comcast branding, custom fonts, and stylesheets.
"""

import os
from PyQt6.QtGui import QFontDatabase, QFont
from PyQt6.QtWidgets import QApplication


class ThemeManager:
    """Manages application theme and branding."""

    # Comcast brand colors
    COMCAST_COLORS = {
        'primary_blue': '#069de0',
        'dark_blue': '#0B8457',
        'success_green': '#05ac3f',
        'warning_orange': '#ff7112',
        'danger_red': '#ef1541',
        'light_gray': '#f0f0f0',
        'dark_gray': '#1a1a1a',
        'white': '#ffffff',
        'black': '#000000',
    }

    @staticmethod
    def apply_comcast_theme(app: QApplication):
        """
        Apply Comcast branding to the Qt application.

        Args:
            app: QApplication instance
        """
        # Load and apply custom font
        ThemeManager._load_custom_font(app)

        # Load and apply QSS stylesheet
        ThemeManager._load_stylesheet(app)

    @staticmethod
    def _load_custom_font(app: QApplication):
        """
        Load ComcastNewVision custom font.

        Args:
            app: QApplication instance
        """
        # Get the project root directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
        font_path = os.path.join(project_root, 'resources', 'fonts', 'ComcastNewVision.otf')

        if os.path.exists(font_path):
            font_id = QFontDatabase.addApplicationFont(font_path)
            if font_id != -1:
                font_families = QFontDatabase.applicationFontFamilies(font_id)
                if font_families:
                    app.setFont(QFont(font_families[0], 10))
                    print(f"Loaded custom font: {font_families[0]}")
            else:
                print(f"Failed to load font from: {font_path}")
        else:
            print(f"Font file not found: {font_path}")
            # Fallback to system fonts
            app.setFont(QFont("Segoe UI", 10))

    @staticmethod
    def _load_stylesheet(app: QApplication):
        """
        Load and apply QSS stylesheet.

        Args:
            app: QApplication instance
        """
        # Get the project root directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
        qss_path = os.path.join(project_root, 'resources', 'styles', 'comcast_stylesheet.qss')

        if os.path.exists(qss_path):
            try:
                with open(qss_path, 'r', encoding='utf-8') as f:
                    stylesheet = f.read()
                app.setStyleSheet(stylesheet)
                print(f"Loaded stylesheet from: {qss_path}")
            except Exception as e:
                print(f"Error loading stylesheet: {e}")
        else:
            print(f"Stylesheet file not found: {qss_path}")

    @staticmethod
    def get_color(color_name: str) -> str:
        """
        Get a Comcast brand color by name.

        Args:
            color_name: Name of the color (e.g., 'primary_blue', 'success_green')

        Returns:
            Hex color code string, or black if not found
        """
        return ThemeManager.COMCAST_COLORS.get(color_name, '#000000')

    @staticmethod
    def get_status_color(status: str) -> str:
        """
        Get appropriate color for a status.

        Args:
            status: Status string (waiting, running, success, failed, etc.)

        Returns:
            Hex color code string
        """
        status_lower = status.lower()
        if status_lower in ('success', 'completed', 'pass'):
            return ThemeManager.COMCAST_COLORS['success_green']
        elif status_lower in ('failed', 'error', 'stop'):
            return ThemeManager.COMCAST_COLORS['danger_red']
        elif status_lower in ('running', 'in_progress'):
            return ThemeManager.COMCAST_COLORS['warning_orange']
        elif status_lower in ('waiting', 'pending'):
            return ThemeManager.COMCAST_COLORS['light_gray']
        else:
            return ThemeManager.COMCAST_COLORS['dark_gray']
