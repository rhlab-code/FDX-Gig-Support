# AI Coding Agent Instructions for AmpPoll Project

## Project Overview
AmpPoll is an amplifier analysis platform for testing Comcast modem/AMP devices. It provides:
- **Tkinter GUI** (`app.py`) for interactive device testing
- **CLI scripts** for direct command execution and batch workflows
- **Unified SSH/SCP layer** for device communication via jump-box tunnel

Three core workflows:
1. **amp_info.py** – MAC → IPv6 lookup via Thanos API (subprocess calls to toybox-main/thanos2.py)
2. **wbfft_v2.py** – Spectrum analysis with dynamic command sequences (replaced wbfft.py)
3. **analysis.py + ssh_manager.py** – Centralized EC metrics, coefficient decoding, data processing

All device communication uses passwordless jump-box SSH (`jump.autobahn.comcast.com`) with SCP file retrieval.

## Architecture & Data Flow

### v2.0 Modernization (Current)
**Old (single-file scripts)**:
- `wbfft.py.bak` / `ec.py.bak` – monolithic per-workflow
- `config_manager.py.bak` / `ec_config_manager.py.bak` – static configs

**New (modular)**:
- **wbfft_v2.py** – Command dispatch via `commands.py` (generated sequences from `amp_settings.json`)
- **ssh_manager.py** – 1912-line unified SSH/SCP executor with task chaining, profile persistence, and reporting
- **analysis.py** – Shared data processing (coefficient decoding, FFT, PSD, peak detection)
- **status_monitor.py** – Real-time task dashboard (Tkinter-based for multi-device tracking)
- **commands.py** – Validates and generates HAL sequences from settings JSON (dynamically builds spectrum/ds/us/upgrade config commands)

### Device Support (Image Types)
Config-driven profiles via `amp_settings.json` (replaces hardcoded CONFIGURATIONS):
- `CC` (Comcast/RDK) – admin/AMPadmin
- `CS` (CommScope) – cli/cli
- `SC` (Sercomm) – device-specific prompts
- `BC` (Broadcom)

Each device type has unique SSH prompt markers and state transition sequences (see `ssh_manager.py` execute_command_on_shell).

### Data Flow: Single Device
```
Input (MAC or IP) → amp_info.py (Thanos lookup if MAC)
  ↓
ssh_manager.connect_and_run_tasks() [paramiko+SCP tunnel]
  ├─ commands.generate_command_sequences(amp_settings.json)
  ├─ execute_command_on_shell() [prompt-driven state machine]
  ├─ SCP retrieve (e.g., get_wbfft_data, EC coefficients)
  └─ analysis.py: parse + decode + transform
  ↓
output/<NODE_ID>/<MAC>/<TIMESTAMP>/{ec/wbfft}/ [JSON/HTML/CSV]
```

### Threading & Async Workflow
- `wbfft_v2.py` uses `threading.Thread` + `queue.Queue` for non-blocking CLI execution
- `StatusMonitor` (Tkinter) listens on queue for real-time multi-device dashboard updates
- `app.py` orchestrates legacy GUI (may be deprecated in favor of StatusMonitor)

## Critical Developer Workflows

### 1. Legacy GUI (app.py)
```powershell
python app.py [--addr <MAC|IPv6>]
```
Tkinter interface for single-device analysis. Orchestrates amp_info.py → wbfft_v2.py → analysis.py pipeline via threading.

### 2. Modern Batch Workflow (wbfft_v2.py + StatusMonitor)
```powershell
# Full workflow with dynamic commands from amp_settings.json
python wbfft_v2.py --env PROD --task showModuleInfo show_ds-profile show_us-profile get_wbfft get_ec \
  --settings amp_settings.json --mac 24:a1:86:1d:da:90

# Output: ./output/NJMFD00N0A/24a1861dda90/2026-02-12_08-22/ (NODE_ID from metadata)
```

### 3. IP Lookup (amp_info.py) – v2.2 with Enhanced Diagnostics
```powershell
python amp_info.py PROD CPE 24:a1:86:1f:f3:ac
# Returns JSON with MAC, IP, node_id, device_name; uses Thanos via toybox-main/thanos2.py
```

### 4. Direct Command Testing
```powershell
# Test SSH connectivity to device
python -m paramiko -c "ssh -J svcAutobahn@jump.autobahn.comcast.com admin@2001:0558:6026:..."

# Verify .env and API access
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print(os.getenv('PROD_API_KEY'))"
```

### Environment Setup
- **Dependencies**: `pip install -r requirements.txt` (macaddress, paramiko, pandas, scipy, plotly, python-dotenv, scp, ttkbootstrap, mpld3)
- **.env file**: Required for amp_info.py → set `PROD_API_KEY`, `DEV_API_KEY`
- **Jump-box credentials**: `svcAutobahn` (configured in `amp_settings.json` or hardcoded in ssh_manager.py)
- **amp_settings.json**: Master config file defining tasks, device profiles, spectrum settings, command sequences, timeouts

## Project-Specific Patterns & Integration Points

### 1. Command Sequence Generation (commands.py → ssh_manager.py)
- **Input**: `amp_settings.json` with config sections (spectrum, ds-profile, us-profile, upgradefw, etc.)
- **Process**: `commands.generate_command_sequences(settings, constants)` builds HAL command list with validation strings
- **Output**: List of dicts with `command`, `validation_string`, optional `delay_before_prompt`
- **Example**: `[{'command': 'configure spectrum', 'validation_string': 'spectrum-allocation', 'delay_before_prompt': 1.5}, ...]`
- **Key Pattern**: Every command has a validation_string to confirm execution; dynamic sequences allow config-driven testing

### 2. SSH State Machine (execute_command_on_shell in ssh_manager.py)
Device communications are **prompt-driven state machines**:
- Send command + `\n` → wait for optional validation_string → wait for prompt_marker (e.g., `"hal>"`)
- Handles timeout, buffer parsing, concurrent prompts, escape sequences
- Regex-based prompt detection with whitespace/control char tolerance
- **Critical**: Always handle `HardStopException` on timeout; increase `timeout` param for slow commands
- **Device-specific prompts**: Stored per image type in amp_settings.json (e.g., `"CC": {"prompt_marker": "hal>"}`)

### 3. Task Chaining & Profile Persistence (ssh_manager.py)
- **Single SSH session** per device; reused across multiple commands to avoid handshake overhead
- **Profile settings JSON** (`output/<NODE_ID>/<MAC>/profile_settings.json`) tracks DS/US profile state across tasks
- **update_profile_settings_file()**: Thread-safe updates using optional file locks
- **Task validation**: `verifiers.py` checks command output before SCP retrieval (prevents empty files)

### 4. Configuration Injection Pattern
`amp_settings.json` structure overrides defaults. Example: image-specific profiles define:
```json
{
  "CC": {
    "username": "admin",
    "password": "AMPadmin",
    "prompt_marker": "hal>",
    "commands": {...}
  }
}
```
Runtime args (--mac, --ip) override JSON values in app execution layer.

### 5. Output Directory Structure & Versioning
```
output/
  <NODE_ID>/              # From amp_info.py metadata
    <MAC>/
      <TIMESTAMP>/        # YYYYMMDD_HHMM (no seconds)
        profile_settings.json
        logs/
          workflow_log_*.log
        <MAC>_<TASK>_<TIMESTAMP>.json    # Raw data
        <MAC>_<TASK>_<TIMESTAMP>.html    # Plotly reports
        <MAC>_<TASK>_<TIMESTAMP>.csv     # Metrics
```
- **MAC-based filenames** ensure uniqueness; recent fix added IP fallback for IP-only inputs
- **Timestamp consistency**: UTC, same across all files in a run
- **Report types**: `.html` = Plotly interactive, `.json` = parsed/decoded, `.csv` = tabular metrics

### 6. Data Processing Pipeline (analysis.py)
Key transformations handled here:
- **complex_to_mag_db()**: Convert I/Q pairs → magnitude (dB): `20 * log10(√(I² + Q²))`
- **decode_line_equalizer_coefficients()**: Hex string → complex I/Q (4.12 fixed-point format)
- **perform_fft_on_taps()**: Time-domain equalizer taps → frequency response
- **process_wbfft_data()**: Raw FFT output → dB-scaled spectrum with channel power
- **calculate_channel_power()**: Per-channel aggregate metric from full spectrum
- **Peak detection**: `scipy.signal.find_peaks()` identifies **12 prominent peaks** (changed from 10 in v6.0.4)

## Common Integration Points & Gotchas

### SSH/SCP Connections
- **Jump-box required** by default; `--no-jump` flag bypasses (connects directly to device)
- Paramiko timeout issues → check `execute_command_on_shell(timeout=...)` parameter (default 20s); increase if commands slow
- SCP file retrieval can fail silently → always validate file existence after transfer using `verifiers.verify_files_retrieved()`
- Session reuse: `ssh_manager.connect_and_run_tasks()` maintains single Paramiko session across all tasks for efficiency

### Data Format Transformations
- **Complex → dB conversion** in `analysis.complex_to_mag_db()`: `magnitude_db = 20 * log10(sqrt(real² + imag²))`
- **FFT parameters** (e.g., `fftSize: 16384`, `samplingRate: 1647000000`) differ per device; defined in `amp_settings.json` per image type
- **Channel specification**: Syntax like `'99M-1215M(6M)'` means range 99M–1215M MHz in 6M step increments (parsed by commands.py)
- **Fixed-point format**: Equalizer coefficients use 4.12 (4 integer, 12 fractional bits); decoder scales by 2^12

### File Naming Conventions
When working with output files:
- Use **MAC address** as primary identifier if available
- If **IP address only** provided → use IP in filename (v2.0.3 fix)
- Timestamp format: `YYYYMMDD_HHMM` (no seconds for consistency across multi-command runs)
- File types: `.csv` (raw metrics), `.html` (Plotly plots), `.json` (parsed coefficients), `.txt` (raw device output)

### Threading & GUI Updates
- Long-running operations (SSH, SCP) block the thread; always wrap in `threading.Thread(target=func, daemon=True).start()`
- GUI updates from worker threads → use `root.after()` or thread-safe queues (see `wbfft_v2.py` queue-based StatusMonitor updates)
- Exception handling: Catch `HardStopException` from `execute_command_on_shell()` for timeout/validation failures

### Address Resolution Flow
1. If MAC provided → `amp_info.py` subprocess calls `toybox-main/thanos2.py` (Thanos API)
2. Thanos returns JSON with IPv6, node_id, device_name
3. wbfft_v2.py uses IP for SSH; MAC used only for file/log naming
4. Bypass IP lookup with `--ip` direct arg (useful for testing known devices)

## Testing / Validation Checklist
- Verify `.env` credentials before running `amp_info.py` (check `PROD_API_KEY`, `DEV_API_KEY`)
- Test address validation with both MAC (`24:a1:86:...`) and IPv6 formats
- Check SSH tunnel via: `python -c "import paramiko; print(paramiko.__version__)"`
- Validate output CSV files have expected columns (e.g., WBFFT: frequency, magnitude_db, channel_power)
- For device state transitions → enable verbose logging (`logging.DEBUG`) to see full prompt sequences
- Verify `amp_settings.json` prompt_marker matches actual device prompts (common issue: trailing spaces, control chars)

## Key Files by Role
| File | Purpose |
|------|---------|
| [app.py](app.py) | Tkinter GUI orchestrator; legacy single-device workflow |
| [wbfft_v2.py](wbfft_v2.py) | Modern CLI entry point; task dispatch + multi-device support |
| [amp_info.py](amp_info.py) | MAC → IP lookup via Thanos API; subprocess wrapper |
| [ssh_manager.py](ssh_manager.py) | Unified SSH/SCP executor (1912 lines); core state machine, task chaining, profile persistence |
| [commands.py](commands.py) | Dynamic HAL sequence generator from amp_settings.json |
| [analysis.py](analysis.py) | Shared data processing: FFT, coefficient decoding, peak detection, reporting |
| [status_monitor.py](status_monitor.py) | Real-time Tkinter dashboard for multi-device task tracking |
| [parsers.py](parsers.py) | Device output → structured JSON (HAL response parsing) |
| [verifiers.py](verifiers.py) | Validates command output before SCP retrieve (prevents empty files) |
| [utils.py](utils.py) | Helper utilities: address validation, IP lookup, error handling |
| [reporting.py](reporting.py) | Generates HTML Plotly reports (EC, WBFFT, EQ, SF, etc.) |
| [amp_settings.json](amp_settings.json) | Master config: device profiles, task definitions, spectrum/ds/us sequences |
| [toybox-main/thanos2.py](toybox-main/thanos2.py) | External Thanos API client (called as subprocess by amp_info.py)
