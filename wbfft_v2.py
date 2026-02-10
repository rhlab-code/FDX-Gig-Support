

# Example SSH:
# ssh -J svcAutobahn@jump.autobahn.comcast.com admin@2001:0558:6026:0032:912B:2704:46EB:00F4

# Example usage:
#   python wbfft_v2.py --env PROD --task showModuleInfo show_ds-profile show_us-profile show_spectrum show_north-afe-backoff show_rf_componenets get_wbfft get_ec show_fafe --settings amp_settings.json 24:a1:86:1d:da:90

#   python wbfft_v2.py --env PROD --task get_wbfft get_ec show_fafe --settings amp_settings.json 24:a1:86:1d:da:90 --ip 2001:558:6026:32:912b:2704:46eb:f4

#   python wbfft_v2.py 
#   | --env PROD 
#   | --task showModuleInfo show_ds-profile show_us-profile show_spectrum show_north-afe-backoff show_rf_componenets get_wbfft get_ec show_fafe 
#   | --settings amp_settings.json 24:a1:86:16:4d:ec

# Test MACs:
#   24:a1:86:1d:da:90


import argparse
import sys
import os
import json
import logging
import importlib
from datetime import datetime
import time
import threading
import queue
import tkinter as tk

from ssh_manager import connect_and_run_tasks
from utils import get_ip_for_mac, HardStopException, save_gui_as_png
from commands import generate_command_sequences
from status_monitor import StatusMonitor # Import the new monitor class

def setup_logging(output_dir):
    """Sets up file and stream logging to the specified directory."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    log_filename = os.path.join(output_dir, f"workflow_log_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log")
    
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
        
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    file_handler = logging.FileHandler(log_filename)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    
    return log_filename

def update_mac_ip_mapping_file(filepath, mac, ip):
    """
    Reads the mapping file (JSON), removes any old entry for the given MAC,
    and updates the MAC/IP pair.
    """
    mapping = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                mapping = json.load(f)
        except Exception:
            mapping = {}
    mapping[mac] = ip
    with open(filepath, 'w') as f:
        json.dump(mapping, f, indent=2)

def run_schedule_worker(schedule_data, args, settings, constants, command_sequences, status_queue):
    """
    This function runs in a separate thread and executes the main script logic.
    It sends status updates back to the GUI via the status_queue.
    """
    connection_results = {}
    lock = threading.Lock()
    # --- FIX: Create a dedicated lock for file writing operations ---
    profile_file_lock = threading.Lock()
    mapping_filepath = os.path.join(args.output, "mac_ip_mapping.json")
    
    all_macs_in_schedule = set()
    for item in schedule_data.values():
        all_macs_in_schedule.update(item.get('mac', []))

    task_ids = sorted([int(k) for k in schedule_data.keys()])
    start_index = args.start_index if args.start_index is not None else task_ids[0]
    end_index = args.end_index if args.end_index is not None else task_ids[-1]

    # --- Initial GUI State Setup ---
    for i in task_ids:
        for mac in all_macs_in_schedule:
            if start_index <= i <= end_index:
                if mac in schedule_data.get(str(i), {}).get('mac', []):
                    status_queue.put((i, mac, "Waiting"))
                else:
                    # This MAC isn't in this step, mark as skipped for clarity
                    status_queue.put((i, mac, "Skip"))
            else:
                status_queue.put((i, mac, "Skip"))

    try:
        for i in range(start_index, end_index + 1):
            if str(i) not in schedule_data:
                continue
            
            task_info = schedule_data.get(str(i))
            task_list = task_info['task']
            mac_list = task_info['mac']
            
            # If the mac list for the current step is empty (possibly from a previous step's logic), skip it.
            if not mac_list:
                logging.info(f"--- Skipping Schedule Item #{i} as its MAC list is empty. ---")
                continue

            parent_mac_from_schedule = task_info.get('parent-mac')
            note = task_info.get('note', 'No note provided.')

            logging.info(f"\n--- Starting Schedule Item #{i} ---")
            logging.info(f"NOTE: {note}")

            has_wait_task = "wait" in task_list
            runnable_tasks = [t for t in task_list if t != "wait"]

            mac_ip_mapping = {}
            parent_ip = None
            logging.info(f"--- Step 1: Looking up IPs for {len(mac_list)} MACs in schedule item #{i} ---")
            for mac in mac_list:
                status_queue.put((i, mac, "Running")) # Update status to show IP lookup
                ip = get_ip_for_mac(mac, args.env, args.type, args.script_path)
                mac_ip_mapping[mac] = ip
                if ip not in ["Not Found", "Error", "Script Not Found"]:
                    update_mac_ip_mapping_file(mapping_filepath, mac, ip)
            
            if parent_mac_from_schedule:
                logging.info(f"--- Looking up IP for parent MAC: {parent_mac_from_schedule} ---")
                parent_ip = get_ip_for_mac(parent_mac_from_schedule, args.env, args.type, args.script_path)
                logging.info(f"Parent IP found: {parent_ip}")
                if parent_ip not in ["Not Found", "Error", "Script Not Found"]:
                    update_mac_ip_mapping_file(mapping_filepath, parent_mac_from_schedule, parent_ip)
            
            is_parallelizable = runnable_tasks and all(
                t.startswith('show') or t.startswith('get_') for t in runnable_tasks
            )
            
            is_backoff_adjust_step = 'adjust_north-afe-backoff' in runnable_tasks
            all_adjustments_not_needed = False # Flag for skipping wait task

            if is_parallelizable:
                logging.info(f"--- Running tasks in PARALLEL for schedule item #{i}: {runnable_tasks} ---")
                threads = []

                def _parallel_task_runner(mac, ip, tasks, device_idx, total_devs):
                    logging.info(f"Starting parallel thread for {mac} ({ip})")
                    _, result_data = connect_and_run_tasks(
                        mac, ip, tasks, command_sequences, settings, constants,
                        parent_mac=parent_mac_from_schedule, parent_ip=parent_ip,
                        device_index=device_idx, total_devices=total_devs,
                        output_dir=args.output,
                        # --- FIX: Pass the lock to the task runner ---
                        file_lock=profile_file_lock
                    )
                    with lock:
                        connection_results.setdefault(i, {})[mac] = result_data
                    
                    tasks_in_result = result_data.get("tasks", {})
                    all_tasks_passed = not (not result_data.get("connected", False) or "error" in tasks_in_result)
                    if all_tasks_passed:
                        for task_name in tasks:
                            if tasks_in_result.get(task_name, {}).get("task_status") != "Success":
                                all_tasks_passed = False
                                break
                    final_status = "Pass" if all_tasks_passed else "Fail"
                    status_queue.put((i, mac, final_status))
                    logging.info(f"Finished parallel thread for {mac}. Status: {final_status}")

                for j, (mac, ip) in enumerate(mac_ip_mapping.items()):
                    status_queue.put((i, mac, "Running"))
                    thread = threading.Thread(
                        target=_parallel_task_runner,
                        args=(mac, ip, runnable_tasks, j + 1, len(mac_ip_mapping))
                    )
                    threads.append(thread)
                    thread.start()
                
                for thread in threads:
                    thread.join()
                logging.info(f"--- All parallel tasks for schedule item #{i} complete. ---")

            else: # Fallback to sequential execution
                if runnable_tasks:
                    logging.info(f"--- Running tasks SEQUENTIALLY for this item: {runnable_tasks} ---")
                    for j, (mac, ip) in enumerate(mac_ip_mapping.items()):
                        status_queue.put((i, mac, "Running"))
                        device_index = j + 1
                        _, result_data = connect_and_run_tasks(
                            mac, ip, runnable_tasks, command_sequences, settings, constants,
                            parent_mac=parent_mac_from_schedule, parent_ip=parent_ip,
                            device_index=device_index, total_devices=len(mac_ip_mapping),
                            output_dir=args.output
                        )
                        connection_results.setdefault(i, {})[mac] = result_data

                        tasks_in_result = result_data.get("tasks", {})
                        all_tasks_passed = not (not result_data.get("connected", False) or "error" in tasks_in_result)
                        if all_tasks_passed:
                            for task_name in runnable_tasks:
                                if tasks_in_result.get(task_name, {}).get("task_status") != "Success":
                                    all_tasks_passed = False
                                    break
                        final_status = "Pass" if all_tasks_passed else "Fail"
                        status_queue.put((i, mac, final_status))
                else:
                    logging.info("No device tasks to run for this schedule item.")
                    for mac in mac_list:
                        status_queue.put((i, mac, "Skip"))

            # --- NEW: Logic to handle conditional skipping after adjust_north-afe-backoff ---
            if is_backoff_adjust_step:
                logging.info(f"--- Post-processing for 'adjust_north-afe-backoff' step #{i} ---")
                macs_to_skip_in_next_steps = []
                step_results = connection_results.get(i, {})

                for mac in mac_list:
                    mac_result = step_results.get(mac, {})
                    task_details = mac_result.get('tasks', {}).get('adjust_north-afe-backoff', {}).get('details', {})
                    backoff_action = task_details.get('new_backoff_action', '')
                    if "No action taken" in backoff_action:
                        macs_to_skip_in_next_steps.append(mac)
                        logging.info(f"Device {mac} does not need backoff adjustment. It will be skipped in subsequent alignment/adjustment steps.")

                if macs_to_skip_in_next_steps:
                    all_adjustments_not_needed = len(macs_to_skip_in_next_steps) == len(mac_list)
                    
                    # --- MODIFIED: Dynamically find all future steps to be skipped ---
                    affected_steps = []
                    tasks_to_check_for_skipping = ["run_alignment", "adjust_us-fdx-settings", "adjust_rlsp_diff"]
                    for step_key_int in range(i + 1, end_index + 1):
                        step_key = str(step_key_int)
                        if step_key in schedule_data:
                            future_task_list = schedule_data[step_key].get('task', [])
                            if any(task in future_task_list for task in tasks_to_check_for_skipping):
                                affected_steps.append(step_key)
                    
                    if affected_steps:
                        logging.info(f"Found subsequent steps to potentially modify based on backoff results: {affected_steps}")

                    if all_adjustments_not_needed:
                        logging.warning(f"All devices in step #{i} did not require adjustment. Subsequent alignment/adjustment steps ({affected_steps}) will be skipped.")
                        for step_key in affected_steps:
														 
                            # Also update the GUI for all macs that were supposed to run in this step
                            for mac_to_skip in schedule_data[step_key]['mac']:
                                status_queue.put((int(step_key), mac_to_skip, "Skip"))
                            schedule_data[step_key]['mac'] = []
                    else:
                        for step_key in affected_steps:
														 
                            original_macs = schedule_data[step_key]['mac']
                            filtered_macs = [m for m in original_macs if m not in macs_to_skip_in_next_steps]
                            if len(original_macs) != len(filtered_macs):
                                logging.info(f"Updating MAC list for step #{step_key}. Removing {len(macs_to_skip_in_next_steps)} device(s).")
                                schedule_data[step_key]['mac'] = filtered_macs
                                # Update GUI for the skipped macs
                                for mac_to_skip in macs_to_skip_in_next_steps:
                                    # Check if this mac was even in the original list for this step before sending update
                                    if mac_to_skip in original_macs:
                                        status_queue.put((int(step_key), mac_to_skip, "Skip"))
            
            if has_wait_task:
                if is_backoff_adjust_step and all_adjustments_not_needed:
                    logging.info(f"Skipping 'wait' task for step #{i} because no devices were adjusted.")
                else:
                    logging.info(f"--- Schedule Item #{i} device tasks complete. Executing 'wait' task. ---")
                    logging.info("Pausing for 150 seconds...")
                    time.sleep(150)
                    logging.info("--- 'wait' task complete. ---")

    except HardStopException as e:
        logging.critical(f"--- HARD STOP during schedule item. Halting execution. ---")
        logging.critical(f"Error details: {e}")
        # The exception now carries the specific MAC that failed.
        mac_in_error = e.mac_address

        if mac_in_error:
            # If we know which MAC failed, update only that one in the GUI.
            logging.info(f"Identified failing device from exception: {mac_in_error}")
            status_queue.put((i, mac_in_error, "Stop"))
        else:
            # Fallback for safety, in case the MAC wasn't attached to the exception.
            logging.warning("Could not identify the specific failing device. Marking all devices in the current step as stopped.")
            current_mac_list = schedule_data.get(str(i), {}).get('mac', [])
            for m in current_mac_list:
               status_queue.put((i, m, "Stop"))

    logging.info("--- Worker thread finished ---")
    
def main():
    """Main function to orchestrate the IP lookup and SSH connection workflow."""
    parser = argparse.ArgumentParser(description="Looks up IPs for MACs and runs specified tasks based on a settings file.")
    # ... (Keep all your existing argparse arguments) ...
    # parser.add_argument('macs', metavar='MAC', type=str, nargs='*', help='One or more MAC addresses (child devices).')
    parser.add_argument('--mac', metavar='MAC', type=str, required=True, help='MAC address of target amplifier.')
    parser.add_argument('--ip', metavar='IP', type=str, required=True, help='Service IPv6 address of target amplifer.')
    parser.add_argument('--env', type=str, choices=['PROD', 'DEV'], required=False, help="The environment ('PROD' or 'DEV').")
    parser.add_argument('--type', type=str, choices=['CM', 'CPE'], default='CPE')
    parser.add_argument('--task', type=str, required=False, nargs='+', help="One or more tasks to perform, or a single path to a .json schedule file.")
    parser.add_argument('--settings', type=str, required=False, help="Path to the JSON file with task settings.")
    parser.add_argument('--script-path', type=str, default='Get_IP_v2.2.py', help="Path to 'Get_IP_v2.2.py'.")
    parser.add_argument('--parent-mac', type=str, help="Parent device MAC address (required for some tasks).")
    parser.add_argument('--start-index', type=int, help="The starting index for tasks in a schedule file.")
    parser.add_argument('--end-index', type=int, help="The ending index for tasks in a schedule file.")
    parser.add_argument('--output', type=str, default='output', help="Path to the output folder.")
    args = parser.parse_args()

    # RH
    # Default args
    args.type = 'CPE'
    args.env = 'PROD'
    args.settings = 'amp_settings.json'
    args.task = ['get_wbfft', 'get_ec', 'show_fafe']



    output_dir = "output/" + args.output
    os.makedirs(output_dir, exist_ok=True)
    log_dir = os.path.join(output_dir, "logs")
    log_filename = setup_logging(log_dir)

    schedule_file_path = None
    if len(args.task) == 1 and args.task[0].endswith('.json'):
        schedule_file_path = args.task[0]
    
    # --- The rest of main remains mostly the same for setup ---
    logging.info(f"Log file for this session: {log_filename}")
    logging.info(f"Loading settings from: {args.settings}")
    
    try:
        with open(args.settings, 'r') as f:
            settings = json.load(f)
    except FileNotFoundError:
        logging.error(f"Settings file not found: {args.settings}")
        sys.exit(1)
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON from the settings file: {args.settings}")
        sys.exit(1)

    constants_file = settings.get("General settings", {}).get("constants_file", "constants.py")
    try:
        constants_module_name = os.path.splitext(constants_file)[0]
        constants = importlib.import_module(constants_module_name)
        logging.info(f"Successfully loaded constants from: {constants_file}")
    except ImportError:
        logging.error(f"Could not import the constants file: {constants_file}. Make sure it exists and is a valid Python file.")
        sys.exit(1)
    
    if "connection" not in settings:
        logging.error("A 'connection' object was not found in the settings file.")
        sys.exit(1)

    command_sequences = generate_command_sequences(settings, constants)
    
    # --- Execution Logic ---
    if schedule_file_path:
        try:
            with open(schedule_file_path, 'r') as f:
                schedule_data = json.load(f)
        except FileNotFoundError:
            logging.error(f"Schedule file not found: {schedule_file_path}")
            sys.exit(1)
        except json.JSONDecodeError:
            logging.error(f"Error decoding JSON from the schedule file: {schedule_file_path}")
            sys.exit(1)

        # --- GUI and Threading Start ---
        status_queue = queue.Queue()

        root = tk.Tk()
        monitor = StatusMonitor(root, schedule_data)

        # --- NEW: Define a function to run on window close ---
        def on_closing():
            """Saves the GUI and then closes the window."""
            save_gui_as_png(root, output_dir) # Call our new function
            root.destroy()

        # Create and start the worker thread
        worker_thread = threading.Thread(
            target=run_schedule_worker,
            args=(schedule_data, args, settings, constants, command_sequences, status_queue),
            daemon=True # Ensures thread exits when main program exits
        )
        worker_thread.start()

        # Start the GUI's queue processor
        monitor.process_queue(status_queue)

        # --- NEW: Bind the closing function to the window's close button ---
        root.protocol("WM_DELETE_WINDOW", on_closing)

        # Start the main loop
        root.mainloop()

        logging.info("--- GUI closed. Program finished. ---")

    else: # Original logic for non-schedule execution (no GUI)
        logging.info("Running in non-schedule mode. No status monitor will be displayed.")
        mac_ip_mapping = {}
        logging.info(f"--- Step 1: Using MAC: {args.mac} and IPv6: {args.ip} ---")
        mac = args.mac
        ip = args.ip
        mac_ip_mapping[mac] = ip
        if ip not in ["Not Found", "Error", "Script Not Found"]:
            update_mac_ip_mapping_file(os.path.join(output_dir, "mac_ip_mapping.json"), mac, ip)

        # logging.info("--- IP lookup complete ---")
        connection_results = {}
        logging.info(f"\n--- Step 2: Establishing SSH connections and running tasks ---")
        try:
            for i, (mac, ip) in enumerate(mac_ip_mapping.items()):
                _mac, result_data = connect_and_run_tasks(
                    mac, ip, args.task, command_sequences, settings, constants,
                    # parent_mac=parent_mac, parent_ip=parent_ip,
                    device_index=i + 1, total_devices=len(mac_ip_mapping),
                    output_dir=output_dir
                )
                connection_results[mac] = result_data
        except HardStopException as e:
            logging.critical(f"--- HARD STOP: A critical error occurred. Halting execution. ---")
            logging.critical(f"Error details: {e}")

        logging.info("--- All device sessions complete ---")
        logging.info(json.dumps({mac: connection_results.get(mac, {}) for mac in [args.mac]}, indent=4))

if __name__ == "__main__":
    main()