import paramiko
import time
import logging
import json
import os
import copy
import re
from datetime import datetime
from scp import SCPClient, SCPException
import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from utils import clean_raw_output, should_proceed, HardStopException
import parsers
import verifiers
from reporting import (generate_eq_html_report, generate_ec_html_report, 
                       generate_us_psd_report, generate_ec_html_report_matlab, generate_wbfft_report, generate_sf_html_report)
from analysis import (
    decode_line_equalizer_coefficients, decode_peq_coefficients, 
    complex_to_mag_db, analyze_psd_delta, process_wbfft_data, calculate_channel_power,
    decode_shaping_filter_coefficients, perform_fft_on_taps
)

def execute_command_on_shell(shell, command, prompt_marker, wait_for_string=None, timeout=20, wait_for_prompt=True, delay_before_prompt=None):
    """Executes a command, optionally waits for a string, then waits for the prompt."""
    shell.send(command + '\n')
    output_buffer = ""
    start_time = time.time()
    
    if wait_for_string:
        wait_strings = wait_for_string if isinstance(wait_for_string, list) else [wait_for_string]
        while not any(s in output_buffer for s in wait_strings):
            if time.time() - start_time > timeout:
                error_msg = f"Timeout waiting for content ('{wait_strings}') after command: '{command}'.\nLast data:\n{output_buffer}"
                raise HardStopException(error_msg)
            if shell.recv_ready():
                output_buffer += shell.recv(4096).decode('utf-8', errors='ignore')
            time.sleep(0.1)

    if delay_before_prompt is not None:
        logging.info(f"Delaying {delay_before_prompt} second(s) before waiting for prompt after command '{command}'...")
        time.sleep(delay_before_prompt)

    if not wait_for_prompt:
        time.sleep(0.5)
        if shell.recv_ready():
             output_buffer += shell.recv(4096).decode('utf-8', errors='ignore')
        return output_buffer

    prompt_pattern = re.compile(re.escape(prompt_marker) + r'[\s\x00-\x1f]*$')

    while True:
        if shell.recv_ready():
            output_buffer += shell.recv(4096).decode('utf-8', errors='ignore')
        
        # Search the buffer for the prompt pattern. This is more reliable than endswith().
        if prompt_pattern.search(output_buffer):
            break

        if time.time() - start_time > timeout:
            error_message = f"Timeout waiting for prompt ('{prompt_marker}') after command: '{command}'.\nLast received data:\n---\n{output_buffer}\n---"
            raise HardStopException(error_message)

        time.sleep(0.1)
    
    time.sleep(0.5)   
    return output_buffer

def update_profile_settings_file(mac_address, parsed_data, task_name, output_dir, file_lock=None):
    """Reads, updates, and writes profile settings to a JSON file in a thread-safe way."""
    
    # This function defines the core logic that needs to be protected by the lock.
    def _perform_update():
        filepath = os.path.join(output_dir, "profile_settings.json")
        profile_data = {}
        if os.path.exists(filepath):
            try:
                # Check for empty file to prevent JSONDecodeError, which happens in a race condition.
                if os.path.getsize(filepath) > 0:
                    with open(filepath, 'r') as f:
                        profile_data = json.load(f)
                else:
                    logging.warning(f"[{mac_address}] profile_settings.json is empty. Initializing a new one.")
            except json.JSONDecodeError:
                logging.warning(f"[{mac_address}] Could not decode existing profile_settings.json. It may be corrupt. A new file will be created.")
                profile_data = {}

        if mac_address not in profile_data:
            profile_data[mac_address] = {}

        if task_name == 'show_ds-profile':
            profile_data[mac_address]['start-freq'] = parsed_data.get('start-freq')
            profile_data[mac_address]['end-freq'] = parsed_data.get('end-freq')
            profile_data[mac_address]['start-power'] = parsed_data.get('start-power')
            profile_data[mac_address]['end-power'] = parsed_data.get('end-power')
        elif task_name == 'show_us-profile':
            profile_data[mac_address]['RLSP'] = parsed_data.get('rlsp')

        if mac_address in profile_data:
            profile_data[mac_address] = {k: v for k, v in profile_data[mac_address].items() if v is not None}

        with open(filepath, 'w') as f:
            json.dump(profile_data, f, indent=2)
        logging.info(f"[{mac_address}] Updated profile settings in {filepath}")

    try:
        if file_lock:
            # If running in parallel, acquire the lock before accessing the file.
            with file_lock:
                _perform_update()
        else:
            # If running sequentially, no lock is needed.
            _perform_update()
    except Exception as e:
        logging.error(f"[{mac_address}] Failed to write to profile_settings.json: {e}")


def connect_and_run_tasks(mac_address, target_hostname, task_names, command_sequences, amp_image, settings, constants,
                          parent_mac=None, parent_ip=None, context=None,
                          device_index=0, total_devices=0, output_dir="output", file_lock=None):
    """Connects to a host and executes a list of predefined tasks sequentially."""
    base_response = {"ip": target_hostname, "connected": False, "tasks": {}}
    if not target_hostname or target_hostname in ["Not Found", "Error", "Script Not Found"]:
        base_response["tasks"]["error"] = "Invalid hostname"
        return mac_address, base_response

    logging.info(f"[{mac_address}] Attempting to connect to {target_hostname} to run tasks: {task_names}...")
    
    general_settings = settings.get("General settings", {})
    other_timeout = general_settings.get("other_timeout", 40)
    if amp_image == 'CC':
        connection_settings = settings.get("connection", {})
    elif amp_image == 'CS':
        connection_settings = settings.get("cs_connection", {})
    jumpbox_client, target_client, shell, scp_client = None, None, None, None

    def _check_for_hard_stop(task_name, task_result_summary):
        """Triggers a hard stop if a critical task (configure or adjust) fails."""
        is_critical = task_name.startswith('configure_') or task_name.startswith('adjust_') or task_name == 'run_alignment'
        if is_critical and task_result_summary.get("task_status") == "Failed":
            error_details = task_result_summary.get('details', 'No details provided.')
            if isinstance(error_details, dict): error_details = json.dumps(error_details)
            if task_result_summary.get("task_results"):
                for step in reversed(task_result_summary["task_results"]):
                    if not step.get('success'):
                        error_details = f"Step failed for command '{step.get('command')}'. Details: {step.get('details')}"
                        break
            raise HardStopException(f"Critical task '{task_name}' failed on device {mac_address} ({target_hostname}). Details: {error_details}", mac_address=mac_address)

    def _log_generic_task_summary(task_name, task_result_summary):
        summary_log = [f"\n[{mac_address}] --- Task Summary: {task_name} ---"]
        status = task_result_summary.get('task_status', 'Unknown')
        summary_log.append(f"Overall Status: {status}")
        if status == "Success":
            summary_log.append("- All steps completed successfully.")
            if task_result_summary.get('verification'):
                 summary_log.append("- Verification: Passed")
        elif status == "Cancelled":
            summary_log.append(f"- Details: {task_result_summary.get('details', 'Task cancelled by user.')}")
        else:
            failing_step = "Unknown failure reason."
            for step in task_result_summary.get("task_results", []):
                if not step.get('success'):
                    failing_step = f"Failed at command '{step.get('command')}'"
                    break
            summary_log.append(f"- Details: {failing_step}")
        summary_log.append("-" * (len(task_name) + 26))
        logging.info("\n".join(summary_log))

    try:
        jumpbox_client = paramiko.SSHClient(); jumpbox_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        jumpbox_client.connect(
            connection_settings.get('jumpbox_hostname'), 
            username=connection_settings.get('jumpbox_username'), 
            timeout=10
        )
        transport = jumpbox_client.get_transport()
        dest_addr = (target_hostname, 22)
        jumpbox_channel = transport.open_channel("direct-tcpip", dest_addr, ('', 0))
        target_client = paramiko.SSHClient(); target_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        target_client.connect(
            target_hostname, 
            username=connection_settings.get('target_username'), 
            password=connection_settings.get('target_password'), 
            sock=jumpbox_channel, 
            timeout=90
        )
        base_response["connected"] = True
        shell = target_client.invoke_shell()
        scp_client = SCPClient(target_client.get_transport())
        initial_output = ""
        start_time = time.time()
        while not initial_output.strip().endswith(constants.PROMPT_MARKERS['default']):
            if time.time() - start_time > 20:
                raise Exception(f"Timeout waiting for initial shell prompt. Last received: {initial_output}")
            if shell.recv_ready(): initial_output += shell.recv(4096).decode('utf-8', errors='ignore')
            time.sleep(0.1)
        
        logging.info(f"[{mac_address}] Getting device module info...")
        device_type, vendor = None, None
        info_sequence = command_sequences.get("showModuleInfo", [])
        parsed_info = {}
        show_module_info_response = {}
        try:
            info_step = info_sequence[0]
            info_output_raw = execute_command_on_shell(shell, info_step['command'], constants.PROMPT_MARKERS['default'], timeout=other_timeout)
            info_output_cleaned = clean_raw_output(info_output_raw)
            if 'parser' in info_step:
                parsed_info = info_step['parser'](info_output_cleaned)
                if parsed_info:
                    device_type = parsed_info.get('Device Type')
                    if device_type:
                        logging.info(f"[{mac_address}] Detected Device Type: {device_type}")
                    else:
                        logging.warning(f"[{mac_address}] Could not determine Device Type from showModuleInfo.")
                    
                    serial_number = parsed_info.get('Serial Number', '')
                    if serial_number.startswith('SC'):
                        vendor = "SC"
                    else:
                        vendor = "CS"
                    parsed_info['Vendor'] = vendor
                    logging.info(f"[{mac_address}] Detected Vendor: {vendor}")

                    # --- NEW: Firmware Version Check ---
                    expected_fw_version = general_settings.get("firmware_version")
                    device_fw_version = parsed_info.get("Firmware Version")
                    if expected_fw_version and device_fw_version:
                        logging.info(f"[{mac_address}] Verifying firmware. Expected: '{expected_fw_version}', Found: '{device_fw_version}'")
                        if device_fw_version != expected_fw_version:
                            error_msg = (f"Firmware version mismatch on device {mac_address}. "
                                         f"Expected '{expected_fw_version}', but found '{device_fw_version}'.")
                            raise HardStopException(error_msg, mac_address=mac_address)
                    elif expected_fw_version:
                        logging.warning(f"[{mac_address}] Could not read device firmware version to verify against '{expected_fw_version}'.")

            if "showModuleInfo" in task_names and parsed_info:
                sanitized_mac = mac_address.replace(':', '')
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = os.path.join(output_dir, f"{sanitized_mac}_showModuleInfo_{timestamp}.json")
                try:
                    with open(filename, 'w') as f: json.dump(parsed_info, f, indent=4)
                    logging.info(f"[{mac_address}] Saved parsed data for task 'showModuleInfo' to {filename}")
                    show_module_info_response['output_file'] = filename
                except Exception as e:
                    logging.error(f"[{mac_address}] Failed to save parsed data for 'showModuleInfo': {e}")

            show_module_info_response.update({
                "task_status": "Success" if parsed_info else "Failed",
                "task_results": [{'command': info_step['command'], 'success': bool(parsed_info), 'details': parsed_info, 'raw_output': info_output_cleaned}]
            })
            base_response["tasks"]["showModuleInfo"] = show_module_info_response

        except Exception as e:
            logging.error(f"[{mac_address}] Failed to execute showModuleInfo: {e}")
            base_response["tasks"]["showModuleInfo"] = {"task_status": "Failed", "details": str(e)}

        logging.info(f"[{mac_address}] Shell is ready. Executing tasks...")
        
        # --- NEW: Create a local context for this session to pass data between tasks ---
        local_context = context.copy() if context else {}

        total_tasks = len(task_names)
        for i, task_name in enumerate(task_names):
            task_index = i + 1

            logging.info(f"\n>>> Executing task {task_index}/{total_tasks} for device {device_index}/{total_devices} ({mac_address}) <<<")

            if task_name == "showModuleInfo":
                continue

            # --- Composite and Special Task Handlers ---
            if task_name == 'configure_ds-profile':
                logging.info(f"[{mac_address}] --- Starting Special Task: {task_name} ---")
                task_result_summary = {"task_status": "Failed", "details": "Task did not complete.", "task_results": [], "verification": {}}
                base_response["tasks"][task_name] = task_result_summary
                
                profile_settings_path = os.path.join(output_dir, "profile_settings.json")
                mac_profile = None
                sequence_to_run = None
                
                if os.path.exists(profile_settings_path):
                    try:
                        with open(profile_settings_path, 'r') as f:
                            mac_profile = json.load(f).get(mac_address)
                    except (json.JSONDecodeError, IOError) as e:
                        logging.warning(f"[{mac_address}] Could not read profile_settings.json: {e}. Using defaults.")

                if mac_profile and all(k in mac_profile for k in ['start-freq', 'end-freq', 'start-power', 'end-power']):
                    logging.info(f"[{mac_address}] Found existing profile. Calculating new profile based on it.")
                    try:
                        x1 = float(mac_profile['start-freq'])
                        x2 = float(mac_profile['end-freq'])
                        y1 = float(mac_profile['start-power'])
                        y2 = float(mac_profile['end-power'])

                        if x2 == x1: raise ValueError("start-freq and end-freq are identical.")

                        m = (y2 - y1) / (x2 - x1)
                        b = y1 - m * x1
                        logging.info(f"[{mac_address}] Calculated slope (m)={m:.10f}, intercept (b)={b:.2f}")

                        ds_settings = settings.get("ds-profile", {})
                        new_x1 = float(ds_settings['start-freq'])
                        new_x2 = float(ds_settings['end-freq'])

                        new_y1 = m * new_x1 + b
                        new_y2 = m * new_x2 + b
                        logging.info(f"[{mac_address}] New target profile: start-power={new_y1:.1f}, end-power={new_y2:.1f}")

                        temp_ds_settings = {
                            "start-freq": str(int(new_x1)), "end-freq": str(int(new_x2)),
                            "start-power": f"{new_y1:.1f}", "end-power": f"{new_y2:.1f}"
                        }
                        
                        sequence_to_run = [
                            {'command': f"configure ds-profile south", 'validation_string': 'obtained current configuration for ds-profile-south'},
                            {'command': f"start-freq {temp_ds_settings['start-freq']}", 'validation_string': 'is set from'},
                            {'command': f"end-freq {temp_ds_settings['end-freq']}", 'validation_string': 'is set from'},
                            {'command': f"start-power {temp_ds_settings['start-power']}", 'validation_string': 'is set from'},
                            {'command': f"end-power {temp_ds_settings['end-power']}", 'validation_string': 'is set from'},
                            {'command': 'commit', 'validation_string': 'applied local configuration'},
                            {'command': 'exit', 'validation_string': None}
                        ]
                    except (ValueError, KeyError, TypeError) as e:
                        logging.error(f"[{mac_address}] Error in dynamic profile calculation: {e}. Falling back to defaults.")
                        sequence_to_run = copy.deepcopy(command_sequences.get(task_name, []))
                else:
                    logging.info(f"[{mac_address}] No valid profile found. Using default settings from provided settings.")
                    sequence_to_run = copy.deepcopy(command_sequences.get(task_name, []))
                
                all_steps_succeeded = True
                for step in sequence_to_run:
                    command = step['command']
                    logging.info(f"[{mac_address}] Sending command: '{command}'")
                    output = execute_command_on_shell(shell, command, step.get('prompt_marker', constants.PROMPT_MARKERS['default']), timeout=other_timeout)
                    cleaned_output = clean_raw_output(output)
                    step_result = {'command': command, 'success': False, 'details': '', 'raw_output': cleaned_output}
                    if 'verifier' in step:
                        verifier_func, parser_func, settings_section = step['verifier']
                        is_match, details = verifier_func(parser_func(cleaned_output), settings_section)
                        step_result.update({'success': is_match, 'details': details if not is_match else "Verification successful."})
                        task_result_summary['verification'][step['command']] = {'status': 'Success' if is_match else 'Failed', 'details': details}
                    elif 'validation_string' in step:
                        expected = step['validation_string']
                        validation_passed = (expected is None) or \
                                          (isinstance(expected, str) and expected in cleaned_output) or \
                                          (isinstance(expected, list) and any(s in cleaned_output for s in expected))
                        step_result.update({'success': validation_passed, 'details': "Validation successful." if validation_passed else f"Validation FAILED. Expected: '{expected}'."})
                    else:
                        step_result['success'] = True
                    
                    if step_result['success']:
                        logging.info(f"[{mac_address}]   - Step Result: [SUCCESS] | Command: '{command}' | Details: {step_result['details']}")
                    else:
                        logging.warning(f"[{mac_address}]   - Step Result: [FAILED] | Command: '{command}' | Details: {step_result['details']}")

                    task_result_summary["task_results"].append(step_result)
                    if not step_result['success']:
                        all_steps_succeeded = False
                        break
                
                task_result_summary["task_status"] = "Success" if all_steps_succeeded else "Failed"
                _log_generic_task_summary(task_name, task_result_summary)
                _check_for_hard_stop(task_name, task_result_summary)
                time.sleep(1)
                continue

            if task_name == 'configure_us-profile':
                logging.info(f"[{mac_address}] --- Starting Special Task: {task_name} ---")
                task_result_summary = {"task_status": "Failed", "details": "Task did not complete.", "task_results": [], "verification": {}}
                base_response["tasks"][task_name] = task_result_summary

                profile_settings_path = os.path.join(output_dir, "profile_settings.json")
                rlsp_to_use = None
                
                # --- FIX START: Improved logic for checking profile_settings.json ---
                if os.path.exists(profile_settings_path):
                    try:
                        with open(profile_settings_path, 'r') as f:
                            mac_profile = json.load(f).get(mac_address)
                            if mac_profile and mac_profile.get('RLSP') is not None:
                                rlsp_to_use = mac_profile.get('RLSP')
                                logging.info(f"[{mac_address}] Found RLSP in profile_settings.json. Using RLSP = {rlsp_to_use}")
                    except (IOError, json.JSONDecodeError) as e:
                        # This new, more specific message will trigger if the file exists but is corrupt or unreadable.
                        logging.warning(f"[{mac_address}] Could not read or parse existing profile_settings.json: {e}. Using default RLSP.")
                else:
                    # This message now only triggers if the file is truly missing.
                    logging.info(f"[{mac_address}] No profile_settings.json found. Using default RLSP.")
                # --- FIX END ---

                if rlsp_to_use is None:
                    us_settings = settings.get("us-profile", {})
                    rlsp_to_use = us_settings.get('rlsp')
                    if rlsp_to_use is not None:
                        logging.info(f"[{mac_address}] Using default RLSP from provided settings: RLSP = {rlsp_to_use}")

                sequence_to_run = None
                if rlsp_to_use is not None:
                    temp_us_settings = {"rlsp": str(rlsp_to_use)}
                    sequence_to_run = [
                        {'command': f"configure us-profile south", 'validation_string': 'obtained current configuration for us-profile-south'},
                        {'command': f"rlsp {temp_us_settings['rlsp']}", 'validation_string': 'rlsp is set from'},
                        {'command': 'commit', 'validation_string': 'applied local configuration'},
                        {'command': 'exit', 'validation_string': None}
                    ]
                else:
                    task_result_summary["details"] = "Could not determine RLSP value."
                
                if sequence_to_run:
                    all_steps_succeeded = True
                    for step in sequence_to_run:
                        command = step['command']
                        logging.info(f"[{mac_address}] Sending command: '{command}'")
                        output = execute_command_on_shell(shell, command, step.get('prompt_marker', constants.PROMPT_MARKERS['default']), timeout=other_timeout)
                        cleaned_output = clean_raw_output(output)
                        step_result = {'command': command, 'success': False, 'details': '', 'raw_output': cleaned_output}
                        if 'verifier' in step:
                            verifier_func, parser_func, settings_section = step['verifier']
                            is_match, details = verifier_func(parser_func(cleaned_output), settings_section)
                            step_result.update({'success': is_match, 'details': details if not is_match else "Verification successful."})
                        elif 'validation_string' in step:
                            expected = step['validation_string']
                            validation_passed = (expected is None) or \
                                              (isinstance(expected, str) and expected in cleaned_output) or \
                                              (isinstance(expected, list) and any(s in cleaned_output for s in expected))
                            step_result.update({'success': validation_passed, 'details': "Validation successful." if validation_passed else f"Validation FAILED. Expected: '{expected}'."})
                        else: step_result['success'] = True
                        
                        if step_result['success']:
                            logging.info(f"[{mac_address}]   - Step Result: [SUCCESS] | Command: '{command}' | Details: {step_result['details']}")
                        else:
                            logging.warning(f"[{mac_address}]   - Step Result: [FAILED] | Command: '{command}' | Details: {step_result['details']}")

                        task_result_summary["task_results"].append(step_result)
                        if not step_result['success']: all_steps_succeeded = False; break
                    task_result_summary["task_status"] = "Success" if all_steps_succeeded else "Failed"
                
                _log_generic_task_summary(task_name, task_result_summary)
                _check_for_hard_stop(task_name, task_result_summary)
                time.sleep(1)
                continue

            if task_name == 'get_eq':
                logging.info(f"[{mac_address}] --- Starting Special Task: get_eq ---")
                task_result_summary = {"task_status": "Not Started", "details": ""}
                base_response["tasks"]["get_eq"] = task_result_summary
                raw_output = ""
                try:
                    command_str = "gnmic -a localhost:9339 --insecure get --path '/north-port-status'"
                    logging.info(f"[{mac_address}] Executing remote command: {command_str}")
                    raw_output = execute_command_on_shell(shell, command_str, constants.PROMPT_MARKERS['default'], timeout=other_timeout)
                    cleaned_output = clean_raw_output(raw_output)
                    json_start_index, json_end_index = cleaned_output.find('['), cleaned_output.rfind(']')
                    if json_start_index == -1 or json_end_index == -1 or json_end_index < json_start_index:
                        raise ValueError("Could not find a valid JSON array ('[...]') in the gnmic command output.")
                    json_string = cleaned_output[json_start_index : json_end_index + 1]
                    output_data = json.loads(json_string)
                    sanitized_mac = mac_address.replace(':', '')
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    json_filename = os.path.join(output_dir, f"{sanitized_mac}_get_eq_data_{timestamp}.json")
                    with open(json_filename, 'w') as f: json.dump(output_data, f, indent=4)
                    logging.info(f"[{mac_address}] Raw gnmic JSON data saved to {json_filename}")
                    ds_hex_coeffs = output_data[0]['updates'][0]['values']['north-port-status']['downstream-line-equalizer-coefficients']
                    ds_decoded_coeffs = decode_line_equalizer_coefficients(ds_hex_coeffs)
                    us_hex_coeffs = output_data[0]['updates'][0]['values']['north-port-status']['upstream-pre-equalizer-coefficients']
                    us_decoded_coeffs = decode_peq_coefficients(us_hex_coeffs)
                    html_filename = os.path.join(output_dir, f"{sanitized_mac}_get_eq_data_{timestamp}.html")
                    generate_eq_html_report(mac_address, us_decoded_coeffs, ds_decoded_coeffs, html_filename, 0.8042)
                    task_result_summary.update({"task_status": "Success", "details": f"JSON data saved to {json_filename}, HTML report saved to {html_filename}", "raw_output": raw_output})
                except Exception as e:
                    task_result_summary.update({"task_status": "Failed", "details": str(e)})
                logging.info(f"[{mac_address}] --- Task '{task_name}' Complete. ---")
                _check_for_hard_stop(task_name, task_result_summary)
                time.sleep(1)
                continue
            
            if task_name == 'get_sf':
                logging.info(f"[{mac_address}] --- Starting Special Task: {task_name} ---")
                task_result_summary = {"task_status": "Not Started", "details": ""}
                base_response["tasks"][task_name] = task_result_summary
                raw_output = ""
                try:
                    command_str = "gnmic -a localhost:9339 --insecure get --path '/south-port-status'"
                    logging.info(f"[{mac_address}] Executing remote command: {command_str}")
                    raw_output = execute_command_on_shell(shell, command_str, constants.PROMPT_MARKERS['default'], timeout=other_timeout)
                    cleaned_output = clean_raw_output(raw_output)
                    
                    json_start_index, json_end_index = cleaned_output.find('['), cleaned_output.rfind(']')
                    if json_start_index == -1 or json_end_index == -1 or json_end_index < json_start_index:
                        raise ValueError("Could not find a valid JSON array ('[...]') in the gnmic command output.")
                    json_string = cleaned_output[json_start_index : json_end_index + 1]
                    output_data = json.loads(json_string)

                    hex_coeffs = output_data[0]['updates'][0]['values']['south-port-status']['downstream-shaping-filter-coefficients']
                    taps_data = decode_shaping_filter_coefficients(hex_coeffs)
                    if not taps_data:
                        raise ValueError("Decoding coefficients resulted in empty list.")

                    sample_rate_mhz = 3294 
                    freq_axis, freq_magnitude = perform_fft_on_taps(taps_data, sample_rate_mhz)
                    if freq_axis is None:
                         raise ValueError("FFT analysis failed.")

                    final_data = {
                        'time_domain_taps': {'tap_numbers': list(range(len(taps_data))), 'amplitudes': taps_data},
                        'frequency_domain_response': {'frequency_mhz': freq_axis, 'normalized_magnitude_db': freq_magnitude}
                    }
                    
                    sanitized_mac = mac_address.replace(':', '')
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    json_filename = os.path.join(output_dir, f"{sanitized_mac}_get_sf_data_{timestamp}.json")
                    with open(json_filename, 'w') as f:
                        json.dump(final_data, f, indent=4)
                    logging.info(f"[{mac_address}] Shaping filter data saved to {json_filename}")

                    html_filename = generate_sf_html_report(mac_address, taps_data, (freq_axis, freq_magnitude), output_dir)
                    
                    task_result_summary.update({
                        "task_status": "Success", 
                        "details": f"JSON data saved to {json_filename}, HTML report saved to {html_filename}", 
                        "raw_output": raw_output, "output_file": json_filename, "report_file": html_filename
                    })

                except Exception as e:
                    logging.error(f"[{mac_address}] An error occurred during get_sf task: {e}", exc_info=True)
                    task_result_summary.update({"task_status": "Failed", "details": str(e), "raw_output": raw_output})
                
                logging.info(f"[{mac_address}] --- Task '{task_name}' Complete. ---")
                _check_for_hard_stop(task_name, task_result_summary)
                time.sleep(1)
                continue

            if task_name == 'get_ec':
                logging.info(f"[{mac_address}] --- Starting Special Task: {task_name} ---")
                task_result_summary = {"task_status": "Failed", "details": "Task did not complete.", "task_results": []}
                base_response["tasks"][task_name] = task_result_summary
                all_decoded_data, freq_coef_complex = {}, [[] for _ in range(3)]
                try:
                    stats_types, sub_band_ids = [1, 5, 6, 7, 8], [0, 1, 2]
                    logging.info(f"[{mac_address}] Entering HAL mode for EC data collection...")
                    execute_command_on_shell(shell, 'debug hal\r\nlog_config --off', constants.PROMPT_MARKERS['hal'], timeout=other_timeout, wait_for_prompt=False, delay_before_prompt=1)
                    for statsType in stats_types:
                        all_decoded_data[statsType] = {}
                        for subBandId in sub_band_ids:
                            filename, remote_path = f"EC_{statsType}_{subBandId}.dat", f"/tmp/EC_{statsType}_{subBandId}.dat"
                            local_path = os.path.join(output_dir, f"{mac_address.replace(':', '')}_{filename}")
                            
                            command = f"ec_pnm_stats {statsType} {subBandId} {remote_path}"
                            command_output = ""
                            command_succeeded = False
                            
                            for attempt in range(3): # Allow for one initial try and one retry
                                logging.info(f"[{mac_address}] Requesting EC data for statsType={statsType}, subBandId={subBandId} (Attempt {attempt + 1}/3)")
                                # We wait for either SUCCESS or FAILED to avoid a timeout
                                current_output = execute_command_on_shell(shell, command, constants.PROMPT_MARKERS['hal'], wait_for_string=["SUCCESS", "FAILED"], timeout=other_timeout, wait_for_prompt=False)
                                command_output = current_output
                            
                                if "SUCCESS" in command_output:
                                    command_succeeded = True
                                    break # Exit loop on success
                                
                                # If it failed, log, wait, and the loop will try again
                                wait_time = attempt * 3
                                logging.warning(f"[{mac_address}] Command '{command}' returned FAILED. Waiting {wait_time} seconds before retrying.")
                                time.sleep(wait_time)

                            time.sleep(3 if statsType == 8 else 1)

                            step_res = {'command': command, 'raw_output': clean_raw_output(command_output)}
                            
                            if not command_succeeded:
                                step_res.update({'success': False, 'details': "Command execution did not return 'SUCCESS'."})
                                task_result_summary['task_results'].append(step_res)
                                continue

                            try:
                                scp_client.get(remote_path, local_path)
                            except SCPException as e:
                                step_res.update({'success': False, 'details': f"SCP failed: {e}"})
                                task_result_summary['task_results'].append(step_res)
                                continue
                            with open(local_path, 'r') as f: content = f.readlines()
                            header_info, data_rows = {}, []
                            for line in content:
                                if ':' in line:
                                    if match := re.search(r"(\w+):(\d+)", line): header_info[match.group(1)] = int(match.group(2))
                                elif "PerBin" not in line: data_rows.append(line.strip().split(','))
                            if not header_info.get('StatType'): continue
                            values, start_freq_hz = [], header_info.get('StartFreq', 0)
                            if statsType == 1:
                                real, imag = [float(row[0]) for row in data_rows if len(row) > 1], [float(row[1]) for row in data_rows if len(row) > 1]
                                values = complex_to_mag_db(real, imag)
                                if real and imag: freq_coef_complex[subBandId] = [complex(r, i) for r, i in zip(real, imag)]
                            else:
                                values = [max(float(row[0]), -60.0) if statsType == 8 else float(row[0]) for row in data_rows if row and row[0]]
                            frequencies = [(start_freq_hz / 1e6 + i * 0.1) for i in range(len(values))]
                            all_decoded_data[statsType][subBandId] = {'frequencies_mhz': frequencies, 'values': values}
                            step_res.update({'success': True, 'details': f"Collected and decoded {len(values)} points."})
                            task_result_summary['task_results'].append(step_res)
                    logging.info(f"[{mac_address}] Exiting HAL mode...")
                    execute_command_on_shell(shell, '\x04\n', constants.PROMPT_MARKERS['default'], timeout=other_timeout)
                    if any(freq_coef_complex):
                        logging.info(f"[{mac_address}] Performing IFFT to generate time-domain data.")
                        all_decoded_data[2] = {}
                        for subBandId, complex_data in enumerate(freq_coef_complex):
                            if not complex_data: continue
                            
                            time_domain = np.fft.ifft(complex_data)
                            with np.errstate(divide='ignore'):
                                time_domain_db = 20 * np.log10(np.abs(time_domain))
                            time_domain_db[np.isneginf(time_domain_db)] = -100
                            plot_len = len(complex_data) // 2
                            values_td = time_domain_db[:plot_len]

                            distance_ft_shifted = []
                            if plot_len > 0:
                                one_way_time_ns = (np.arange(plot_len) * (5.0 / plot_len) / 2.0) * 1000
                                distance_ft_original = one_way_time_ns * 0.87 * 0.983571056

                                try:
                                    peaks, _ = find_peaks(values_td)
                                    threshold_db = -20.0
                                    first_peak_index = None

                                    # Find the first peak that exceeds the threshold
                                    if peaks.size > 0:
                                        for peak_idx in peaks:
                                            if values_td[peak_idx] > threshold_db:
                                                first_peak_index = peak_idx
                                                break # Stop after finding the first one

                                    if first_peak_index is not None:
                                        distance_shift = distance_ft_original[first_peak_index]
                                        distance_ft_shifted = (distance_ft_original - distance_shift).tolist()
                                        logging.info(f"[{mac_address}] Time-domain plot for sub-band {subBandId} shifted by {distance_shift:.2f} ft (first peak over {threshold_db} dB).")
                                    else:
                                        distance_ft_shifted = distance_ft_original.tolist()
                                        logging.warning(f"[{mac_address}] No peaks found over threshold ({threshold_db} dB) for sub-band {subBandId}. Using un-shifted plot.")
                                
                                except Exception as peak_e:
                                    distance_ft_shifted = distance_ft_original.tolist()
                                    logging.error(f"[{mac_address}] Error during peak detection for sub-band {subBandId}: {peak_e}. Using un-shifted plot.")
                            
                            all_decoded_data[2][subBandId] = {'distance_ft': distance_ft_shifted, 'values_db': values_td.tolist()}
                            
                    generate_ec_html_report(mac_address, all_decoded_data, output_dir)
                    # generate_ec_html_report_matlab(mac_address, all_decoded_data, output_dir)
                    sanitized_mac = mac_address.replace(':', '')
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    json_filename = os.path.join(output_dir, f"{sanitized_mac}_get_ec_data_{timestamp}.json")
                    with open(json_filename, 'w') as f: json.dump(all_decoded_data, f, indent=4)
                    task_result_summary.update({"task_status": "Success", "details": f"EC data and reports generated.", "output_file": json_filename})
                except Exception as e:
                    logging.error(f"[{mac_address}] An error occurred during get_ec task: {e}", exc_info=True)
                    task_result_summary['details'] = str(e)
                    try: execute_command_on_shell(shell, '\x04\n', constants.PROMPT_MARKERS['default'], timeout=other_timeout)
                    except Exception as exit_e: logging.error(f"[{mac_address}] Could not exit HAL mode: {exit_e}")
                logging.info(f"[{mac_address}] --- Task '{task_name}' Complete. ---")
                _check_for_hard_stop(task_name, task_result_summary)
                time.sleep(1)
                continue

            if task_name == 'get_us_psd':
                logging.info(f"[{mac_address}] --- Starting Special Task: {task_name} ---")
                task_result_summary = {"task_status": "Failed", "details": "Task did not complete.", "task_results": []}
                base_response["tasks"][task_name] = task_result_summary
                us_psd_data = {}
                try:
                    us_rlsp = None
                    # --- MODIFIED: Check the local_context first ---
                    if local_context and 'parent_rlsp' in local_context:
                        us_rlsp = local_context.get('parent_rlsp')
                        logging.info(f"[{mac_address}] Using RLSP value from current session's context: {us_rlsp}")
                    elif context and 'parent_rlsp' in context:
                        us_rlsp = context.get('parent_rlsp')
                        logging.info(f"[{mac_address}] Using RLSP value provided from calling context: {us_rlsp}")
                    
                    if us_rlsp is None:
                        us_rlsp = settings.get("RPD_settings", {}).get("US_RLSP")
                        logging.info(f"[{mac_address}] Using default RLSP value from provided settings: {us_rlsp}")

                    if us_rlsp is None: raise ValueError("US_RLSP could not be determined from context or settings.json")
                    
                    target_psd_100khz = float(us_rlsp) - (10 * np.log10(6.4 / 0.1))

                    logging.info(f"[{mac_address}] Target PSD: {target_psd_100khz:.1f} dBmV/100kHz")
                    logging.info(f"[{mac_address}] Entering HAL mode for US PSD data collection...")
                    execute_command_on_shell(shell, 'debug hal\r\nlog_config --off', constants.PROMPT_MARKERS['hal'], timeout=other_timeout, wait_for_prompt=False, delay_before_prompt=1)
                    for subBandId in [0, 1, 2]:
                        remote_path = f"/tmp/EC_8_{subBandId}.dat"
                        local_path = os.path.join(output_dir, f"{mac_address.replace(':', '')}_EC_8_{subBandId}.dat")
                        command = f"ec_pnm_stats 8 {subBandId} {remote_path}"
                        command_output = execute_command_on_shell(shell, command, constants.PROMPT_MARKERS['hal'], wait_for_string="SUCCESS", timeout=other_timeout, wait_for_prompt=False)
                        time.sleep(3.5)
                        step_res = {'command': command, 'raw_output': clean_raw_output(command_output)}
                        if 'SUCCESS' not in command_output:
                            step_res.update({'success': False, 'details': "Command did not return 'SUCCESS'."})
                            task_result_summary['task_results'].append(step_res)
                            continue
                        try:
                            scp_client.get(remote_path, local_path)
                        except SCPException as e:
                            step_res.update({'success': False, 'details': f"SCP failed: {e}"})
                            task_result_summary['task_results'].append(step_res)
                            continue
                        with open(local_path, 'r') as f: content = f.readlines()
                        header_info = {}
                        for line in content:
                            if ':' in line:
                                if match := re.search(r"(\w+):(\d+)", line): header_info[match.group(1)] = int(match.group(2))
                        data_rows = [line.strip().split(',') for line in content if ':' not in line and "PerBin" not in line]
                        values = [max(float(row[0]), -60.0) for row in data_rows if row and row[0]]
                        start_freq_hz = header_info.get('StartFreq', 0)
                        frequencies = [(start_freq_hz / 1e6 + i * 0.1) for i in range(len(values))]
                        us_psd_data[subBandId] = {'frequencies_mhz': frequencies, 'values': values}
                        step_res.update({'success': True, 'details': f"Collected {len(values)} data points."})
                        task_result_summary['task_results'].append(step_res)
                    logging.info(f"[{mac_address}] Exiting HAL mode...")
                    execute_command_on_shell(shell, '\x04\n', constants.PROMPT_MARKERS['default'], timeout=other_timeout)
                    if not us_psd_data: raise Exception("No US PSD data was collected.")
                    
                    all_values = []
                    for subBandId in sorted(us_psd_data.keys()):
                        all_values.extend(us_psd_data[subBandId].get('values', []))
                    if all_values:
                        avg_input_power = sum(all_values) / len(all_values)
                        logging.info(f"[{mac_address}] Average input power: {avg_input_power:.1f} dBmV")
                        # if avg_input_power < -30:
                        if avg_input_power < -70:   #RH
                            logging.error(f"[{mac_address}] Average input power {avg_input_power:.1f} dBmV is below threshold (-30 dBmV). Ending task and script.")
                            task_result_summary['details'] = f"Average input power {avg_input_power:.1f} dBmV is below threshold (-30 dBmV)."
                            task_result_summary['task_status'] = "Failed"
                            raise HardStopException(f"Average input power {avg_input_power:.1f} dBmV is below threshold (-30 dBmV) on device {mac_address}.", mac_address=mac_address)

                    full_freq, full_psd = [], []
                    for subBandId in sorted(us_psd_data.keys()):
                        data = us_psd_data[subBandId]
                        full_freq.extend(data.get('frequencies_mhz', []))
                        full_psd.extend(data.get('values', []))
                    eq_adjust, atten_adjust = analyze_psd_delta(full_freq, full_psd, target_psd_100khz)
                    if eq_adjust is not None and atten_adjust is not None:
                        logging.info(f"[{mac_address}] Suggested EQ adjust: {eq_adjust:.1f} dB, Atten adjust: {atten_adjust:.1f} dB")
                        task_result_summary['analysis'] = {'suggested_eq_db': f"{eq_adjust:.1f}", 'suggested_atten_db': f"{atten_adjust:.1f}"}
                    else:
                        logging.warning(f"[{mac_address}] Could not generate EQ/Attenuation suggestions.")
                    child_mac_for_report = context.get('child_mac') if context else None
                    # html_filename = generate_us_psd_report(mac_address, us_psd_data, target_psd_100khz, output_dir, eq_adjust, atten_adjust, child_mac_address=child_mac_for_report)
                    html_filename = generate_us_psd_report_matlab(mac_address, us_psd_data, target_psd_100khz, output_dir, eq_adjust, atten_adjust, child_mac_address=child_mac_for_report)
                    # --- NEW: Save results to JSON ---
                    sanitized_mac = mac_address.replace(':', '')
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    json_filename_prefix = f"parent_{sanitized_mac}"
                    if child_mac_for_report:
                        sanitized_child = child_mac_for_report.replace(':', '')
                        json_filename_prefix += f"_child_{sanitized_child}"
                    json_filename = os.path.join(output_dir, f"{json_filename_prefix}_get_us_psd_data_{timestamp}.json")
                    
                    json_output_data = {
                        "parent_mac": mac_address,
                        "child_mac": child_mac_for_report,
                        "target_psd_dbmv_100khz": target_psd_100khz,
                        "analysis": task_result_summary.get('analysis', {}),
                        "psd_data": us_psd_data
                    }
                    try:
                        with open(json_filename, 'w') as f:
                            json.dump(json_output_data, f, indent=4)
                        logging.info(f"[{mac_address}] Saved US PSD data to {json_filename}")
                        task_result_summary['output_file'] = json_filename
                    except Exception as e:
                        logging.error(f"[{mac_address}] Failed to save US PSD JSON file: {e}")

                    task_result_summary.update({"task_status": "Success", "details": f"US PSD report generated at {html_filename}"})
                except Exception as e:
                    logging.error(f"[{mac_address}] An error occurred during get_us_psd task: {e}", exc_info=True)
                    task_result_summary['details'] = str(e)
                    try: execute_command_on_shell(shell, '\x04\n', constants.PROMPT_MARKERS['default'], timeout=other_timeout)
                    except Exception as exit_e: logging.error(f"[{mac_address}] Could not exit HAL mode: {exit_e}")
                logging.info(f"[{mac_address}] --- Task '{task_name}' Complete. ---")
                _check_for_hard_stop(task_name, task_result_summary)
                time.sleep(1)
                continue

            if task_name == 'get_clipping':
                logging.info(f"[{mac_address}] --- Starting Special Task: {task_name} ---")
                task_result_summary = {"task_status": "Failed", "details": "Task did not complete.", "task_results": []}
                base_response["tasks"][task_name] = task_result_summary

                def get_clipping_counts(current_shell):
                    """Helper function to run show_fafe and parse all clipping counts."""
                    counts = {}
                    fafe_sequence = copy.deepcopy(command_sequences.get('show_fafe', []))
                    for step in fafe_sequence:
                        output = execute_command_on_shell(
                            current_shell, step['command'], step.get('prompt_marker', constants.PROMPT_MARKERS['default']),
                            wait_for_string=step.get('wait_for_string'), timeout=other_timeout
                        )
                        cleaned_output = clean_raw_output(output)
                        if 'parser' in step:
                            parsed_data = step['parser'](cleaned_output)
                            for core_key, core_data in parsed_data.items():
                                # Standard path for LAFE cores
                                if 'RxClipCount' in core_data:
                                    count_value_str = core_data.get('RxClipCount', '0').split('(')[0].strip()
                                    try:
                                        counts[f"{core_key}_RxClipCount"] = int(count_value_str)
                                    except (ValueError, TypeError):
                                        counts[f"{core_key}_RxClipCount"] = 0
                                
                                # Nested path for FAFE cores (Rx)
                                if 'Rx' in core_data and isinstance(core_data['Rx'], dict) and 'RxClipCount' in core_data['Rx']:
                                    count_value_str = core_data['Rx'].get('RxClipCount', '0').split('(')[0].strip()
                                    try:
                                        counts[f"{core_key}_RxClipCount"] = int(count_value_str)
                                    except (ValueError, TypeError):
                                        counts[f"{core_key}_RxClipCount"] = 0

                                # Nested path for FAFE cores (Nc)
                                if 'Nc' in core_data and isinstance(core_data['Nc'], dict) and 'NcClipCount' in core_data['Nc']:
                                    count_value_str = core_data['Nc'].get('NcClipCount', '0').split('(')[0].strip()
                                    try:
                                        counts[f"{core_key}_NcClipCount"] = int(count_value_str)
                                    except (ValueError, TypeError):
                                        counts[f"{core_key}_NcClipCount"] = 0
                    return counts

                try:
                    clipping_settings = settings.get("clipping_test", {})
                    test_time_sec = clipping_settings.get("test_time", 10)
                    
                    logging.info(f"[{mac_address}] Getting initial clipping counts...")
                    initial_counts = get_clipping_counts(shell)
                    logging.info(f"[{mac_address}] Initial Counts: {initial_counts}")

                    logging.info(f"[{mac_address}] Waiting for {test_time_sec} seconds...")
                    time.sleep(test_time_sec)

                    logging.info(f"[{mac_address}] Getting final clipping counts...")
                    final_counts = get_clipping_counts(shell)
                    logging.info(f"[{mac_address}] Final Counts: {final_counts}")

                    all_keys = sorted(set(initial_counts.keys()) | set(final_counts.keys()))
                    increments = {}
                    log_output = f"\n[{mac_address}] --- Clipping Count Increments (Duration: {test_time_sec}s) ---\n"
                    log_output += f"{'Counter':<35} | {'Initial':>10} | {'Final':>10} | {'Increment':>10}\n"
                    log_output += "-"*80 + "\n"
                    for key in all_keys:
                        initial = initial_counts.get(key, 0)
                        final = final_counts.get(key, 0)
                        increment = final - initial
                        increments[key] = increment
                        log_output += f"{key:<35} | {initial:>10} | {final:>10} | {increment:>10}\n"
                    
                    logging.info(log_output)
                    task_result_summary["details"] = {
                        "duration_seconds": test_time_sec,
                        "initial_counts": initial_counts,
                        "final_counts": final_counts,
                        "increments": increments
                    }
                    task_result_summary["task_status"] = "Success"

                    # --- MODIFICATION: Save clipping results to JSON ---
                    sanitized_mac = mac_address.replace(':', '')
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    json_filename = os.path.join(output_dir, f"{sanitized_mac}_{task_name}_{timestamp}.json")
                    
                    try:
                        with open(json_filename, 'w') as f:
                            json.dump(task_result_summary["details"], f, indent=4)
                        logging.info(f"[{mac_address}] Saved clipping results to {json_filename}")
                        task_result_summary['output_file'] = json_filename
                    except Exception as e:
                        logging.error(f"[{mac_address}] Failed to save clipping results JSON file: {e}")

                except Exception as e:
                    logging.error(f"[{mac_address}] An error occurred during get_clipping task: {e}", exc_info=True)
                    task_result_summary['details'] = str(e)
                    # Ensure we exit HAL mode if an error occurs
                    try:
                        if 'hal' in shell.recv(1024).decode('utf-8', errors='ignore'):
                             execute_command_on_shell(shell, '\x04\n', constants.PROMPT_MARKERS['default'], timeout=other_timeout)
                    except Exception as exit_e:
                        logging.error(f"[{mac_address}] Could not exit HAL mode after clipping test error: {exit_e}")

                logging.info(f"[{mac_address}] --- Task '{task_name}' Complete. ---")
                _check_for_hard_stop(task_name, task_result_summary)
                time.sleep(1)
                continue

            if task_name == 'adjust_north-afe-backoff':
                logging.info(f"[{mac_address}] --- Starting Composite Task: {task_name} ---")
                task_result_summary = {"task_status": "Failed", "details": "Task did not complete.", "sub_task_results": {}}
                base_response["tasks"][task_name] = task_result_summary

                def run_simple_sequence(seq_name, sequence):
                    logging.info(f"[{mac_address}] Running sub-task: {seq_name}")
                    task_result_summary["sub_task_results"][seq_name] = []
                    for step in sequence:
                        try:
                            output = execute_command_on_shell(
                                shell, step['command'],
                                step.get('prompt_marker', constants.PROMPT_MARKERS['default']),
                                timeout=step.get('timeout', other_timeout),
                                wait_for_prompt=step.get('wait_for_prompt', True),
                                delay_before_prompt=step.get('delay_before_prompt')
                            )
                            cleaned_output = clean_raw_output(output)
                            task_result_summary["sub_task_results"][seq_name].append({'command': step['command'], 'raw_output': cleaned_output})
                        except Exception as e:
                            logging.error(f"[{mac_address}] Sub-task {seq_name} failed at command '{step['command']}': {e}")
                            return False
                    return True

                def run_and_get_power_metrics():
                    metrics = {}
                    sequence = copy.deepcopy(command_sequences['get_nc_input_power'])
                    all_parsed_data = {}
                    for step in sequence:
                        output = execute_command_on_shell(shell, step['command'], step.get('prompt_marker', constants.PROMPT_MARKERS['default']), timeout=other_timeout)
                        if 'parser' in step:
                            all_parsed_data.update(step['parser'](clean_raw_output(output)))
                    fafe_data = all_parsed_data.get('FAFE_core_4', {})
                    nc_data = fafe_data.get('Nc', {})
                    def get_db_value(text):
                        if text is None: return None
                        match = re.search(r'\((.*?)\)|([\d\.]+\s*dBmV)', text)
                        if match: return (match.group(1) or match.group(2)).strip()
                        return text.strip()
                    metrics['NcInputPower'] = get_db_value(nc_data.get('NcInputPower'))
                    metrics['AdcNcBackoff'] = get_db_value(fafe_data.get('AdcNcBackoff'))
                    metrics['MeasuredAdcNcBackoff'] = get_db_value(fafe_data.get('MeasuredAdcNcBackoff'))
                    return metrics

                try:
                    logging.info(f"[{mac_address}] Measuring power/backoff before TG start...")
                    before_metrics = run_and_get_power_metrics()

                    if not run_simple_sequence('tg_start', copy.deepcopy(command_sequences['tg_start'])):
                        raise Exception("tg_start sub-task failed.")
                    time.sleep(3)
                    
                    logging.info(f"[{mac_address}] Measuring power/backoff after TG start...")
                    after_metrics = run_and_get_power_metrics()

                    if not run_simple_sequence('tg_stop', copy.deepcopy(command_sequences['tg_stop'])):
                        logging.warning(f"[{mac_address}] tg_stop sub-task failed, but continuing with reporting.")
                    
                    results = {}
                    def parse_db_to_float(s):
                        try: return float(s.lower().replace('dbmv','').replace('db','').strip())
                        except (ValueError, AttributeError, TypeError): return None
                    all_metric_keys = set(before_metrics.keys()) | set(after_metrics.keys())
                    for key in all_metric_keys:
                        before_val, after_val = before_metrics.get(key), after_metrics.get(key)
                        before_str = before_val if before_val is not None else 'N/A'
                        after_str = after_val if after_val is not None else 'N/A'
                        before_float, after_float = parse_db_to_float(before_str), parse_db_to_float(after_str)
                        diff_str = "N/A"
                        if before_float is not None and after_float is not None:
                            diff = after_float - before_float
                            if isinstance(diff, (int, float)): diff_str = f"{diff:.1f} dB"
                        results[key] = {'before': before_str, 'after': after_str, 'difference': diff_str}

                    logging.info(f"[{mac_address}] <<<<< North AFE Backoff Measurement Results >>>>>")
                    log_output = "\n" + "="*85 + "\n" + f"{'Parameter':<25} | {'Before':<20} | {'After':<20} | {'Difference':<15}\n" + "-"*85 + "\n"
                    for key, data in results.items():
                        log_output += f"{key:<25} | {data['before']:<20} | {data['after']:<20} | {data['difference']:<15}\n"
                    log_output += "="*85
                    logging.info(log_output)
                    
                    task_result_summary["details"] = results
                    task_result_summary["task_status"] = "Success"

                    nc_power_diff_str = results.get('NcInputPower', {}).get('difference', 'N/A')
                    nc_power_diff_float = parse_db_to_float(nc_power_diff_str)

                    if nc_power_diff_float is not None:
                        new_backoff_adjust_value = nc_power_diff_float
                        logging.info(f"[{mac_address}] Calculated raw backoff adjustment value: {new_backoff_adjust_value:.1f}")

                        if new_backoff_adjust_value <= 1.0:
                            logging.info(f"[{mac_address}] Backoff adjustment value is less than 1.0. No configuration needed.")
                            task_result_summary["details"]["new_backoff_action"] = f"No action taken (adjustment value {new_backoff_adjust_value:.1f} is < 1.0)."
                        else:
                            prompt = f"PROMPT [{mac_address}] New backoff adjustment is ~{new_backoff_adjust_value:.1f}. Proceed with configuration and reset? (yes/no):"
                            if should_proceed(prompt, settings, "Prompt_before_apply_north-afe-backoff"):
                                logging.info(f"[{mac_address}] Proceeding with configuration. Getting current backoff value...")

                                current_backoff = settings.get("north-afe-backoff", {}).get("backoff", 3.0)

                                unrounded_total = float(current_backoff) + new_backoff_adjust_value
                                new_backoff_total = round(unrounded_total * 2) / 2.0
                                logging.info(f"[{mac_address}] New total backoff will be {new_backoff_total} (Current: {current_backoff} + Adjust: {new_backoff_adjust_value:.1f}, rounded from {unrounded_total:.1f})")

                                backoff_success = False
                                try:
                                    task_result_summary["sub_task_results"]['configure_north-afe-backoff'] = []
                                    temp_backoff_settings = {"backoff": new_backoff_total}
                                    backoff_sequence = copy.deepcopy(command_sequences['configure_north-afe-backoff'])
                                    backoff_sequence[1]['command'] = f"north-afe-backoff {new_backoff_total}"
                                    
                                    sub_task_all_steps_succeeded = True
                                    for step in backoff_sequence:
                                        command = step['command']
                                        logging.info(f"[{mac_address}] Sending command: '{command}'")
                                        output = execute_command_on_shell(shell, step['command'], step.get('prompt_marker', constants.PROMPT_MARKERS['default']), timeout=other_timeout)
                                        cleaned_output = clean_raw_output(output)
                                        step_result = {'command': command, 'success': False, 'details': '', 'raw_output': cleaned_output}
                                        
                                        if 'verifier' in step:
                                            verifier_func, parser_func, settings_section = step['verifier']
                                            is_match, details = verifier_func(parser_func(cleaned_output), settings_section)
                                            step_result.update({'success': is_match, 'details': details if not is_match else "Verification successful."})
                                        elif 'validation_string' in step:
                                            expected = step['validation_string']
                                            validation_passed = (expected is None) or (isinstance(expected, str) and expected in cleaned_output) or \
                                                              (isinstance(expected, list) and any(s in cleaned_output for s in expected))
                                            step_result.update({'success': validation_passed, 'details': "Validation successful." if validation_passed else f"Validation FAILED. Expected: '{expected}'."})
                                        else:
                                            step_result['success'] = True
                                        
                                        if step_result['success']:
                                            logging.info(f"[{mac_address}]   - Step Result: [SUCCESS] | Command: '{command}' | Details: {step_result['details']}")
                                        else:
                                            logging.warning(f"[{mac_address}]   - Step Result: [FAILED] | Command: '{command}' | Details: {step_result['details']}")

                                        task_result_summary["sub_task_results"]['configure_north-afe-backoff'].append(step_result)
                                        if not step_result['success']:
                                            sub_task_all_steps_succeeded = False
                                            break
                                    backoff_success = sub_task_all_steps_succeeded
                                    task_result_summary["details"]["new_backoff_action"] = f"Configuration with new backoff {new_backoff_total} {'succeeded' if backoff_success else 'failed'}."
                                except Exception as sub_e:
                                    logging.error(f"[{mac_address}] Sub-task configure_north-afe-backoff failed with an exception: {sub_e}")
                                
                                if backoff_success:
                                    logging.info(f"[{mac_address}] Backoff configured successfully. Sending reset command.")
                                    shell.send('reset\n')
                                    time.sleep(1)
                                    logging.info(f"[{mac_address}] Reset command sent. This session will now end for this device.")
                                    task_result_summary["details"]["reset_action"] = "Reset command sent."
                                    return mac_address, base_response
                                else:
                                    logging.error(f"[{mac_address}] Skipping reset because backoff configuration failed.")
                                    task_result_summary["details"]["reset_action"] = "Reset skipped due to configuration failure."
                            else:
                                logging.info(f"[{mac_address}] User chose not to proceed. Ending task.")
                                task_result_summary["details"]["new_backoff_action"] = "User aborted configuration."
                    else:
                        logging.warning(f"[{mac_address}] Could not calculate NcInputPower difference. Skipping new backoff configuration.")

                except Exception as e:
                    logging.error(f"[{mac_address}] Composite task {task_name} failed: {e}")
                    task_result_summary["details"] = str(e)
                
                summary_log = [f"\n[{mac_address}] --- Task Summary: {task_name} ---"]
                summary_log.append(f"Overall Status: {task_result_summary.get('task_status', 'Unknown')}")
                if 'before' in task_result_summary.get('details', {}).get('NcInputPower', {}): summary_log.append("- Power Measurement: Success")
                else: summary_log.append("- Power Measurement: Failed or Incomplete")
                backoff_action = task_result_summary.get('details', {}).get('new_backoff_action', 'Not Performed')
                if 'succeeded' in backoff_action: summary_log.append(f"- Backoff Configuration: Success ({backoff_action})")
                elif 'failed' in backoff_action: summary_log.append(f"- Backoff Configuration: Failed ({backoff_action})")
                else: summary_log.append(f"- Backoff Configuration: Skipped ({backoff_action})")
                reset_action = task_result_summary.get('details', {}).get('reset_action', 'Not Performed')
                if 'sent' in reset_action: summary_log.append("- Device Reset: Success (Command Sent)")
                else: summary_log.append(f"- Device Reset: Skipped ({reset_action})")
                summary_log.append("-" * (len(task_name) + 26))
                logging.info("\n".join(summary_log))
                
                logging.info(f"[{mac_address}] --- Task '{task_name}' Complete. ---")
                _check_for_hard_stop(task_name, task_result_summary)
                time.sleep(1)
                continue
            
            if task_name == 'adjust_us-fdx-settings':
                logging.info(f"[{mac_address}] --- Starting Composite Task: {task_name} ---")
                task_result_summary = {"task_status": "Failed", "details": "Task did not complete.", "sub_task_results": {}}
                base_response["tasks"][task_name] = task_result_summary

                if not parent_mac or not parent_ip or parent_ip in ["Not Found", "Error", "Script Not Found"]:
                    error_msg = "Parent MAC/IP not provided or invalid, cannot run this task."
                    logging.error(f"[{mac_address}] {error_msg}")
                    task_result_summary["details"] = error_msg
                    _check_for_hard_stop(task_name, task_result_summary)
                    continue

                def _execute_sequence_on_shell(seq_task_name, sequence, current_shell, current_mac, current_device_type):
                    """Helper to run a command sequence on an already connected shell."""
                    sub_task_summary = {"task_status": "Not Started", "task_results": [], "verification": {}}
                    all_steps_succeeded = True
                    for step in sequence:
                        if 'verifier' in step and step['verifier'][0].__name__ == 'verify_rf_components_config':
                            verifier_func, parser_func, settings_section = step['verifier']
                            dynamic_settings = settings_section.copy()
                            dynamic_settings['device_type'] = current_device_type
                            step['verifier'] = (verifier_func, parser_func, dynamic_settings)
                        
                        command = step['command']
                        logging.info(f"[{current_mac}] Sending command: '{command}'")
                        output = execute_command_on_shell(
                            current_shell, command, step.get('prompt_marker', constants.PROMPT_MARKERS['default']),
                            wait_for_string=step.get('wait_for_string'), timeout=step.get('timeout', other_timeout),
                            wait_for_prompt=step.get('wait_for_prompt', True),
                            delay_before_prompt=step.get('delay_before_prompt')
                        )
                        cleaned_output = clean_raw_output(output)
                        step_result = {'command': command, 'success': False, 'details': '', 'raw_output': cleaned_output}

                        if 'parser' in step:
                            parsed_data = step['parser'](cleaned_output)
                            step_result['success'], step_result['details'] = (True, parsed_data) if parsed_data else (False, "Parsing FAILED.")
                        elif 'validation_string' in step:
                            expected = step['validation_string']
                            validation_passed = (expected is None) or (isinstance(expected, str) and expected in cleaned_output) or \
                                              (isinstance(expected, list) and any(s in cleaned_output for s in expected))
                            step_result['success'], step_result['details'] = (True, "Validation successful.") if validation_passed else (False, f"Validation FAILED. Expected: '{expected}'.")
                        elif 'verifier' in step:
                            verifier_func, parser_func, settings_section = step['verifier']
                            parsed_config = parser_func(cleaned_output)
                            is_match, details = verifier_func(parsed_config, settings_section)
                            step_result.update({'success': is_match, 'details': details if not is_match else "Verification successful."})
                            sub_task_summary['verification'][command] = {'status': 'Success' if is_match else 'Failed', 'details': details}
                        
                        if step_result['success']:
                            logging.info(f"[{current_mac}]   - Step Result: [SUCCESS] | Command: '{command}' | Details: {step_result['details']}")
                        else:
                            logging.warning(f"[{current_mac}]   - Step Result: [FAILED] | Command: '{command}' | Details: {step_result['details']}")

                        sub_task_summary["task_results"].append(step_result)
                        if not step_result['success']:
                            all_steps_succeeded = False
                            break
                    
                    sub_task_summary["task_status"] = "Success" if all_steps_succeeded else "Failed"
                    return sub_task_summary

                try:
                    logging.info(f"[{mac_address}] Step 1: Running tg_start on child device...")
                    tg_start_seq = copy.deepcopy(command_sequences['tg_start'])
                    tg_start_result = _execute_sequence_on_shell('tg_start', tg_start_seq, shell, mac_address, device_type)
                    task_result_summary['sub_task_results']['child_tg_start'] = tg_start_result
                    if tg_start_result.get('task_status') != "Success":
                        raise Exception("Failed to run tg_start on child device.")

                    # --- MODIFIED: Combine parent tasks into a single SSH session ---
                    logging.info(f"[{mac_address}] Step 2: Running 'show_us-profile' and 'get_us_psd' on parent {parent_mac} in one session...")
                    
                    _, parent_response = connect_and_run_tasks(
                        parent_mac, parent_ip, ['show_us-profile', 'get_us_psd'], 
                        command_sequences, settings, constants, 
                        context={'child_mac': mac_address},
                        output_dir=output_dir
                    )
                    
                    show_us_profile_res = parent_response.get("tasks", {}).get("show_us-profile", {})
                    get_us_psd_res = parent_response.get("tasks", {}).get("get_us_psd", {})
                    task_result_summary['sub_task_results']['parent_show_us_profile'] = show_us_profile_res
                    task_result_summary['sub_task_results']['parent_get_us_psd_before'] = get_us_psd_res

                    if show_us_profile_res.get('task_status') != "Success" or get_us_psd_res.get('task_status') != "Success":
                         raise Exception(f"One or more tasks failed on parent device. RLSP Status: {show_us_profile_res.get('task_status')}, PSD Status: {get_us_psd_res.get('task_status')}")

                    analysis = get_us_psd_res.get('analysis', {})
                    eq_adjust = round(float(analysis.get('suggested_eq_db', 0)), 1)
                    atten_adjust = round(float(analysis.get('suggested_atten_db', 0))*2)/2
                    logging.info(f"[{mac_address}] Step 3 & 4: Rounded adjustments -> EQ adjust: {eq_adjust} dB, Atten adjust: {atten_adjust} dB")
                    task_result_summary['analysis'] = {'rounded_eq_adjust': eq_adjust, 'rounded_atten_adjust': atten_adjust}

                    if abs(eq_adjust) > 0.5 or abs(atten_adjust) > 0.5:
                        prompt = f"PROMPT [{mac_address}] Apply changes? EQ adjust: {eq_adjust} dB, Atten adjust: {atten_adjust} dB. (yes/no):"
                        if should_proceed(prompt, settings, "Prompt_before_apply_us-fdx-settings"):
                            logging.info(f"[{mac_address}] Step 5a: Getting current FDX settings from child...")
                            # --- MODIFIED SECTION: Added retry logic for getting module info ---
                            show_info_result = None
                            parsed_module_info = None
                            max_attempts = 3
                            for attempt in range(max_attempts):
                                logging.info(f"[{mac_address}] Attempting to get module info (Attempt {attempt + 1}/{max_attempts})...")
                                show_info_seq = copy.deepcopy(command_sequences['showModuleInfo'])
                                temp_result = _execute_sequence_on_shell('showModuleInfo', show_info_seq, shell, mac_address, device_type)
                                
                                # Check if parsing was successful and required keys are present
                                if temp_result.get('task_status') == "Success":
                                    parsed_data = temp_result['task_results'][0].get('details', {})
                                    if parsed_data.get('US FDX Atten') is not None and parsed_data.get('US FDX Eq') is not None:
                                        show_info_result = temp_result
                                        parsed_module_info = parsed_data
                                        logging.info(f"[{mac_address}] Successfully retrieved and parsed module info.")
                                        break # Success, exit the loop
                                
                                if attempt < max_attempts - 1:
                                    logging.warning(f"[{mac_address}] Failed to get valid module info. Retrying in 3 seconds...")
                                    time.sleep(3)
                                else:
                                    logging.error(f"[{mac_address}] Failed to get valid module info after {max_attempts} attempts.")
                                    show_info_result = temp_result # Store the last failed result for logging
                            
                            task_result_summary['sub_task_results']['child_showModuleInfo'] = show_info_result
                            if not parsed_module_info:
                                raise Exception("Failed to get module info from child after multiple retries.")
                            # --- END MODIFIED SECTION ---

                            current_atten = float(parsed_module_info.get('US FDX Atten', 0))
                            current_eq = float(parsed_module_info.get('US FDX Eq', 0))
                            logging.info(f"[{mac_address}] Current values -> EQ: {current_eq}, Atten: {current_atten}")

                            new_eq = current_eq + eq_adjust
                            new_atten = current_atten + atten_adjust
                            logging.info(f"[{mac_address}] Step 5b: Calculated new values -> EQ: {new_eq:.1f}, Atten: {new_atten:.1f}")

                            final_eq, final_atten = max(0.0, min(new_eq, 15.0)), max(0.0, min(new_atten, 31.5))
                            if final_eq != new_eq: logging.warning(f"[{mac_address}] US FDX EQ value {new_eq:.1f} clamped to {final_eq:.1f}.")
                            if final_atten != new_atten: logging.warning(f"[{mac_address}] US FDX Atten value {new_atten:.1f} clamped to {final_atten:.1f}.")
                            
                            logging.info(f"[{mac_address}] Final values to be applied -> EQ: {final_eq:.1f}, Atten: {final_atten:.1f}")
                            task_result_summary['new_values'] = {'new_eq': f"{final_eq:.1f}", 'new_atten': f"{final_atten:.1f}"}

                            logging.info(f"[{mac_address}] Step 5c: Applying new values to child...")
                            configure_sequence = [
                                {'command': "rf-components", 'validation_string': None},
                                {'command': f"us-fdx-atten {final_atten:.1f}", 'validation_string': 'is set from'},
                                {'command': f"us-fdx-eq {final_eq:.1f}", 'validation_string': 'is set from'},
                                {'command': 'exit', 'validation_string': None}
                            ]
                            config_result = _execute_sequence_on_shell('configure_rf_components', configure_sequence, shell, mac_address, device_type)
                            task_result_summary['sub_task_results']['child_configure_rf_components'] = config_result
                            if config_result.get('task_status') != "Success":
                                raise Exception("Failed to configure new RF components on child.")

                            logging.info(f"[{mac_address}] Step 5d: Running get_us_psd on parent device again...")
                            # --- MODIFIED: Get RLSP from previous parent run to pass to the second run ---
                            parent_rlsp = None
                            if show_us_profile_res.get('task_status') == "Success":
                                for step in show_us_profile_res.get('task_results', []):
                                    if step.get('command') == 'show configuration' and isinstance(step.get('details'), dict):
                                        parent_rlsp = step.get('details', {}).get('rlsp')
                                        break
                            if parent_rlsp is None:
                                logging.warning(f"[{mac_address}] Could not re-verify RLSP for second PSD run, will use default/previous.")

                            _, parent_after_response = connect_and_run_tasks(
                                parent_mac, parent_ip, ['get_us_psd'], 
                                command_sequences, settings, constants, 
                                context={'child_mac': mac_address, 'parent_rlsp': parent_rlsp},
                                output_dir=output_dir
                            )
                            get_psd_after_result = parent_after_response.get("tasks", {}).get("get_us_psd", {})
                            task_result_summary['sub_task_results']['parent_get_us_psd_after'] = get_psd_after_result
                            task_result_summary['task_status'] = "Success"
                        else:
                            logging.info(f"[{mac_address}] Step 6: User chose not to apply changes.")
                            task_result_summary.update({'details': "User aborted adjustment.", 'task_status': "Success"})
                    else:
                        logging.info(f"[{mac_address}] No adjustments needed (EQ adjust: {eq_adjust}, Atten adjust: {atten_adjust}).")
                        task_result_summary.update({'details': "No adjustments needed.", 'task_status': "Success"})
                
                except Exception as e:
                    logging.error(f"[{mac_address}] Composite task {task_name} failed: {e}", exc_info=True)
                    task_result_summary["details"] = str(e)
                
                finally:
                    logging.info(f"[{mac_address}] Step 7: Running tg_stop on child device...")
                    tg_stop_seq = copy.deepcopy(command_sequences['tg_stop'])
                    tg_stop_result = _execute_sequence_on_shell('tg_stop', tg_stop_seq, shell, mac_address, device_type)
                    task_result_summary['sub_task_results']['child_tg_stop'] = tg_stop_result
                
                summary_log = [f"\n[{mac_address}] --- Task Summary: {task_name} ---"]
                summary_log.append(f"Overall Status: {task_result_summary.get('task_status', 'Unknown')}")
                def get_subtask_status(sub_task_name):
                    sub_task = task_result_summary.get('sub_task_results', {}).get(sub_task_name, {})
                    return sub_task.get('task_status', 'Not Performed')
                summary_log.append(f"- Child Device tg_start: {get_subtask_status('child_tg_start')}")
                summary_log.append(f"- Parent Device PSD Measurement (Before): {get_subtask_status('parent_get_us_psd_before')}")
                config_status = get_subtask_status('child_configure_rf_components')
                if 'new_values' not in task_result_summary and config_status == 'Not Performed':
                    config_details = "Skipped (No changes needed or user aborted)"
                else: config_details = config_status
                summary_log.append(f"- Child Device Configuration: {config_details}")
                summary_log.append(f"- Parent Device PSD Measurement (After): {get_subtask_status('parent_get_us_psd_after')}")
                summary_log.append(f"- Child Device tg_stop: {get_subtask_status('child_tg_stop')}")
                summary_log.append("-" * (len(task_name) + 26))
                logging.info("\n".join(summary_log))
                
                logging.info(f"[{mac_address}] --- Task '{task_name}' Complete. ---")
                _check_for_hard_stop(task_name, task_result_summary)
                time.sleep(1)
                continue

            if task_name == 'adjust_rlsp_diff':
                logging.info(f"[{mac_address}] --- Starting Composite Task: {task_name} ---")
                task_result_summary = {"task_status": "Failed", "details": "Task did not complete.", "sub_task_results": {}}
                base_response["tasks"][task_name] = task_result_summary

                def _execute_sequence(seq_task_name, sequence):
                    """
                    Helper to run a command sequence with retries on parsing failure.
                    Returns a dictionary of parsed data if all steps and parsers succeed.
                    Returns None if any step fails.
                    """
                    task_result_summary["sub_task_results"][seq_task_name] = []
                    all_steps_succeeded = True
                    parsed_data_for_sequence = {}

                    for step in sequence:
                        command = step['command']
                        max_attempts = 3 if 'parser' in step else 1
                        step_result = {}
                        
                        for attempt in range(max_attempts):
                            attempt_log = f" (Attempt {attempt + 1}/{max_attempts})" if max_attempts > 1 else ""
                            logging.info(f"[{mac_address}] Sending command for '{seq_task_name}': '{command}'{attempt_log}")
                            
                            parse_was_successful = True

                            try:
                                output = execute_command_on_shell(
                                    shell, command, step.get('prompt_marker', constants.PROMPT_MARKERS['default']),
                                    wait_for_string=step.get('wait_for_string'), timeout=step.get('timeout', other_timeout),
                                    wait_for_prompt=step.get('wait_for_prompt', True),
                                    delay_before_prompt=step.get('delay_before_prompt')
                                )
                                cleaned_output = clean_raw_output(output)
                                step_result = {'command': command, 'success': False, 'details': '', 'raw_output': cleaned_output}

                                if 'parser' in step:
                                    parsed_data = step['parser'](cleaned_output)
                                    if parsed_data:
                                        step_result['success'] = True
                                        step_result['details'] = parsed_data
                                        parsed_data_for_sequence.update(parsed_data)
                                    else:
                                        parse_was_successful = False
                                        step_result['success'] = False
                                        step_result['details'] = "Parsing FAILED."
                                elif 'validation_string' in step:
                                    expected = step['validation_string']
                                    validation_passed = (expected is None) or (isinstance(expected, str) and expected in cleaned_output) or \
                                                        (isinstance(expected, list) and any(s in cleaned_output for s in expected))
                                    step_result['success'] = validation_passed
                                    step_result['details'] = "Validation successful." if validation_passed else f"Validation FAILED. Expected: '{expected}'."
                                else:
                                    step_result['success'] = True
                            
                            except Exception as e:
                                logging.error(f"[{mac_address}] Step failed for command '{command}' with exception: {e}")
                                step_result = {'command': command, 'success': False, 'details': f"Exception during execution: {e}", 'raw_output': locals().get('cleaned_output', '')}
                                parse_was_successful = False

                            if parse_was_successful:
                                break
                            
                            if not parse_was_successful and attempt < max_attempts - 1:
                                wait_time = (attempt + 1) * 2
                                logging.warning(f"[{mac_address}] Parsing failed for '{command}'. Retrying in {wait_time} seconds...")
                                time.sleep(wait_time)
                        
                        task_result_summary["sub_task_results"][seq_task_name].append(step_result)
                        
                        if not step_result.get('success', False):
                            all_steps_succeeded = False
                            break
                    
                    if all_steps_succeeded:
                        return parsed_data_for_sequence
                    else:
                        return None

                try:
                    # 1. read the RPD RLSP setting from settings json file: RPD_settings \ US_RLSP as A.
                    rpd_settings = settings.get("RPD_settings", {})
                    rpd_rlsp_A = rpd_settings.get("US_RLSP")
                    if rpd_rlsp_A is None:
                        raise ValueError("US_RLSP not found in RPD_settings in the settings file.")
                    logging.info(f"[{mac_address}] Step 1: RPD RLSP (A) from settings: {rpd_rlsp_A}")
                    task_result_summary['details'] = {'step1_rpd_rlsp_A': rpd_rlsp_A}

                    # 2. read the Amp RLSP setting with task "show_us-profile" as B.
                    logging.info(f"[{mac_address}] Step 2: Reading Amp RLSP (B) using 'show_us-profile'")
                    show_us_profile_seq = copy.deepcopy(command_sequences['show_us-profile'])
                    us_profile_data = _execute_sequence('show_us-profile', show_us_profile_seq)
                    
                    if us_profile_data is None or 'rlsp' not in us_profile_data:
                        raise ValueError("Failed to retrieve or parse Amp RLSP from 'show_us-profile'.")
                    amp_rlsp_B = us_profile_data['rlsp']
                    logging.info(f"[{mac_address}] Step 2: Amp RLSP (B) found: {amp_rlsp_B}")
                    task_result_summary['details']['step2_amp_rlsp_B'] = amp_rlsp_B

                    # 3. derive the difference between RPD RLSP and Amp RLSP as X = A - B.
                    diff_X = float(rpd_rlsp_A) - float(amp_rlsp_B)
                    logging.info(f"[{mac_address}] Step 3: Calculated difference (X = A - B): {diff_X:.1f}")
                    task_result_summary['details']['step3_diff_X'] = f"{diff_X:.1f}"

                    # 4. read the Amp current us-fdx-atten with task "showModuleInfo" as Y.
                    logging.info(f"[{mac_address}] Step 4: Reading current us-fdx-atten (Y) and eq using 'showModuleInfo'")
                    show_module_info_seq = copy.deepcopy(command_sequences['showModuleInfo'])
                    module_info_data = _execute_sequence('showModuleInfo', show_module_info_seq)
                    if module_info_data is None or 'US FDX Atten' not in module_info_data or 'US FDX Eq' not in module_info_data:
                        raise ValueError("Failed to retrieve or parse 'US FDX Atten' or 'US FDX Eq' from 'showModuleInfo'.")
                    
                    current_atten_Y = float(module_info_data['US FDX Atten'])
                    current_eq = float(module_info_data['US FDX Eq'])
                    logging.info(f"[{mac_address}] Step 4: Current us-fdx-atten (Y) found: {current_atten_Y}")
                    logging.info(f"[{mac_address}] Step 4: Current us-fdx-eq found: {current_eq}")
                    task_result_summary['details']['step4_current_atten_Y'] = current_atten_Y
                    task_result_summary['details']['step4_current_eq'] = current_eq
                    
                    # 5. derive the the new value Z = Y - X
                    new_atten_Z = current_atten_Y - diff_X
                    logging.info(f"[{mac_address}] Step 5: Calculated new us-fdx-atten based on RLSP diff (Z = Y - X): {new_atten_Z:.1f}")
                    task_result_summary['details']['step5_new_atten_Z_unrounded'] = f"{new_atten_Z:.1f}"
                    
                    # --- Start of new DS Profile Adjustment Logic ---
                    logging.info(f"[{mac_address}] --- Starting DS Profile Adjustment ---")
                    
                    # 1a & 1b: Get RPD DS settings and calculate power levels
                    ds_rpd_settings = rpd_settings
                    if not all(k in ds_rpd_settings for k in ["DS_BasePower", "DS_TiltMaximumFrequency", "DS_TiltValue"]):
                        raise ValueError("Missing required DS settings in RPD_settings of settings file.")
                    
                    rpd_max_freq = float(ds_rpd_settings["DS_TiltMaximumFrequency"])
                    rpd_min_freq = 108000000.0
                    rpd_power_at_max = ds_rpd_settings["DS_BasePower"] / 10.0 # From settings, value is 10x
                    rpd_power_at_min = rpd_power_at_max - (ds_rpd_settings["DS_TiltValue"] / 10.0)
                    logging.info(f"[{mac_address}] RPD DS Profile: Power at {rpd_min_freq/1e6:.1f} MHz = {rpd_power_at_min:.1f} dBmV, Power at {rpd_max_freq/1e6:.1f} MHz = {rpd_power_at_max:.1f} dBmV")

                    # 2a: Get current DS profile from Amp
                    logging.info(f"[{mac_address}] Reading Amp DS profile using 'show_ds-profile'")
                    show_ds_profile_seq = copy.deepcopy(command_sequences['show_ds-profile'])
                    ds_profile_data = _execute_sequence('show_ds-profile', show_ds_profile_seq)
                    if ds_profile_data is None:
                        raise ValueError("Failed to retrieve or parse Amp DS profile from 'show_ds-profile'.")

                    # 2b: Derive Amp's power levels
                    amp_start_freq = float(ds_profile_data["start-freq"])
                    amp_end_freq = float(ds_profile_data["end-freq"])
                    amp_start_power = float(ds_profile_data["start-power"])
                    amp_end_power = float(ds_profile_data["end-power"])
                    
                    # Calculate slope and intercept for the Amp's power line
                    if (amp_end_freq - amp_start_freq) == 0: raise ValueError("Amp DS profile start and end frequencies are the same.")
                    m_amp = (amp_end_power - amp_start_power) / (amp_end_freq - amp_start_freq)
                    b_amp = amp_start_power - (m_amp * amp_start_freq)
                    
                    def get_amp_power_at_freq(freq):
                        return (m_amp * freq) + b_amp

                    amp_power_at_rpd_min = get_amp_power_at_freq(rpd_min_freq)
                    amp_power_at_rpd_max = get_amp_power_at_freq(rpd_max_freq)
                    logging.info(f"[{mac_address}] Amp DS Profile (calculated at RPD points): Power at {rpd_min_freq/1e6:.1f} MHz = {amp_power_at_rpd_min:.1f} dBmV, Power at {rpd_max_freq/1e6:.1f} MHz = {amp_power_at_rpd_max:.1f} dBmV")
                    
                    # 3. Compare levels and derive adjustments
                    atten_adj_X = amp_power_at_rpd_min - rpd_power_at_min
                    diff_at_max = amp_power_at_rpd_max - rpd_power_at_max
                    eq_adj_Y = atten_adj_X - diff_at_max
                    logging.info(f"[{mac_address}] Calculated raw adjustments: Atten (X) = {atten_adj_X:.1f} dB, EQ (Y) = {eq_adj_Y:.1f} dB")

                    # 4. Scale the adjustment values
                    scale_factor = (684.0 - 108.0) / (1218.0 - 108.0)
                    scaled_eq_adj = eq_adj_Y * scale_factor
                    scaled_atten_adj = atten_adj_X - scaled_eq_adj * 0.75
                    logging.info(f"[{mac_address}] Scaled adjustments: Atten = {scaled_atten_adj:.1f} dB, EQ = {scaled_eq_adj:.1f} dB")
                    task_result_summary['details']['ds_profile_adj'] = {'atten_adj_scaled': f"{scaled_atten_adj:.1f}", 'eq_adj_scaled': f"{scaled_eq_adj:.1f}"}

                    # 5. Apply these two new adjustments
                    # First, combine with RLSP-based adjustment for attenuation
                    final_unrounded_atten = new_atten_Z + scaled_atten_adj 
                    final_unrounded_eq = current_eq + scaled_eq_adj
                    
                    logging.info(f"[{mac_address}] Combined adjustments (unrounded): Atten = {final_unrounded_atten:.1f}, EQ = {final_unrounded_eq:.1f}")

                    # Round final values
                    rounded_atten = round(final_unrounded_atten * 2) / 2.0
                    rounded_eq = round(final_unrounded_eq * 10) / 10.0

                    # Clamp the final values to their allowed ranges
                    final_atten = max(0.0, min(31.5, rounded_atten))
                    final_eq = max(0.0, min(15.0, rounded_eq))

                    if final_atten != rounded_atten:
                        logging.warning(f"[{mac_address}] Final Atten value {rounded_atten:.1f} was out of bounds [0.0, 31.5]. Clamping to {final_atten:.1f}.")
                    if final_eq != rounded_eq:
                        logging.warning(f"[{mac_address}] Final EQ value {rounded_eq:.1f} was out of bounds [0.0, 15.0]. Clamping to {final_eq:.1f}.")
                    
                    logging.info(f"[{mac_address}] Final values to be set: us-fdx-atten = {final_atten:.1f}, us-fdx-eq = {final_eq:.1f}")
                    task_result_summary['details']['final_values_to_set'] = {'atten': f"{final_atten:.1f}", 'eq': f"{final_eq:.1f}"}

                    # 6. set the new us-fdx-atten and us-fdx-eq values
                    set_final_values_seq = [
                        {'command': "rf-components", 'validation_string': None},
                        {'command': f"us-fdx-atten {final_atten:.1f}", 'validation_string': 'is set from'},
                        {'command': f"us-fdx-eq {final_eq:.1f}", 'validation_string': 'is set from'},
                        {'command': 'exit', 'validation_string': None}
                    ]
                    
                    set_result = _execute_sequence('set_final_values', set_final_values_seq)
                    if set_result is None: # Helper returns None on failure
                        raise ValueError("Failed to execute command to set final atten/eq values.")
                    
                    logging.info(f"[{mac_address}] Successfully set new us-fdx-atten and us-fdx-eq values.")
                    task_result_summary['task_status'] = "Success"
                    task_result_summary['details']['final_result'] = "Success"

                except Exception as e:
                    logging.error(f"[{mac_address}] Composite task {task_name} failed: {e}", exc_info=True)
                    task_result_summary["details"] = str(e)

                _log_generic_task_summary(task_name, task_result_summary)
                _check_for_hard_stop(task_name, task_result_summary)
                time.sleep(1)
                continue

            if task_name == 'get_wbfft':
                logging.info(f"[{mac_address}] --- Starting Special Task: {task_name} ---")
                task_result_summary = {"task_status": "Failed", "details": "Task did not complete.", "task_results": []}
                base_response["tasks"][task_name] = task_result_summary
                local_files = {} 
                try:
                    sanitized_mac = mac_address.replace(':', '')
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

                    logging.info(f"[{mac_address}] Stage 1: Collecting HAL gains...")
                    gain_sequence = command_sequences.get('get_wbfft_hal_gains', [])
                    hal_output = ""
                    for step in gain_sequence:
                        hal_output += execute_command_on_shell(shell, step['command'], step['prompt_marker'], wait_for_string=step.get('wait_for_string'), timeout=other_timeout, delay_before_prompt=1.0)
                    
                    cleaned_hal_output = clean_raw_output(hal_output)
                    task_result_summary['task_results'].append({'command': 'get_wbfft_hal_gains', 'raw_output': cleaned_hal_output, 'success': True})
                    
                    logging.info(f"[{mac_address}] Stage 2: Running WBFFT captures...")
                    execute_command_on_shell(shell, 'debug hal\r\nlog_config --off', constants.PROMPT_MARKERS['hal'], wait_for_string="Connected", timeout=other_timeout, wait_for_prompt=False, delay_before_prompt=1.0)

                    remote_files_to_get, local_wbfft_paths = {}, {}
                    wbfft_settings = constants.WBFFT_SETTINGS
                    
                    for m_name, m_config in constants.WBFFT_MEASUREMENT_CONFIGS.items():
                        logging.info(f"[{mac_address}]  - Starting capture for: {m_name} (ADC: {m_config['adcSelect']})")
                        wbfft_config_cmd = (f"/wbfft/configuration startFreq {wbfft_settings['startFreq']} endFreq {wbfft_settings['endFreq']} "
                                            f"outputFormat {wbfft_settings['outputFormat']} outputScale {wbfft_settings['outputScale']} fftSize {wbfft_settings['fftSize']} "
                                            f"windowMode {wbfft_settings['windowMode']} averagingMode {wbfft_settings['averagingMode']} "
                                            f"samplingRate {wbfft_settings['samplingRate']} adcSelect {m_config['adcSelect']} "
                                            f"runDuration {wbfft_settings['runDuration']} triggerCount {wbfft_settings['triggerCount']} "
                                            f"aggrPeriod {wbfft_settings['aggrPeriod']}")
                        execute_command_on_shell(shell, wbfft_config_cmd, constants.PROMPT_MARKERS['hal'], wait_for_string="Success", timeout=other_timeout, delay_before_prompt=step.get('delay_before_prompt'))
                        
                        remote_wbfft_base = f"/tmp/WBFFT_{m_name}"
                        execute_command_on_shell(shell, f"/wbfft/start_capture 59.5 {remote_wbfft_base}", constants.PROMPT_MARKERS['hal'], wait_for_string="Success", timeout=other_timeout, delay_before_prompt=step.get('delay_before_prompt'))
                        time.sleep(1)

                        local_wbfft_base = os.path.join(output_dir, f"WBFFT_{m_config['output_prefix']}_{sanitized_mac}")
                        local_wbfft_paths[m_name] = local_wbfft_base
                        remote_files_to_get[remote_wbfft_base] = f"{local_wbfft_base}.dat"
                        remote_files_to_get[f"{remote_wbfft_base}.config"] = f"{local_wbfft_base}.config"

                    logging.info(f"[{mac_address}] Stage 3: Building list of calibration files to download...")
                    all_s2p_keys = set(key for cfg in constants.WBFFT_MEASUREMENT_CONFIGS.values() for key in cfg['s2p_keys'])
                    for s2p_key in all_s2p_keys:
                        s2p_file = constants.S2P_FILES.get(s2p_key)
                        if not s2p_file: continue
                        remote_path = os.path.join(constants.WBFFT_REMOTE_PATHS['s2p_remote_path'], s2p_file).replace("\\", "/")
                        original_basename = os.path.basename(s2p_file)
                        prefixed_local_path = os.path.join(output_dir, f"{sanitized_mac}_{original_basename}")
                        remote_files_to_get[remote_path] = prefixed_local_path

                    all_comp_keys = set(key for cfg in constants.WBFFT_MEASUREMENT_CONFIGS.values() for key in cfg['add_comp_keys'])
                    for comp_key in all_comp_keys:
                        comp_file = constants.COMP_FILES.get(comp_key)
                        if not comp_file: continue
                        remote_path = os.path.join(constants.WBFFT_REMOTE_PATHS['additional_comp_remote_path'], comp_file).replace("\\", "/")
                        original_basename = os.path.basename(comp_file)
                        prefixed_local_path = os.path.join(output_dir, f"{sanitized_mac}_{original_basename}")
                        remote_files_to_get[remote_path] = prefixed_local_path
                    
                    execute_command_on_shell(shell, '\x04\n', constants.PROMPT_MARKERS['default'], timeout=other_timeout)
                    
                    logging.info(f"[{mac_address}] Stage 4: Downloading {len(remote_files_to_get)} files via SCP...")
                    for remote, local in remote_files_to_get.items():
                        try:
                            logging.info(f"[{mac_address}]  - Downloading {remote} to {local}")
                            scp_client.get(remote, local)
                            local_files[remote] = local
                        except SCPException as e:
                            logging.error(f"[{mac_address}] Failed to download {remote}: {e}")
                            raise Exception(f"SCP failed for {remote}")
                    
                    logging.info(f"[{mac_address}] Stage 5: Post-processing all measurements...")
                    processed_dfs = process_wbfft_data(local_wbfft_paths, cleaned_hal_output, constants, output_dir, sanitized_mac=sanitized_mac)
                    if not processed_dfs:
                        raise Exception("WBFFT post-processing failed to produce data.")

                    final_df = processed_dfs[0]
                    for i in range(1, len(processed_dfs)):
                        final_df = pd.merge(final_df, processed_dfs[i], on='Frequency', how='outer')
                    final_df = final_df.sort_values(by='Frequency').reset_index(drop=True)
                    
                    logging.info(f"[{mac_address}] Stage 6: Calculating channel power...")
                    power_results_list = calculate_channel_power(final_df, constants.WBFFT_CHANNEL_DEFINITIONS)
                    
                    if not power_results_list:
                        logging.warning(f"[{mac_address}] Channel power calculation did not produce results.")
                    
                    logging.info(f"[{mac_address}] Stage 7: Generating final reports...")
                    json_path = os.path.join(output_dir, f"{sanitized_mac}_get_wbfft_data_{timestamp}.json")
                    final_df.to_json(json_path, orient='records')
                    
                    if power_results_list:
                        power_json_path = os.path.join(output_dir, f"{sanitized_mac}_get_wbfft_channel_power_{timestamp}.json")
                        with open(power_json_path, 'w') as f:
                            json.dump(power_results_list, f, indent=4)
                        logging.info(f"[{mac_address}] Saved channel power data to {power_json_path}")
                        task_result_summary['channel_power_file'] = power_json_path

                    html_path = generate_wbfft_report(mac_address, final_df, power_results_list, output_dir)
                    task_result_summary.update({
                        "task_status": "Success", 
                        "details": "Successfully completed WBFFT analysis.",
                        "output_file": json_path,
                        "report_file": html_path
                    })

                except Exception as e:
                    logging.error(f"[{mac_address}] An error occurred during get_wbfft task: {e}", exc_info=True)
                    task_result_summary['details'] = str(e)
                    try: 
                        if 'hal' in shell.recv(1024).decode('utf-8', errors='ignore'):
                            execute_command_on_shell(shell, '\x04\n', constants.PROMPT_MARKERS['default'], timeout=other_timeout)
                    except Exception as exit_e: 
                        logging.error(f"[{mac_address}] Could not exit HAL mode: {exit_e}")

                logging.info(f"[{mac_address}] --- Task '{task_name}' Complete. ---")
                _check_for_hard_stop(task_name, task_result_summary)
                time.sleep(1)
                continue
            
            elif task_name == 'run_alignment':
                logging.info(f"[{mac_address}] --- Starting Special Task: {task_name} ---")
                task_result_summary = {"task_status": "Not Started", "task_results": []}
                base_response["tasks"][task_name] = task_result_summary

                alignment_settings = settings.get("alignment", {})
                atten_threshold = alignment_settings.get("atten_adjust_threshold", 3.0)
                eq_threshold = alignment_settings.get("eq_adjust_threshold", 3.0)
                auto_proceed_on_threshold = alignment_settings.get("prompt_if_adjust_out-of-range", False)

                temp_settings_for_prompt = {
                    "General settings": {"prompt_key": auto_proceed_on_threshold}
                }

                sequence = copy.deepcopy(command_sequences.get(task_name, []))
                all_steps_succeeded = True
                task_cancelled_by_user = False

                for step in sequence:
                    command = step['command']
                    wait_string = step.get('wait_for_string')
                    timeout = step.get('timeout', other_timeout)
                    prompt_marker = step.get('prompt_marker', constants.PROMPT_MARKERS['default'])
                    
                    step_result = {}
                    try:
                        logging.info(f"[{mac_address}] Sending command: '{command}'")
                        output = execute_command_on_shell(
                            shell, command, prompt_marker,
                            wait_for_string=wait_string, timeout=timeout
                        )
                        cleaned_output = clean_raw_output(output)
                        step_result = {'command': command, 'success': False, 'details': '', 'raw_output': cleaned_output}

                        if 'validation_string' in step:
                            expected = step['validation_string']
                            validation_passed = (expected is None) or \
                                                (isinstance(expected, str) and expected in cleaned_output) or \
                                                (isinstance(expected, list) and any(s in cleaned_output for s in expected))
                            step_result['success'] = validation_passed
                            step_result['details'] = "Validation successful." if validation_passed else f"Validation FAILED. Expected: '{expected}'."
                        else:
                            step_result['success'] = True

                        if not step_result['success']:
                            all_steps_succeeded = False
                            task_result_summary["task_results"].append(step_result)
                            break
                        
                        adjustment_val, threshold, adj_type_str = None, 0.0, ""
                        if command == 'start-ds1':
                            adjustment_val = parsers.parse_alignment_adjustment(cleaned_output, 'eq')
                            threshold, adj_type_str = eq_threshold, "EQ"
                        elif command == 'start-ds2':
                            adjustment_val = parsers.parse_alignment_adjustment(cleaned_output, 'atten')
                            threshold, adj_type_str = atten_threshold, "Attenuation"

                        if adjustment_val is not None:
                            log_msg = f"Proposed {adj_type_str} adjustment: {adjustment_val:.1f} dB"
                            #logging.info(f"[{mac_address}] {log_msg}")
                            step_result['details'] = log_msg
                            
                            if abs(adjustment_val) > threshold:
                                warning_msg = f"WARNING: {adj_type_str} adjustment ({adjustment_val:.1f} dB) exceeds threshold of {threshold:.1f} dB."
                                logging.warning(f"[{mac_address}] {warning_msg}")
                                prompt_msg = f"PROMPT [{mac_address}] {warning_msg} Do you want to continue with the alignment? (yes/no)"
                                
                                if not should_proceed(prompt_msg, temp_settings_for_prompt, "prompt_key"):
                                    logging.warning(f"[{mac_address}] User cancelled alignment task.")
                                    all_steps_succeeded = False
                                    task_cancelled_by_user = True
                                    task_result_summary["task_results"].append(step_result)
                                    break
                    
                    except Exception as e:
                        logging.error(f"[{mac_address}] Step failed for command '{command}': {e}")
                        step_result = {'command': command, 'success': False, 'details': str(e), 'raw_output': locals().get('cleaned_output', '')}
                        all_steps_succeeded = False
                        task_result_summary["task_results"].append(step_result)
                        break
                    
                    if step_result['success']:
                        logging.info(f"[{mac_address}]   - Step Result: [SUCCESS] | Command: '{command}' | Details: {step_result['details']}")
                    else:
                        logging.warning(f"[{mac_address}]   - Step Result: [FAILED] | Command: '{command}' | Details: {step_result['details']}")

                    task_result_summary["task_results"].append(step_result)
                
                if task_cancelled_by_user:
                    task_result_summary["task_status"] = "Cancelled"
                    task_result_summary["details"] = "User cancelled due to out-of-range adjustment."
                else:
                    task_result_summary["task_status"] = "Success" if all_steps_succeeded else "Failed"
                
                _log_generic_task_summary(task_name, task_result_summary)
                _check_for_hard_stop(task_name, task_result_summary)
                time.sleep(1)
                continue

            if task_name == 'reset':
                logging.info(f"[{mac_address}] --- Starting Task: {task_name} ---")
                task_result_summary = {"task_status": "Not Started", "task_results": []}
                base_response["tasks"][task_name] = task_result_summary
                prompt = f"PROMPT [{mac_address}] Are you sure you want to reset the device? (yes/no):"
                if should_proceed(prompt, settings, "Prompt_before_apply_reset"):
                    logging.info(f"[{mac_address}] Confirmed reset. Sending command...")
                    try:
                        shell.send('reset\n')
                        time.sleep(1)
                        logging.info(f"[{mac_address}] Reset command sent. This session will now end for this device.")
                        step_result = {'command': 'reset', 'success': True, 'details': 'Reset command sent.'}
                        task_result_summary.update({'task_results': [step_result], 'task_status': "Success"})
                        return mac_address, base_response
                    except Exception as e:
                        step_result = {'command': 'reset', 'success': False, 'details': str(e)}
                        task_result_summary.update({'task_results': [step_result], 'task_status': "Failed"})
                else:
                    logging.info(f"[{mac_address}] User aborted reset.")
                    step_result = {'command': 'reset', 'success': True, 'details': 'User aborted reset.'}
                    task_result_summary.update({'task_results': [step_result], 'task_status': "Success"})
                logging.info(f"[{mac_address}] --- Task '{task_name}' Complete. ---")
                _check_for_hard_stop(task_name, task_result_summary)
                time.sleep(1)
                continue
            
            # --- Default Task Runner ---
            task_result_summary = {"task_status": "Not Started", "task_results": [], "verification": {}}
            base_response["tasks"][task_name] = task_result_summary
            logging.info(f"[{mac_address}] --- Starting Task: {task_name} ---")
            
            all_parsed_data_for_task = {}
            sequence = copy.deepcopy(command_sequences.get(task_name, []))

            if not sequence:
                task_result_summary["task_status"] = f"Error: Task '{task_name}' not defined."
                _check_for_hard_stop(task_name, task_result_summary)
                continue

            all_steps_succeeded = True
            for step in sequence:
                command = step['command']
                
                # --- Retry Logic Start ---
                max_attempts = 3
                # Only apply retries to steps that involve parsing. A verifier step also involves parsing.
                should_retry_on_parse_fail = 'parser' in step or 'verifier' in step
                
                if not should_retry_on_parse_fail:
                    max_attempts = 1 # No retries for simple validation steps

                step_result = {}
                for attempt in range(max_attempts):
                    attempt_log = f" (Attempt {attempt + 1}/{max_attempts})" if max_attempts > 1 else ""
                    logging.info(f"[{mac_address}] Sending command: '{command}'{attempt_log}")
                    
                    output = execute_command_on_shell(
                        shell, command, step.get('prompt_marker', constants.PROMPT_MARKERS['default']),
                        wait_for_string=step.get('wait_for_string'), timeout=step.get('timeout', other_timeout),
                        delay_before_prompt=step.get('delay_before_prompt')
                    )
                    cleaned_output = clean_raw_output(output)
                    step_result = {'command': command, 'success': False, 'details': '', 'raw_output': cleaned_output}
                    
                    parse_was_successful = True # Assume success unless parsing fails

                    if 'parser' in step:
                        parsed_data = step['parser'](cleaned_output)
                        if parsed_data:
                            step_result['success'], step_result['details'] = True, parsed_data
                            all_parsed_data_for_task.update(parsed_data)
                        else:
                            parse_was_successful = False
                            step_result['success'], step_result['details'] = False, "Parsing FAILED."

                    elif 'verifier' in step:
                        verifier_func, parser_func, settings_section = step['verifier']
                        parsed_config = parser_func(cleaned_output)
                        if parsed_config:
                            is_match, details = verifier_func(parsed_config, settings_section)
                            step_result['success'] = is_match
                            step_result['details'] = details if not is_match else "Verification successful."
                            task_result_summary['verification'][command] = {'status': 'Success' if is_match else 'Failed', 'details': details}
                        else:
                            parse_was_successful = False
                            step_result['success'] = False
                            step_result['details'] = "Parsing FAILED before verification."
                    
                    elif 'validation_string' in step:
                        expected = step['validation_string']
                        validation_passed = (expected is None) or \
                                          (isinstance(expected, str) and expected in cleaned_output) or \
                                          (isinstance(expected, list) and any(s in cleaned_output for s in expected))
                        step_result['success'], step_result['details'] = (True, "Validation successful.") if validation_passed else (False, f"Validation FAILED. Expected: '{expected}'.")
                    
                    else:
                        step_result['success'] = True
                    
                    # Decide whether to break or continue the retry loop
                    if parse_was_successful:
                        break # Exit retry loop on successful parse or for non-parsable steps
                    
                    # If parsing failed, handle retry
                    if not parse_was_successful:
                        if attempt < max_attempts - 1:
                            wait_time = (attempt + 1) * 2 # 2s, 4s
                            logging.warning(f"[{mac_address}] Parsing failed for command '{command}'. Retrying in {wait_time} seconds...")
                            time.sleep(wait_time)
                        else:
                            logging.error(f"[{mac_address}] Parsing failed for command '{command}' after {max_attempts} attempts. This step has failed.")
                # --- Retry Logic End ---

                if step_result['success']:
                    logging.info(f"[{mac_address}]   - Step Result: [SUCCESS] | Command: '{command}' | Details: {step_result['details']}")
                else:
                    logging.warning(f"[{mac_address}]   - Step Result: [FAILED] | Command: '{command}' | Details: {step_result['details']}")

                task_result_summary["task_results"].append(step_result)
                if not step_result['success']:
                    all_steps_succeeded = False
                    break
            
            task_result_summary["task_status"] = "Success" if all_steps_succeeded else "Failed"
            
            if task_name.startswith("show_") and all_parsed_data_for_task and all_steps_succeeded:
                sanitized_mac = mac_address.replace(':', '')
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = os.path.join(output_dir, f"{sanitized_mac}_{task_name}_{timestamp}.json")
                try:
                    with open(filename, 'w') as f:
                        json.dump(all_parsed_data_for_task, f, indent=4)
                    logging.info(f"[{mac_address}] Saved parsed data for task '{task_name}' to {filename}")
                    task_result_summary['output_file'] = filename
                except Exception as e:
                    logging.error(f"[{mac_address}] Failed to save parsed data for '{task_name}': {e}")

            # --- NEW: After a task runs, update the local context for the next task in the same session ---
            if task_name == 'show_us-profile' and task_result_summary["task_status"] == "Success":
                for step in task_result_summary.get('task_results', []):
                    if step.get('command') == 'show configuration' and isinstance(step.get('details'), dict):
                        rlsp = step.get('details', {}).get('rlsp')
                        if rlsp:
                            logging.info(f"[{mac_address}] Storing RLSP '{rlsp}' for subsequent tasks in this session.")
                            local_context['parent_rlsp'] = rlsp
                            break

            if task_name in ["show_ds-profile", "show_us-profile"] and all_parsed_data_for_task and all_steps_succeeded:
                update_profile_settings_file(mac_address, all_parsed_data_for_task, task_name, output_dir, file_lock=file_lock)

            logging.info(f"[{mac_address}] --- Task '{task_name}' Complete. ---")
            
            if task_name.startswith('configure_'):
                _log_generic_task_summary(task_name, task_result_summary)

            _check_for_hard_stop(task_name, task_result_summary)
            time.sleep(1)

        return mac_address, base_response
    except HardStopException as e:
        # This block catches HardStopExceptions from deeper functions (like execute_command_on_shell)
        # that don't have the mac_address context. We will now re-raise the exception
        # but with the mac_address attached so the main worker thread knows which device failed.
        logging.critical(f"[{mac_address}] A critical error occurred on {target_hostname}: {e}")
        base_response["tasks"]["error"] = f"A critical error occurred: {e}"
        raise HardStopException(str(e), mac_address=mac_address) from e
    except Exception as e:
        logging.error(f"[{mac_address}] A non-timeout error occurred on {target_hostname}: {e}", exc_info=True)
        base_response["tasks"]["error"] = f"An error occurred: {e}"
        return mac_address, base_response
    finally:
        if scp_client: scp_client.close()
        if shell: shell.close()
        if target_client: target_client.close()
        if jumpbox_client: jumpbox_client.close()
            