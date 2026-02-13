#
#
#
#
#   Sample node: PADUSTES4A
#   Sapmle Amp Name UNREG-PADUSTEST4-24:A1:86:1F:F3:AC
#   Sample MAC 24:a1:86:1f:f3:ac
#   Sample IP  2001:0558:6031:001C:3408:5385:73EF:FE58

''' example usages:
python app.py --image CC --addr 24:a1:86:1f:f3:ac
python app.py --image CC --addr 2001:0558:6031:001C:3408:5385:73EF:FE58
'''

import argparse
import ipaddress
import logging
import subprocess
import sys
import os
import macaddress
import json
import ast
from datetime import datetime
import re
import threading
import tkinter as tk
import ttkbootstrap as tb
from ttkbootstrap.constants import *
# from ttkbootstrap.scrolledtext import ScrolledText
import tkinter.messagebox as messagebox
import tkinter.font as tkfont

parser = argparse.ArgumentParser(description="AmpPoll - amplifier polling for multiple measurement points.")
parser.add_argument('--addr', type=str, help="Optional. Specify either IP or MAC address of the target device. Overrides the value in config.")
args = parser.parse_args()


def is_valid_addr(value: str) -> bool:
	"""Return True if value is a valid MAC or IPv6 address."""
	if not value:
		return False
	try:
		# Try MAC first
		macaddress.MAC(value)
		return True
	except Exception:
		pass
	try:
		ipaddress.IPv6Address(value)
		return True
	except Exception:
		return False


def is_ipv6(value: str) -> bool:
    """Return True if `value` is a valid IPv6 address."""
    if not value:
        return False
    try:
        ipaddress.IPv6Address(value)
        return True
    except Exception:
        return False


def launch_gui():
	# Create root window with ttkbootstrap yeti theme
	root = tb.Window(themename='yeti')
	root.title('AmpPoll - Amplifier Polling Utility')
	icon_png_path = os.path.join(os.getcwd(), 'resources/icons/icon-128.png')
	# root.state('zoomed')  # Maximize window on Windows

	# Register and set custom font as default
	font_path = os.path.join(os.getcwd(), 'resources', 'fonts', 'ComcastNewVision.otf')
	try:
		if os.path.exists(font_path):
			tkfont.nametofont('TkDefaultFont').configure(family='ComcastNewVision')
			tkfont.nametofont('TkTextFont').configure(family='ComcastNewVision')
			tkfont.nametofont('TkFixedFont').configure(family='ComcastNewVision')
			tkfont.nametofont('TkMenuFont').configure(family='ComcastNewVision')
			tkfont.nametofont('TkHeadingFont').configure(family='ComcastNewVision')
			tkfont.nametofont('TkCaptionFont').configure(family='ComcastNewVision')
			tkfont.nametofont('TkSmallCaptionFont').configure(family='ComcastNewVision')
			tkfont.nametofont('TkIconFont').configure(family='ComcastNewVision')
			tkfont.nametofont('TkTooltipFont').configure(family='ComcastNewVision')
	except Exception:
		pass

	try:
		img = tb.PhotoImage(file=icon_png_path)
		root.iconphoto(False, img)
	except Exception:
		pass
	header_font = tkfont.Font(root=root, family='ComcastNewVision', size=12, weight='bold')
	normal_font = tkfont.Font(root=root, family='ComcastNewVision', size=10)

	main = tb.Frame(root, padding=(16, 12, 32, 32))
	main.pack(fill='both', expand=True)

	title = tb.Label(main, text='AmpPoll', font=header_font)
	title.grid(row=0, column=0, columnspan=3, sticky='w')

	# Image selector
	tb.Label(main, text='Amp Software:', font=normal_font).grid(row=1, column=0, sticky='e', pady=8)
	image_var = tb.StringVar(value='CC')
	image_combo = tb.Combobox(main, textvariable=image_var, values=['CC', 'CS', 'SC', 'BC', 'CCs'], state='readonly', width=12)
	image_combo.grid(row=1, column=1, sticky='w', padx=(8, 0))

	# Address entry
	tb.Label(main, text='Address (MAC or IPv6):', font=normal_font).grid(row=2, column=0, sticky='e')
	addr_var = tb.StringVar()
	addr_entry = tb.Entry(main, textvariable=addr_var, width=42, font=normal_font)
	addr_entry.grid(row=2, column=1, columnspan=2, sticky='w', padx=(8, 0))

	# Task selector (checkboxes)
	available_tasks = [
		# 'showModuleInfo', 'show_spectrum', 'show_ds-profile', 'show_us-profile', 
		# 'show_rf_components', 'show_fafe',
		'get_wbfft', 'get_eq', 'get_sf', 'get_ec', 'get_us_psd',
		'reset'
	]
	
    # available_tasks = [
    #     'showModuleInfo', 'show_spectrum', 'show_ds-profile', 'show_us-profile', 
    #     'show_north-afe-backoff', 'show_rf_components', 'show_alignment', 'show_fafe',
    #     'get_wbfft', 'get_eq', 'get_sf', 'get_ec', 'get_us_psd', 'get_clipping',
    #     'get_nc_input_power', 'get_wbfft_hal_gains',
    #     'configure_spectrum', 'configure_ds-profile', 'configure_us-profile', 
    #     'configure_north-afe-backoff', 'configure_rf_components', 'run_alignment',
    #     'adjust_north-afe-backoff', 'adjust_us-fdx-settings', 'adjust_rlsp_diff',
    #     'commit_ds-profile', 'commit_us-profile', 'upgradefw', 'reset', 'tg_start', 'tg_stop',
    #     'generate_key', 'wait'
	# ]
	
	# Function to convert task names to human-readable labels
	def make_label(task_name):
		"""Convert task_name like 'show_ds-profile' to 'Show DS Profile'."""
		label = task_name.replace('_', ' ').replace('-', ' ')
		return ' '.join(word.capitalize() for word in label.split())
	
	# Create frame for checkboxes
	task_frame = tb.Frame(main)
	task_frame.grid(row=3, column=0, columnspan=3, sticky='ew', padx=(0, 0), pady=(8, 16))
	
	# Dictionary to store task checkbox variables
	task_vars = {}
	
	# Organize tasks in columns (3 columns for better layout)
	num_cols = 3
	for i, task in enumerate(available_tasks):
		row = i // num_cols
		col = i % num_cols
		var = tb.BooleanVar(value=False)
		task_vars[task] = var
		label_text = make_label(task)
		cb = tb.Checkbutton(task_frame, text=label_text, variable=var, bootstyle='info')
		cb.grid(row=row, column=col, sticky='w', padx=(0, 16), pady=(2, 2))

	# Validation / status label
	status_var = tb.StringVar(value='Ready')
	status_label = tb.Label(main, textvariable=status_var, font=normal_font, foreground='#0B8457')
	status_label.grid(row=4, column=0, columnspan=3, sticky='w', pady=(6, 2))

	# Spinner label for loading animation
	spinner_var = tb.StringVar(value='')
	spinner_label = tb.Label(main, textvariable=spinner_var, font=normal_font, foreground='#0B8457')
	spinner_label.grid(row=4, column=1, sticky='w', padx=(8, 0))

	# Script status area
	scripts_frame = tb.Frame(main)
	scripts_frame.grid(row=4, column=2, sticky='e', padx=(8,0))
	# small labels for each script
	# script_names = ['amp_info.py', 'wbfft.py', 'ec.py']
	script_names = ['Amp Info', 'Data Graphs']
	script_status_labels = {}
	for i, name in enumerate(script_names):
		lbl = tb.Label(scripts_frame, text=f"{name}: Idle", font=('ComcastNewVision', 9))
		lbl.grid(row=i, column=0, sticky='e')
		script_status_labels[name] = lbl

	# Buttons
	btn_frame = tb.Frame(main)
	btn_frame.grid(row=5, column=0, columnspan=3, sticky='e', pady=(12, 0))

	def set_status(text, ok=True):
		status_var.set(text)
		status_label.configure(foreground='#0B8457' if ok else '#C62828')

	# def update_task_status(task_name, status, ok=True):
	# 	"""Update the status label for a specific task.
	# 	Status can be 'Running', 'Completed', or 'Failed'.
	# 	"""
	# 	if task_name in task_status_labels:
	# 		if status == 'Running':
	# 			task_status_labels[task_name].configure(text=f"{make_label(task_name)}: ● Running", foreground='#F57C00')
	# 		elif status == 'Completed':
	# 			task_status_labels[task_name].configure(text=f"{make_label(task_name)}: ✓ Completed", foreground='#0B8457')
	# 		elif status == 'Failed':
	# 			task_status_labels[task_name].configure(text=f"{make_label(task_name)}: ✗ Failed", foreground='#C62828')
	# 	root.update_idletasks()

	def append_output(text):
		pass

	def clear_output():
		pass

	def clear_all():
		"""Uncheck all tasks and clear the address input field."""
		for var in task_vars.values():
			var.set(False)
		addr_var.set('')
		clear_output()
		set_status('Cleared', ok=True)

	def select_all_tasks():
		"""Select all tasks."""
		for var in task_vars.values():
			var.set(True)


	# Spinner animation setup
	spinner_frames = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
	spinner_idx = [0]

	def animate_spinner():
		if spinner_var.get() != '':  # Only animate if we're in spinner mode
			spinner_idx[0] = (spinner_idx[0] + 1) % len(spinner_frames)
			spinner_var.set(spinner_frames[spinner_idx[0]])
			root.after(100, animate_spinner)

	def stop_spinner():
		spinner_var.set('')
		spinner_idx[0] = 0

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

	def on_submit(event=None):
		image = image_var.get()
		addr = addr_var.get().strip()
		if not addr:
			messagebox.showerror('Validation error', 'Please enter an address (MAC or IPv6).')
			set_status('Validation error', ok=False)
			return
		if not is_valid_addr(addr):
			messagebox.showerror('Validation error', 'Address must be a valid MAC or IPv6 address.')
			set_status('Invalid address', ok=False)
			return
		
		# Get selected tasks from checkboxes
		selected_tasks = [task for task, var in task_vars.items() if var.get()]
		if not selected_tasks:
			messagebox.showerror('Validation error', 'Please select at least one task.')
			set_status('No tasks selected', ok=False)
			return
		
		# Disable submit button and start spinner
		submit_btn.config(state='disabled')
		clear_output()
		spinner_var.set('●')
		animate_spinner()
		
		# Run submission in background thread
		def run_submission():
			try:
				on_submit_worker(image, addr, selected_tasks)
			finally:
				# Stop spinner and re-enable button on main thread
				root.after(0, lambda: spinner_var.set(''))
				root.after(0, lambda: submit_btn.config(state='normal'))
				root.after(0, lambda: addr_entry.focus())
		
		thread = threading.Thread(target=run_submission, daemon=True)
		thread.start()

	def on_submit_worker(image, addr, selected_tasks_list):
		parsed, raw = run_amp_info(image, addr)

		# Determine IP to use for subsequent calls
		ip_to_use = None
		cm_mac_val = None
		fn_name_val = None

		if isinstance(parsed, dict):
			# check for cpeIpv6Addr or cmMacAddr keys
			if 'cpeIpv6Addr' in parsed and parsed.get('cpeIpv6Addr'):
				ip_to_use = parsed.get('cpeIpv6Addr')
			if 'cmMacAddr' in parsed and parsed.get('cmMacAddr'):
				cm_mac_val = parsed.get('cmMacAddr')
			# fnName may be present
			if 'fnName' in parsed and parsed.get('fnName'):
				fn_name_val = parsed.get('fnName')

		# If amp_info returned cmMacAddr, use the submitted ipv6 address as ip
		if cm_mac_val and is_ipv6(addr):
			ip_to_use = addr

		# If no ip found but submitted addr is IPv6, use it
		if not ip_to_use and is_ipv6(addr):
			ip_to_use = addr

		# Build fnName string: fnName + '/' + cmMacAddr_or_submitted_mac + '/' + YYYYMMDD
		date_str = datetime.now().strftime('%Y-%m-%d_%H-%M')
		mac_for_fn = cm_mac_val
		# if we don't have cm_mac_val and submitted addr looks like a MAC, use it
		try:
			if not mac_for_fn:
				# treat original addr as MAC if it parses
				macaddress.MAC(addr)
				mac_for_fn = addr
		except Exception:
			mac_for_fn = mac_for_fn

		# sanitize mac: remove :, -, _, and spaces
		if mac_for_fn:
			mac_for_fn = re.sub(r'[:\-_\s]+', '', str(mac_for_fn))

		fn_components = []
		if fn_name_val:
			fn_components.append(str(fn_name_val))
		if mac_for_fn:
			fn_components.append(str(mac_for_fn))
		fn_components.append(date_str)
		fn_name_string = '/'.join(fn_components)
		append_output(f'Constructed path: {fn_name_string}')

		# If we have an IP, call wbfft_v2.py with --mac and --ip
		if ip_to_use:
			set_status('Working on it', ok=True)
			env = os.environ.copy()
			env['IMAGE'] = image

			# Get selected tasks and build task argument
			task_arg = ' '.join(selected_tasks_list)

			# wbfft_2.py
			# python wbfft_v2.py 24:a1:86:1d:da:90 --ip 2001:558:6026:32:912b:2704:46eb:f4 --task showModuleInfo get_wbfft get_ec
			try:
				wbfft_path = os.path.join(os.path.dirname(__file__), 'wbfft_v2.py')
				# Build a single command string with quoted arguments
				wbfft_cmd_str = f'"{sys.executable}" "{wbfft_path}" --mac "{mac_for_fn}" --ip "{ip_to_use}" --image "{image}" --output "{fn_name_string}" --task {task_arg}'
				append_output(f'Running: {wbfft_cmd_str}')
				
				wb = subprocess.run(wbfft_cmd_str, capture_output=True, text=True, env=env, timeout=180, shell=True)
				if wb.returncode == 0:
					append_output(wb.stdout.strip() or '(no output)')
				
				else:
					append_output(wb.stderr.strip() or wb.stdout.strip() or f'wbfft returned {wb.returncode}')
			
			except Exception as e:
				append_output(f'wbfft execution error: {e}')
			

			# ec.py
			# try:
			# 	ec_path = os.path.join(os.path.dirname(__file__), 'ec.py')
			# 	ec_cmd_str = f'"{sys.executable}" "{ec_path}" --image "{image}" --ip "{ip_to_use}" --path "{fn_name_string}"'
			# 	append_output(f'Running: {ec_cmd_str}')
			# 	update_script_status('ec.py', 'Running...', ok=True)
			# 	ecproc = subprocess.run(ec_cmd_str, capture_output=True, text=True, env=env, timeout=300, shell=True)
			# 	if ecproc.returncode == 0:
			# 		append_output(ecproc.stdout.strip() or '(no output)')
			# 		update_script_status('ec.py', 'Completed', ok=True)
			# 	else:
			# 		append_output(ecproc.stderr.strip() or ecproc.stdout.strip() or f'ec returned {ecproc.returncode}')
			# 		update_script_status('ec.py', 'Error', ok=False)
			# except Exception as e:
			# 	append_output(f'ec execution error: {e}')
			# 	update_script_status('ec.py', 'Error', ok=False)

			set_status('Completed Tasks', ok=True)
		else:
			append_output('No valid IP determined; skipping wbfft/ec invocation')
			set_status('No IP determined', ok=False)


	submit_btn = tb.Button(btn_frame, text='Submit', command=on_submit, bootstyle='success')
	submit_btn.grid(row=0, column=0, padx=6)
	# copy_btn = tb.Button(btn_frame, text='Copy DEBUG Info', command=copy_output, bootstyle='info')
	# copy_btn.grid(row=0, column=1, padx=6)
	select_all_btn = tb.Button(btn_frame, text='Select All', command=select_all_tasks, bootstyle='info')
	select_all_btn.grid(row=0, column=1, padx=6)
	clear_btn = tb.Button(btn_frame, text='Reset', command=clear_all, bootstyle='warning')
	clear_btn.grid(row=0, column=2, padx=6)

	# make the output region expand
	main.rowconfigure(4, weight=0)
	main.columnconfigure(2, weight=1)

	# keyboard
	addr_entry.focus()
	root.bind('<Return>', on_submit)

	root.mainloop()


if __name__ == '__main__':
	# If the script was launched without CLI args, open the GUI for convenience.
	if len(sys.argv) == 1:
		launch_gui()
	else:
		# If addr provided via CLI, just print a short confirmation (preserve CLI usage)
		if args.addr:
			print(f"CLI mode: addr={args.addr}")