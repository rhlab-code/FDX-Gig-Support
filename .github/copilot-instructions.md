# AI Coding Agent Instructions for AmpPoll Project

## Project Overview
AmpPoll is an amplifier analysis platform for testing Comcast modem/AMP devices. It provides a Tkinter GUI (`app.py`) that orchestrates three core analysis workflows via SSH/SCP communication:
1. **amp_info.py** – Queries device metadata via Thanos API to get IP from MAC
2. **wbfft.py** – Wideband FFT spectrum analysis 
3. **ec.py** – Echo Cancellation coefficient/metric extraction

All device communication uses passwordless jump-box SSH with SCP file retrieval.

## Architecture & Data Flow

### Multi-Device Support
Each analysis script supports **image types** via config-driven device profiles:
- `CC` (Comcast/RDK) – admin/AMPadmin
- `CS` (CommScope) – cli/cli
- `SC` (Sercomm)
- `BC` (Broadcom)
- `CCs` (Comcast Special)

**Device identifier flow**: MAC address → [amp_info.py] → IPv6 address → [wbfft.py/ec.py] → SSH tunnel + command execution + SCP retrieve output

### Core Unified Libraries
- **`amp_library.py`** (EC use) – Base `AmpControl` class with device subclasses (`CommscopeAmp`, `ComcastAmp`, `SercommAmp`, `BroadcomAmp`). Implements polymorphic `hal_comm()` / `rf_comm()` methods that handle device-specific SSH prompts and state transitions.
- **`wbfft_amp_library.py`** (similar structure, separate for WBFFT) – Parallel device implementations.
- **`config_manager.py`** (WBFFT) / **`ec_config_manager.py`** (EC) – Single `CONFIGURATIONS` dict mapping image type → device credentials, paths, remote command sets, FFT parameters, etc.

### Threading Model
`app.py` uses `threading.Thread` for non-blocking script execution. GUI status labels update via thread-safe mechanisms (observed in execution loop); output streamed to scrolled text widget.

## Critical Developer Workflows

### Running the GUI
```powershell
python app.py
```
Launches Tkinter interface. Accepts MAC or IPv6 address input, triggers orchestrated workflow via "Submit" button.

### CLI Invocations (Direct Script Calls)
```powershell
# Query IP from MAC
python amp_info.py PROD CPE 24:a1:86:1f:f3:ac

# WBFFT analysis
python wbfft.py --image CC --domain PROD --mac 24:a1:86:00:41:74 --channels '99M-1215M(6M)'

# EC analysis
python ec.py --image CC --domain PROD --mac 24:a1:86:1f:f3:ac
```

### Environment Setup
- **Dependencies**: `pip install -r requirements.txt` (macaddress, paramiko, pandas, scipy, plotly, python-dotenv, scp)
- **.env file**: Required for `amp_info.py` (set `PROD_API_KEY`, `DEV_API_KEY`)
- **Jump-box**: SSH tunneling via `jump.autobahn.comcast.com` with `svcAutobahn` credentials (configured in `config_manager.py`)

## Project-Specific Patterns

### 1. Address Resolution Strategy
- GUI/CLI accept both **MAC address** and **IPv6 address** as input
- If MAC provided → `amp_info.py` resolves to IP; if IP provided → bypass lookup
- All output filenames include MAC or IP identifier (see v2.0.3 fix in `wbfft.py`)

### 2. SSH State Machine in `amp_library.py` / `wbfft_amp_library.py`
Device communications are **prompt-driven state machines**. Example (`CommscopeAmp.hal_comm`):
- Send `\r\n` → expect prompt (e.g., `"hal>"`)
- If `"FDX-AMP>"` seen → send `'hal\n'` to transition
- If `"login:"` seen → send `'cli\n'` 
- Loop with 10-second timeout; collect full output and parse return

**Key pattern**: Always inject `\r\n` to sync state; use `channel.recv()` polling; handle multiple concurrent prompts in output buffer.

### 3. Configuration Injection Pattern
Scripts override config values via CLI args (e.g., `--mac`, `--ip`, `--domain`, `--path`):
```python
config = config_manager.CONFIGURATIONS[args.image]
# Then override:
if args.mac:
    config['target_ecm_mac'] = args.mac
```
This allows single config file + runtime flexibility.

### 4. Output Paths & Versioning
- Results saved to `./output/<NODE_ID>/<MAC>/<TIMESTAMP>/ec/` or `wbfft/`
- All output files include device identifiers (MAC or IP) in name
- HTML reports for EC plots (Plotly), CSV data files for metrics
- Check `v6.0.x` and `v2.0.x` version comments for recent fixes (MAC vs. IP in filenames, peak detection count changes)

### 5. Peak Detection (EC only)
Uses `scipy.signal.find_peaks()` to identify **12 most prominent peaks** in time-domain echoes (changed from 10 in v6.0.4). See `ec.py` for peak sorting and plotting logic.

## Common Integration Points & Gotchas

### SSH/SCP Connections
- **Jump-box required** by default; `--no-jump` flag bypasses (connects directly to device)
- Paramiko timeout issues → check `wait_time` parameter (default 10s); increase if commands slow
- SCP file retrieval can fail silently → always validate file existence after transfer

### Data Format Transformations
- **Complex → dB conversion** in `AmpControl.complex_to_mag_db()`: `magnitude_db = 20 * log10(sqrt(real² + imag²))`
- **FFT parameters** (e.g., `fftSize: 16384`, `samplingRate: 1647000000`) differ per device; do NOT hardcode
- **Channel specification**: Syntax like `'99M-1215M(6M)'` means range 99M–1215M MHz in 6M step increments

### File Naming Conventions
When working with output files:
- Use **MAC address** as primary identifier if available
- If **IP address only** provided → use IP in filename (recent v2.0.3 fix)
- Timestamp format: `YYYYMMDD_HHMM`
- File types: `.csv` (raw metrics), `.html` (Plotly plots), `.json` (parsed coefficients), `.txt` (raw device output)

### Threading & GUI Updates
- Long-running operations (SSH, SCP) block the thread; always wrap in `threading.Thread(target=func, daemon=True).start()`
- GUI updates from worker threads → use `root.after()` or thread-safe queues (see `app.py` output streaming)

## Testing / Validation Checklist
- Verify `.env` credentials before running `amp_info.py`
- Test address validation with both MAC (`24:a1:86:...`) and IPv6 formats
- Check SSH tunnel via: `python -c "import paramiko; print(paramiko.__version__)"`
- Validate output CSV files have expected columns (e.g., EC: frequency, coefficient, magnitude_db)
- For device state transitions → enable verbose SSH logging to debug prompt sequences

## Key Files by Role
| File | Purpose |
|------|---------|
| [app.py](app.py) | Tkinter GUI orchestrator; launches workflows via threading |
| [amp_info.py](amp_info.py) | MAC → IP lookup via Thanos API |
| [wbfft.py](wbfft.py) | Spectrum analysis; FFT data retrieval + HTML plotting |
| [ec.py](ec.py) | EC metrics & coefficients extraction; peak detection |
| [config_manager.py](config_manager.py) / [ec_config_manager.py](ec_config_manager.py) | Device profiles & SSH credentials |
| [amp_library.py](amp_library.py) / [wbfft_amp_library.py](wbfft_amp_library.py) | Polymorphic device control (state machine SSH) |
| [output/](output/) | Results tree: `NODE_ID/MAC/TIMESTAMP/(ec\|wbfft)/` |
