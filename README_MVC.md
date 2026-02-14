# AmpPoll MVC Dashboard

Modern PyQt6-based dashboard for amplifier diagnostics and testing with full MVC architecture.

## 🎯 Overview

This application has been completely refactored from a tkinter-based procedural design to a modern PyQt6 MVC (Model-View-Controller) architecture with a fullscreen dashboard interface that displays interactive Plotly graphs directly within the application.

### Key Features

- ✅ **Modern PyQt6 UI** - Fullscreen dashboard with professional Comcast branding
- ✅ **Embedded Interactive Graphs** - Plotly reports displayed in-app using QWebEngineView
- ✅ **MVC Architecture** - Clean separation of concerns for maintainability
- ✅ **Real-time Status Updates** - Tree view showing task execution progress
- ✅ **Background Task Execution** - Non-blocking SSH operations using QThread
- ✅ **Comcast Brand Compliance** - Custom fonts, colors, and styling
- ✅ **External Report Launch** - Option to open HTML reports in browser

## 🏗️ Architecture

### Project Structure

```
fdx_gig/
├── main.py                    # Application entry point
├── requirements.txt           # Python dependencies
├── amp_settings.json          # Configuration file
│
├── src/                       # Source code (NEW)
│   ├── models/                # Domain models
│   │   ├── amplifier.py       # Device model
│   │   ├── task.py            # Task execution models
│   │   ├── measurement.py     # Measurement data models
│   │   ├── app_state.py       # Observable application state
│   │   └── configuration.py   # Configuration models
│   │
│   ├── views/                 # PyQt6 UI components
│   │   ├── main_window.py     # Main window
│   │   ├── widgets/           # UI widgets
│   │   │   ├── device_input_panel.py
│   │   │   ├── task_selection_panel.py
│   │   │   ├── control_panel.py
│   │   │   ├── graph_display_panel.py
│   │   │   ├── execution_status_panel.py
│   │   │   └── log_console_panel.py
│   │   └── styles/
│   │       └── theme_manager.py
│   │
│   ├── controllers/           # Application logic
│   │   └── main_controller.py
│   │
│   └── workers/               # Background workers
│       └── task_worker.py     # QThread SSH task execution
│
├── lib/                       # Business logic (existing)
│   ├── ssh_manager.py         # SSH connection & task execution
│   ├── analysis.py            # Data analysis & coefficient decoding
│   ├── reporting.py           # Plotly HTML report generation
│   ├── parsers.py             # Output parsing
│   ├── commands.py            # Command sequences
│   └── utils.py               # Utility functions
│
├── resources/                 # Resources
│   ├── fonts/ComcastNewVision.otf
│   ├── icons/
│   └── styles/comcast_stylesheet.qss
│
└── legacy/                    # Old tkinter GUI (archived)
    ├── app.py
    └── tools.py
```

### MVC Design

**Model Layer** (`src/models/`):
- `AmplifierDevice` - Device properties and connection state
- `Task`, `TaskResult`, `TaskSequence` - Task execution models
- `WBFFTMeasurement`, `EqualizerData`, etc. - Measurement data
- `ApplicationState` - Observable state with Qt signals

**View Layer** (`src/views/`):
- `MainWindow` - Fullscreen dashboard with 3-panel layout
- Device input, task selection, control buttons (left panel)
- Interactive graph display with QWebEngineView (center panel)
- Execution status tree and log console (right panel)
- Comcast brand styling via QSS

**Controller Layer** (`src/controllers/`):
- `MainController` - Orchestrates UI and business logic
- Handles user interactions, validates input
- Manages TaskWorker threads for SSH operations
- Updates UI based on task execution signals

## 🚀 Getting Started

### Prerequisites

- Python 3.8+
- PyQt6 and PyQt6-WebEngine
- All existing dependencies (paramiko, plotly, pandas, etc.)

### Installation

1. **Install dependencies:**

```bash
pip install -r requirements.txt
```

2. **Verify resources:**

Ensure the following files exist:
- `resources/fonts/ComcastNewVision.otf`
- `resources/styles/comcast_stylesheet.qss`
- `amp_settings.json`

### Running the Application

```bash
python main.py
```

The application will launch in fullscreen mode with the modern dashboard interface.

## 📋 Usage

### Basic Workflow

1. **Select Device Configuration:**
   - Choose amp software type (CC, CS, SC, BC, CCs)
   - Enter MAC address or IPv6 address

2. **Select Tasks:**
   - Check desired tasks:
     - WBFFT - Wideband FFT measurement
     - Equalizer - US/DS equalizer coefficients
     - Shape Filter - Shaping filter coefficients
     - Echo Canceller - EC coefficients and PSD
     - Upstream PSD - Power spectral density analysis
   - Use "Select All" to choose all non-reset tasks

3. **Execute:**
   - Click "Submit" (or press Ctrl+Return)
   - Monitor real-time progress in execution status panel
   - View logs in console panel

4. **View Results:**
   - Interactive graphs display automatically in center panel
   - Use navigation controls to switch between reports
   - Click "Open in Browser" for external viewing
   - Zoom, pan, hover on graphs for full Plotly interactivity

### Keyboard Shortcuts

- `Ctrl+Return` - Submit
- `Ctrl+R` - Clear
- `Ctrl+Q` - Exit
- `F11` - Toggle fullscreen
- `Ctrl+1` - Toggle status panel
- `Ctrl+2` - Toggle log console
- `F1` - Documentation

## 🎨 Comcast Branding

The application adheres to Comcast brand guidelines:

### Colors

- **Primary Blue:** `#069de0`
- **Success Green:** `#05ac3f`
- **Warning Orange:** `#ff7112`
- **Danger Red:** `#ef1541`

### Typography

- Font: ComcastNewVision (custom font loaded from resources)
- Fallback: Segoe UI

### UI Elements

- Buttons styled with brand colors
- Group boxes with blue borders
- Status indicators with appropriate colors
- Modern, clean design aesthetic

## 🔧 Configuration

### Settings File (`amp_settings.json`)

Contains connection settings, device configurations, and WBFFT constants. Loaded automatically on startup.

### Output Directory

Reports are saved to `output/` by default. Structure:
```
output/
└── {fn_name}/{mac}/{datetime}/
    ├── {mac}_get_wbfft_data_{timestamp}.html
    ├── {mac}_get_eq_data_{timestamp}.html
    └── ...
```

## 🧪 Testing

### Manual Testing

1. Launch application: `python main.py`
2. Verify UI loads with Comcast branding
3. Test address validation (enter invalid address)
4. Select tasks and submit
5. Verify status updates in real-time
6. Check graph display loads correctly
7. Test external browser launch

### Key Test Cases

- ✅ Address validation (MAC and IPv6 formats)
- ✅ Task execution with real device
- ✅ Graph embedding in QWebEngineView
- ✅ Progress tracking and status updates
- ✅ Error handling and user feedback
- ✅ Fullscreen mode and panel resizing

## 📊 Features Comparison

| Feature | Old (tkinter) | New (PyQt6 MVC) |
|---------|---------------|-----------------|
| Architecture | Procedural | MVC |
| UI Framework | tkinter/ttkbootstrap | PyQt6 |
| Graph Display | External browser only | Embedded + External |
| Interactivity | None in-app | Full Plotly interactivity |
| Status Tracking | Text labels | Tree view with icons |
| Logging | None | Filtered log console |
| Threading | Basic | QThread with signals |
| Branding | Partial | Full Comcast compliance |
| Maintainability | Low | High |

## 🔍 Technical Details

### Observable State Management

`ApplicationState` uses Qt signals for reactive updates:
- `device_added` - New device added
- `task_started` - Task execution started
- `task_completed` - Task completed successfully
- `report_generated` - HTML report ready
- UI components automatically update via signal/slot connections

### Background Task Execution

`TaskWorker` (QThread) handles SSH operations:
1. Runs in separate thread (non-blocking UI)
2. Emits progress signals
3. Calls existing `ssh_manager.connect_and_run_tasks()`
4. Thread-safe communication via Qt signals

### Graph Display Strategy

Uses `QWebEngineView` (Chromium-based):
- Embeds Plotly HTML reports directly
- Full interactivity (zoom, pan, hover, legend toggle)
- No changes to existing `reporting.py`
- Professional in-app experience

## 🐛 Troubleshooting

### Application won't start

- Check PyQt6 installation: `pip install PyQt6 PyQt6-WebEngine`
- Verify Python version: 3.8+
- Check console for error messages

### Font not loading

- Verify `resources/fonts/ComcastNewVision.otf` exists
- Application will fall back to Segoe UI automatically

### Graphs not displaying

- Ensure QWebEngineView is installed: `pip install PyQt6-WebEngine`
- Check that HTML files exist in output directory
- Verify file permissions

### SSH connection fails

- Check network connectivity
- Verify jumpbox credentials in `amp_settings.json`
- Review log console for error details

## 🔮 Future Enhancements

Potential improvements:
- Multi-device queue execution
- Report comparison side-by-side
- Export/import sessions
- Dark mode support
- Customizable dashboards
- Advanced filtering and search
- Data export to CSV/Excel

## 📝 Migration Notes

### From Old to New

The old tkinter GUI (`app.py`) has been moved to `legacy/` directory. To use the new PyQt6 application:

```bash
# Old way
python app.py

# New way
python main.py
```

### Backwards Compatibility

- All existing business logic preserved in `lib/`
- Same SSH connection mechanisms
- Same report generation (Plotly HTML)
- Same task execution flow
- Same configuration files

## 📄 License

Internal Comcast tool - All rights reserved.

## 🤝 Contributing

This is an internal tool. For questions or issues, contact the development team.

---

**Version:** 2.0.0 (MVC Refactored)
**Last Updated:** 2026-02-14
**Framework:** PyQt6 6.6.0+
