import ast
import logging
import sys
import subprocess
import os
import json
from PIL import ImageGrab
from datetime import datetime
import os

class HardStopException(Exception):
    """Custom exception to signal a hard stop of the entire script."""
    # --- FIX START ---
    # We add mac_address to the constructor to store which device caused the error.
    def __init__(self, message, mac_address=None):
        super().__init__(message)
        self.mac_address = mac_address
    # --- FIX END ---

def should_proceed(prompt_message, settings, prompt_key):
    """
    Checks a task-specific prompt setting from settings.json.
    If false (boolean or string), it auto-proceeds without a prompt.
    If true or any other value (or missing), it prompts the user for confirmation.
    """
    # Default to prompting if the setting is missing for safety.
    prompt_setting = settings.get("General settings", {}).get(prompt_key, True)

    # --- FIX: Handle both boolean `false` and string "false" ---
    # This makes the check more robust against common config file variations.
    if prompt_setting is False or (isinstance(prompt_setting, str) and prompt_setting.lower() == 'false'):
        # If disabled, log the automatic action and proceed.
        log_msg = prompt_message.replace('PROMPT ', '').split(' (yes/no)')[0]
        logging.info(f"Auto-proceeding as per setting '{prompt_key}': {log_msg}")
        return True
    else:
        # If enabled (or missing), display the prompt and wait for user input.
        user_input = input(f"{prompt_message} ")
        return user_input.lower().strip() == 'yes'

def get_ip_for_mac(mac_address, environment, ip_type, script_path):
    """Calls the Get_IP_v2.2.py script for a single MAC address."""
    if not os.path.exists(script_path):
        logging.error(f"[{mac_address}] Script not found at: {script_path}")
        return "Script Not Found"
    try:
        command = [sys.executable, script_path, environment, ip_type, mac_address]
        process = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')
        ip_address = process.stdout.strip()
        logging.info(f"[{mac_address}] Found IP: {ip_address}")
        return ip_address if ip_address else "Not Found"
    except subprocess.CalledProcessError as e:
        logging.error(f"[{mac_address}] Error during IP lookup. Stderr: {e.stderr.strip()}")
        return "Error"
    except Exception as e:
        logging.error(f"[{mac_address}] Unexpected error during IP lookup: {e}")
        return "Error"

def clean_raw_output(raw_text):
    """Cleans raw SSH output for better readability by removing control characters and normalizing lines."""
    import re
    if not isinstance(raw_text, str):
        return raw_text
    
    # This regex removes most ANSI escape codes and other non-printable control characters.
    cleaned_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]|\x1b\[[0-9;]*[a-zA-Z]', '', raw_text)
    
    # Standardize line endings to \n
    cleaned_text = cleaned_text.replace('\r\n', '\n').replace('\r', '\n')
    
    # Split by lines, strip whitespace from each, and filter out any that are now empty
    lines = [line.strip() for line in cleaned_text.split('\n')]
    non_empty_lines = [line for line in lines if line]
    
    # Join them back together
    return '\n'.join(non_empty_lines)

def save_gui_as_png(root, output_dir):
    """
    Captures the tkinter root window and saves it as a PNG file.
    
    Args:
        root: The tkinter root window object.
        output_dir: The directory to save the image in.
    """
    try:
        # Ensure the window is fully rendered before capture
        root.update_idletasks()
        
        # Get the coordinates of the tkinter window
        x = root.winfo_rootx()
        y = root.winfo_rooty()
        width = root.winfo_width()
        height = root.winfo_height()
        
        # Define the bounding box for the screenshot
        bbox = (x, y, x + width, y + height)
        
        # Capture the image
        img = ImageGrab.grab(bbox=bbox, all_screens=True)
        
        # Create a timestamped filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filepath = os.path.join(output_dir, f"execution_summary_{timestamp}.png")
        
        # Save the image
        img.save(filepath)
        logging.info(f"GUI execution summary saved to {filepath}")
        
    except Exception as e:
        logging.error(f"Failed to save GUI screenshot: {e}")

# Adding  newer function to retreive amp information
# returns json array with MAC, IPv6, and node name regardless of which address is submitted
def run_amp_info(image, addr):
    cmd = [sys.executable, os.path.join(os.path.dirname(__file__), 'amp_info.py'), 'PROD', 'CPE', addr]
    env = os.environ.copy()
    # set_status('Running Amp Info...', ok=True)
    # append_output(f'Running: {" ".join(cmd)}')
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)
        raw_out = proc.stdout.strip() if proc.stdout else ''
        # raw_err = proc.stderr.strip() if proc.stderr else ''
        if proc.returncode != 0:
            # append_output(raw_err or raw_out or f'return code {proc.returncode}')
            # set_status('Error running Amp Info', ok=False)
            return None, raw_out
        # try to parse output as JSON first, then as Python literal
        parsed = None
        if raw_out:
            try:
                parsed = json.loads(raw_out)
            except Exception:
                try:
                    parsed = ast.literal_eval(raw_out)
                except Exception:
                    parsed = None

        # append_output(raw_out or '(no output)')
        # set_status('Amp Info completed', ok=True)
        return parsed, raw_out

    except subprocess.TimeoutExpired:
        # append_output('Amp Info timed out')
        # set_status('Timeout', ok=False)
        return None, ''
    except Exception as e:
        # append_output(f'Execution error: {e}')
        # set_status('Execution error', ok=False)
        return None, ''