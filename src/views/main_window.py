"""
Main Window

The main application window with fullscreen dashboard layout.
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QMenuBar, QMenu, QToolBar, QStatusBar, QLabel
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QAction, QIcon

from .widgets.device_input_panel import DeviceInputPanel
from .widgets.task_selection_panel import TaskSelectionPanel
from .widgets.control_panel import ControlPanel
from .widgets.graph_display_panel import GraphDisplayPanel
from .widgets.execution_status_panel import ExecutionStatusPanel
from .widgets.log_console_panel import LogConsolePanel


class MainWindow(QMainWindow):
    """Main application window with fullscreen dashboard."""

    def __init__(self):
        """Initialize the main window."""
        super().__init__()
        self.setWindowTitle("AmpPoll - Amplifier Polling Dashboard")
        self.resize(1080, 768)  # Default size, will go fullscreen

        # Initialize UI components
        self._create_menu_bar()
        #self._create_toolbar()
        self._create_central_widget()
        self._create_status_bar()

    def _create_menu_bar(self):
        """Create the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Settings menu
        settings_menu = menubar.addMenu("&Settings")

        preferences_action = QAction("&Preferences", self)
        preferences_action.setShortcut("Ctrl+,")
        # preferences_action.triggered.connect(self._show_preferences)
        settings_menu.addAction(preferences_action)

        connection_settings_action = QAction("&Connection Settings", self)
        # connection_settings_action.triggered.connect(self._show_connection_settings)
        settings_menu.addAction(connection_settings_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        self.toggle_status_action = QAction("Toggle &Status Panel", self)
        self.toggle_status_action.setShortcut("Ctrl+1")
        self.toggle_status_action.setCheckable(True)
        self.toggle_status_action.setChecked(False)  # Hidden by default
        self.toggle_status_action.triggered.connect(self._toggle_status_panel)
        view_menu.addAction(self.toggle_status_action)

        toggle_log_action = QAction("Toggle &Log Console", self)
        toggle_log_action.setShortcut("Ctrl+2")
        toggle_log_action.setCheckable(True)
        toggle_log_action.setChecked(False)  # Hidden by default
        # Note: same panel as status, so use same toggle
        view_menu.addAction(toggle_log_action)

        view_menu.addSeparator()

        fullscreen_action = QAction("&Fullscreen", self)
        fullscreen_action.setShortcut("F11")
        fullscreen_action.setCheckable(True)
        fullscreen_action.triggered.connect(self._toggle_fullscreen)
        view_menu.addAction(fullscreen_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        about_action = QAction("&About", self)
        # about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

        documentation_action = QAction("&Documentation", self)
        documentation_action.setShortcut("F1")
        # documentation_action.triggered.connect(self._show_documentation)
        help_menu.addAction(documentation_action)

    def _create_toolbar(self):
        """Create the toolbar."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)

        # Submit action
        submit_action = QAction("Submit", self)
        submit_action.setShortcut("Ctrl+Return")
        # submit_action.triggered.connect(self._on_submit)
        toolbar.addAction(submit_action)

        toolbar.addSeparator()

        # Clear action
        clear_action = QAction("Clear", self)
        clear_action.setShortcut("Ctrl+R")
        # clear_action.triggered.connect(self._on_clear)
        toolbar.addAction(clear_action)

        toolbar.addSeparator()

        # Open output folder action
        open_folder_action = QAction("Open Output Folder", self)
        # open_folder_action.triggered.connect(self._open_output_folder)
        toolbar.addAction(open_folder_action)

    def _create_central_widget(self):
        """Create the central widget with 3-panel layout."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main horizontal layout
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Create horizontal splitter for 3-panel layout
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # LEFT PANEL: Device input, task selection, controls
        left_panel = self._create_left_panel()
        main_splitter.addWidget(left_panel)

        # CENTER PANEL: Graph display
        self.graph_panel = GraphDisplayPanel()
        main_splitter.addWidget(self.graph_panel)

        # RIGHT PANEL: Execution status and log console (vertical splitter)
        self.right_panel = self._create_right_panel()
        main_splitter.addWidget(self.right_panel)

        # Set initial sizes (25% left, 75% center when right panel hidden)
        main_splitter.setSizes([480, 1440, 0])
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 3)
        main_splitter.setStretchFactor(2, 0)

        # Hide right panel by default
        self.right_panel.hide()

        main_layout.addWidget(main_splitter)

        # Store references
        self.main_splitter = main_splitter

    def _create_left_panel(self) -> QWidget:
        """
        Create the left control panel.

        Returns:
            QWidget containing device input, task selection, and controls
        """
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(10)

        # Device input panel
        self.device_input_panel = DeviceInputPanel()
        left_layout.addWidget(self.device_input_panel)

        # Task selection panel
        self.task_selection_panel = TaskSelectionPanel()
        left_layout.addWidget(self.task_selection_panel)

        # Control panel
        self.control_panel = ControlPanel()
        left_layout.addWidget(self.control_panel)

        # Add stretch to push everything to the top
        left_layout.addStretch()

        return left_panel

    def _create_right_panel(self) -> QWidget:
        """
        Create the right panel with status and log console.

        Returns:
            QWidget containing execution status and log console
        """
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(0)

        # Create vertical splitter for status and log
        right_splitter = QSplitter(Qt.Orientation.Vertical)

        # Execution status panel
        self.status_panel = ExecutionStatusPanel()
        right_splitter.addWidget(self.status_panel)

        # Log console panel
        self.log_panel = LogConsolePanel()
        right_splitter.addWidget(self.log_panel)

        # Set initial sizes (60% status, 40% log)
        right_splitter.setSizes([600, 400])
        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 2)

        right_layout.addWidget(right_splitter)

        # Store reference
        self.right_splitter = right_splitter

        return right_panel

    def _create_status_bar(self):
        """Create the status bar."""
        statusbar = QStatusBar()
        self.setStatusBar(statusbar)

        # Connection status label
        self.connection_status_label = QLabel("Disconnected")
        statusbar.addWidget(self.connection_status_label)

        statusbar.addWidget(QLabel("|"))

        # Task progress label
        self.task_progress_label = QLabel("Ready")
        statusbar.addWidget(self.task_progress_label)

        statusbar.addWidget(QLabel("|"))

        # Output directory label
        self.output_dir_label = QLabel("Output: output/")
        statusbar.addPermanentWidget(self.output_dir_label)

    def _toggle_fullscreen(self, checked: bool):
        """
        Toggle fullscreen mode.

        Args:
            checked: True if fullscreen should be enabled
        """
        if checked:
            self.showFullScreen()
        else:
            self.showNormal()

    def _toggle_status_panel(self, checked: bool):
        """
        Toggle the status/log panel visibility.

        Args:
            checked: True to show, False to hide
        """
        if checked:
            self.right_panel.show()
            # Adjust splitter sizes to show right panel (25% left, 50% center, 25% right)
            self.main_splitter.setSizes([480, 960, 480])
        else:
            self.right_panel.hide()
            # Adjust splitter sizes for 2-panel layout (25% left, 75% center)
            self.main_splitter.setSizes([480, 1440, 0])

    def show_status_panel(self):
        """Show the status panel (called when task execution starts)."""
        self.right_panel.show()
        self.toggle_status_action.setChecked(True)
        # Adjust splitter sizes to show right panel
        self.main_splitter.setSizes([480, 960, 480])

    def update_connection_status(self, status: str):
        """
        Update the connection status in the status bar.

        Args:
            status: Connection status text
        """
        self.connection_status_label.setText(status)

    def update_task_progress(self, progress: str):
        """
        Update the task progress in the status bar.

        Args:
            progress: Task progress text
        """
        self.task_progress_label.setText(progress)

    def update_output_directory(self, directory: str):
        """
        Update the output directory in the status bar.

        Args:
            directory: Output directory path
        """
        self.output_dir_label.setText(f"Output: {directory}")
