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


parser = argparse.ArgumentParser(description="FDX-AMP WBFFT Analyzer for multiple measurement points.")
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
	import tkinter as tk
	from tkinter import ttk, messagebox
	from tkinter import scrolledtext
	import tkinter.font as tkfont

	root = tk.Tk()
	root.title('AMP Info Launcher')
	root.geometry('640x360')

	# Style
	style = ttk.Style()
	try:
		style.theme_use('clam')
	except Exception:
		pass
	header_font = tkfont.Font(root=root, family='Segoe UI', size=12, weight='bold')
	normal_font = tkfont.Font(root=root, family='Segoe UI', size=10)

	main = ttk.Frame(root, padding=(16, 12, 16, 12))
	main.pack(fill='both', expand=True)

	title = ttk.Label(main, text='AMP Info Launcher', font=header_font)
	title.grid(row=0, column=0, columnspan=3, sticky='w')

	# Image selector
	ttk.Label(main, text='Image:', font=normal_font).grid(row=1, column=0, sticky='e', pady=8)
	image_var = tk.StringVar(value='CC')
	image_combo = ttk.Combobox(main, textvariable=image_var, values=['CC', 'CS', 'SC', 'BC', 'CCs'], state='readonly', width=12)
	image_combo.grid(row=1, column=1, sticky='w', padx=(8, 0))

	# Address entry
	ttk.Label(main, text='Addr (MAC or IPv6):', font=normal_font).grid(row=2, column=0, sticky='e')
	addr_var = tk.StringVar()
	addr_entry = ttk.Entry(main, textvariable=addr_var, width=42, font=normal_font)
	addr_entry.grid(row=2, column=1, columnspan=2, sticky='w', padx=(8, 0))

	# Validation / status label
	status_var = tk.StringVar(value='Ready')
	status_label = ttk.Label(main, textvariable=status_var, font=normal_font, foreground='#0B8457')
	status_label.grid(row=3, column=0, columnspan=3, sticky='w', pady=(6, 2))

	# Spinner label for loading animation
	spinner_var = tk.StringVar(value='')
	spinner_label = ttk.Label(main, textvariable=spinner_var, font=normal_font, foreground='#0B8457')
	spinner_label.grid(row=3, column=1, sticky='w', padx=(8, 0))

	# Script status area
	scripts_frame = ttk.Frame(main)
	scripts_frame.grid(row=3, column=2, sticky='e', padx=(8,0))
	# small labels for each script
	script_names = ['amp_info.py', 'wbfft.py', 'ec.py']
	script_status_labels = {}
	for i, name in enumerate(script_names):
		lbl = ttk.Label(scripts_frame, text=f"{name}: Idle", font=('Segoe UI', 9))
		lbl.grid(row=i, column=0, sticky='e')
		script_status_labels[name] = lbl

	# Output pane
	out_label = ttk.Label(main, text='Output:', font=normal_font)
	out_label.grid(row=4, column=0, sticky='nw', pady=(8, 0))
	output = scrolledtext.ScrolledText(main, height=8, wrap='word', font=('Consolas', 10))
	output.grid(row=4, column=1, columnspan=2, sticky='nsew', padx=(8, 0), pady=(8, 0))
	output.configure(state='disabled')

	# Buttons
	btn_frame = ttk.Frame(main)
	btn_frame.grid(row=5, column=0, columnspan=3, sticky='e', pady=(12, 0))

	def set_status(text, ok=True):
		status_var.set(text)
		status_label.configure(foreground='#0B8457' if ok else '#C62828')

	def update_script_status(script, text, ok=True):
		"""Update the small script status label with color."""
		lbl = script_status_labels.get(script)
		if not lbl:
			return
		lbl.configure(text=f"{script}: {text}")
		lbl.configure(foreground='#0B8457' if ok else '#C62828')

	def append_output(text):
		output.configure(state='normal')
		output.insert('end', text + '\n')
		output.see('end')
		output.configure(state='disabled')

	def clear_output():
		output.configure(state='normal')
		output.delete('1.0', 'end')
		output.configure(state='disabled')

	def copy_output():
		root.clipboard_clear()
		root.clipboard_append(output.get('1.0', 'end').strip())
		set_status('Output copied to clipboard', ok=True)

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
		set_status('Running amp_info.py...', ok=True)
		update_script_status('amp_info.py', 'Running...', ok=True)
		append_output(f'Running: {" ".join(cmd)}')
		try:
			proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)
			raw_out = proc.stdout.strip() if proc.stdout else ''
			raw_err = proc.stderr.strip() if proc.stderr else ''
			if proc.returncode != 0:
				append_output(raw_err or raw_out or f'return code {proc.returncode}')
				set_status('Error running amp_info.py', ok=False)
				update_script_status('amp_info.py', 'Error', ok=False)
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

			append_output(raw_out or '(no output)')
			set_status('amp_info.py completed', ok=True)
			update_script_status('amp_info.py', 'Completed', ok=True)
			return parsed, raw_out

		except subprocess.TimeoutExpired:
			append_output('amp_info.py timed out')
			set_status('Timeout', ok=False)
			return None, ''
		except Exception as e:
			append_output(f'Execution error: {e}')
			set_status('Execution error', ok=False)
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
		
		# Disable submit button and start spinner
		submit_btn.config(state='disabled')
		clear_output()
		spinner_var.set('●')
		animate_spinner()
		
		# Run submission in background thread
		def run_submission():
			try:
				on_submit_worker(image, addr)
			finally:
				# Stop spinner and re-enable button on main thread
				root.after(0, lambda: spinner_var.set(''))
				root.after(0, lambda: submit_btn.config(state='normal'))
				root.after(0, lambda: addr_entry.focus())
		
		thread = threading.Thread(target=run_submission, daemon=True)
		thread.start()

	def on_submit_worker(image, addr):
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
		date_str = datetime.now().strftime('%Y%m%d_%H%M')
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
		append_output(f'Constructed FN_NAME: {fn_name_string}')

		# If we have an IP, call wbfft.py and ec.py with --image and --ip
		if ip_to_use:
			set_status('Running wbfft.py and ec.py...', ok=True)
			env = os.environ.copy()
			env['IMAGE'] = image

			# wbfft.py
			try:
				wbfft_path = os.path.join(os.path.dirname(__file__), 'wbfft.py')
				# Build a single command string with quoted arguments
				wbfft_cmd_str = f'"{sys.executable}" "{wbfft_path}" --image "{image}" --ip "{ip_to_use}" --channels "99M-1215M(6M)" --path "{fn_name_string}"'
				append_output(f'Running: {wbfft_cmd_str}')
				update_script_status('wbfft.py', 'Running...', ok=True)
				wb = subprocess.run(wbfft_cmd_str, capture_output=True, text=True, env=env, timeout=180, shell=True)
				if wb.returncode == 0:
					append_output(wb.stdout.strip() or '(no output)')
					update_script_status('wbfft.py', 'Completed', ok=True)
				else:
					append_output(wb.stderr.strip() or wb.stdout.strip() or f'wbfft returned {wb.returncode}')
					update_script_status('wbfft.py', 'Error', ok=False)
			except Exception as e:
				append_output(f'wbfft execution error: {e}')
				update_script_status('wbfft.py', 'Error', ok=False)

			# ec.py
			try:
				ec_path = os.path.join(os.path.dirname(__file__), 'ec.py')
				ec_cmd_str = f'"{sys.executable}" "{ec_path}" --image "{image}" --ip "{ip_to_use}" --path "{fn_name_string}"'
				append_output(f'Running: {ec_cmd_str}')
				update_script_status('ec.py', 'Running...', ok=True)
				ecproc = subprocess.run(ec_cmd_str, capture_output=True, text=True, env=env, timeout=300, shell=True)
				if ecproc.returncode == 0:
					append_output(ecproc.stdout.strip() or '(no output)')
					update_script_status('ec.py', 'Completed', ok=True)
				else:
					append_output(ecproc.stderr.strip() or ecproc.stdout.strip() or f'ec returned {ecproc.returncode}')
					update_script_status('ec.py', 'Error', ok=False)
			except Exception as e:
				append_output(f'ec execution error: {e}')
				update_script_status('ec.py', 'Error', ok=False)

			set_status('Completed wbfft/ec', ok=True)
		else:
			append_output('No valid IP determined; skipping wbfft/ec invocation')
			set_status('No IP determined', ok=False)


	submit_btn = ttk.Button(btn_frame, text='Submit', command=on_submit)
	submit_btn.grid(row=0, column=0, padx=6)
	copy_btn = ttk.Button(btn_frame, text='Copy Output', command=copy_output)
	copy_btn.grid(row=0, column=1, padx=6)
	clear_btn = ttk.Button(btn_frame, text='Clear', command=clear_output)
	clear_btn.grid(row=0, column=2, padx=6)

	# make the output region expand
	main.rowconfigure(4, weight=1)
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