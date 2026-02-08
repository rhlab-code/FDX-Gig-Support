# AMP Info Launcher

A professional Tkinter-based GUI application that orchestrates analysis workflows for AMP (Amplifier) devices, integrating `amp_info.py`, `wbfft.py`, and `ec.py` scripts.

## Overview

The AMP Info Launcher provides an intuitive interface to:
1. Query device information via `amp_info.py`
2. Automatically construct device identifiers from returned metadata
3. Launch WBFFT (Wideband FFT) analysis
4. Launch EC (Echo Cancellation) analysis
5. Track execution status of all scripts in real-time
6. View detailed output logs with copy functionality

## Features

- **Professional GUI Design**: Modern ttk-based interface with custom fonts and colors
- **Real-time Status Tracking**: Monitor execution status of `amp_info.py`, `wbfft.py`, and `ec.py`
- **Animated Loading Spinner**: Visual feedback during script execution
- **Address Validation**: Supports both MAC addresses and IPv6 addresses
- **Responsive Interface**: Threading prevents GUI freezing during long operations
- **Scrollable Output Pane**: View full script output with keyboard navigation
- **Output Utilities**: Copy and Clear buttons for output management
- **Keyboard Shortcuts**: Enter to submit, focus management

## Prerequisites

### Python Version
- Python 3.7 or higher

### Required Modules

The application requires the following Python packages:

```
macaddress           # MAC address validation
numpy                # Numerical operations
paramiko             # SSH/SCP protocol
pandas               # Data processing
scipy                # Scientific computing (peak detection)
scp                  # Secure file transfer
plotly               # Interactive plotting
python-dotenv        # Environment variable loading
```

### Installation

1. **Clone or download the repository**
   ```powershell
   cd c:\Users\<username>\OneDrive - Comcast\Documents\repos\fdx_gig
   ```

2. **Install dependencies**
   ```powershell
   pip install -r requirements.txt
   ```

3. **Verify environment variables** (for `amp_info.py`)
   
   Create or update `.env` file in the project root with:
   ```
   PROD_API_KEY=your_prod_api_key
   DEV_API_KEY=your_dev_api_key
   ```

## Usage

### Running the GUI

```powershell
python app.py
```

The GUI will launch with the following interface:

- **Image Selector**: Dropdown to choose image type (CC, CS, SC, BC, CCs)
- **Address Input**: Enter a MAC address or IPv6 address
- **Status Indicators**: Real-time status for each script
- **Output Pane**: Scrollable log of all operations
- **Action Buttons**:
  - Submit: Execute the workflow
  - Copy Output: Copy output to clipboard
  - Clear: Clear the output pane

### Workflow

1. **Select Image Type**: Choose from CC, CS, SC, BC, or CCs
2. **Enter Address**: Provide either:
   - MAC address (e.g., `24:a1:86:1f:f3:ac`)
   - IPv6 address (e.g., `2001:0558:6031:001C:3408:5385:73EF:FE58`)
3. **Submit**: Click Submit or press Enter
4. **Monitor Progress**:
   - Animated spinner shows processing is active
   - Script status labels update (Running → Completed or Error)
   - Output pane displays command arguments and results
5. **Review Results**: Scroll through output, copy if needed

## Workflow Details

### Step 1: Query amp_info.py
- Calls `amp_info.py` with `PROD CPE <address>`
- Parses returned JSON/dict for:
  - `cpeIpv6Addr`: CPE device IPv6
  - `cmMacAddr`: Cable Modem MAC address
  - `fnName`: Device/node name

### Step 2: Construct Identifier String
- Format: `fnName/sanitized_MAC/YYYYMMDD_HHMM`
- MAC is sanitized (removes `:`, `-`, `_`, spaces)
- This string becomes the `--path` argument for subsequent scripts

### Step 3: Determine IP Address
- If `cpeIpv6Addr` returned: use it as `--ip`
- If `cmMacAddr` returned and submitted address is IPv6: use submitted IPv6 as `--ip`
- If submitted address is IPv6: use it as `--ip`

### Step 4: Execute wbfft.py and ec.py
Both scripts are called with:
```
--image <selected_image>
--ip <determined_ipv6>
--path <constructed_identifier_string>
```

## GUI Components

| Component | Purpose |
|-----------|---------|
| Image Dropdown | Select target image (CC/CS/SC/BC/CCs) |
| Address Entry | Input MAC or IPv6 address (required) |
| Status Label | Display current operation status |
| Script Status Area | Show real-time status for each script |
| Output Pane | Scrollable log of all commands and results |
| Submit Button | Execute workflow |
| Copy Output Button | Copy output to clipboard |
| Clear Button | Clear output pane |

## Error Handling

The application provides clear error messages for:
- Missing address input
- Invalid MAC or IPv6 format
- Missing required node name (fnName)
- Script execution failures
- Timeouts (60s for amp_info, 180s for wbfft, 300s for ec)

## Environment Variables

Set these in `.env` or system environment:
- `PROD_API_KEY`: Production API key for amp_info queries
- `DEV_API_KEY`: Development API key for amp_info queries
- `IMAGE`: Selected image type (passed to wbfft/ec)

## Logging

All operations are logged to the GUI output pane including:
- Command arguments
- Script output (stdout)
- Error messages (stderr)
- Execution status
- Return codes

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Enter | Submit workflow |
| Click address field | Set focus for input |

## Troubleshooting

### GUI not responding
- The application uses threading. If a script hangs, check that the target device is reachable.
- Common timeouts: wbfft (180s), ec (300s)

### "No node name found" error
- amp_info.py did not return fnName, cmMacAddr, or a valid IP
- Verify the address is correct and the device is reachable

### Permission errors with SSH/SCP
- Ensure paramiko has permission to access SSH keys
- Check network connectivity to target device

### Missing modules
- Run: `pip install -r requirements.txt`
- Verify Python version is 3.7+

## Example Usage

```powershell
# Launch GUI 
python app.py

# In GUI:
# 1. Select "CC" from Image dropdown
# 2. Enter "24:a1:86:1f:f3:ac" in Address field
# 3. Click Submit
# 4. Monitor output pane for progress
# 5. Results will show commands executed and any output from wbfft/ec
```

## Files

- `app.py` - Main GUI application
- `amp_info.py` - Device information query script
- `wbfft.py` - Wideband FFT analysis script
- `ec.py` - Echo Cancellation analysis script
- `requirements.txt` - Python package dependencies
- `.env` - Environment configuration (create if needed)

## Notes

- The application runs scripts as subprocesses with `shell=True` on Windows
- All output from subprocesses is captured and displayed in the GUI
- The constructed `--path` identifier is used for output file organization
- Threading ensures UI remains responsive during long operations

## Support

For issues or questions, refer to the individual script documentation:
- `amp_info.py` - Device lookup documentation
- `wbfft.py` - Wideband FFT analysis documentation
- `ec.py` - Echo Cancellation analysis documentation
