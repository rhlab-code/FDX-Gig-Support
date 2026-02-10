# status_monitor.py (updated)

import tkinter as tk
from tkinter import font
import queue
import logging

class StatusMonitor:
    """
    A tkinter-based GUI to monitor the status of tasks for multiple devices.
    """
    
    # Define the color mapping for different statuses
    STATUS_COLORS = {
        "Pass": "#4CAF50",       # Green
        "Fail": "#F44336",       # Red
        "Stop": "#F44336",       # Red
        "Running": "#FFC107",    # Yellow/Amber
        "Waiting": "#2196F3",    # Blue
        "Skip": "#9E9E9E",       # Gray
        "Not Started": "#FFFFFF" # White
    }

    def __init__(self, root, schedule_data):
        """
        Initializes the status monitor window.
        
        Args:
            root: The root tkinter window object.
            schedule_data: The parsed JSON data from the schedule file.
        """
        self.root = root
        self.root.title("Real-Time Task Status Monitor")
        
        # --- Data Extraction ---
        # Get the schedule items (steps) for rows, sorted numerically
        self.schedule_items = sorted([int(k) for k in schedule_data.keys()])

        # --- UPDATE 1: Order MAC addresses based on the first step in the schedule ---
        # Find the first schedule item key (e.g., "0") to define the MAC order
        first_step_key = str(self.schedule_items[0])
        self.mac_addresses = schedule_data.get(first_step_key, {}).get('mac', [])
        
        # Fallback if the first step has no MACs, revert to finding all and sorting
        if not self.mac_addresses:
            logging.warning("First schedule step has no MACs; ordering may be alphabetical.")
            all_macs = set()
            for item in schedule_data.values():
                all_macs.update(item.get('mac', []))
            self.mac_addresses = sorted(list(all_macs))
        
        # --- Grid Creation ---
        self.grid_labels = {}
        bold_font = font.Font(weight="bold")

        # --- UPDATE 2: Y-axis headers now show sub-tasks ---
        for i, item_index in enumerate(self.schedule_items):
            item_data = schedule_data.get(str(item_index), {})
            note = item_data.get('note', f'Step {item_index}')
            tasks = item_data.get('task', [])
            task_string = ", ".join(tasks)
            # Create a multi-line label to show step note and the list of tasks
            label_text = f"{item_index}: {note}\nTasks: {task_string}"
            
            label = tk.Label(
                self.root, 
                text=label_text, 
                relief=tk.RIDGE, 
                width=45,          # Increased width for more text
                anchor='w', 
                justify=tk.LEFT, # Align multi-line text to the left
                font=bold_font,
                wraplength=350     # Wrap text if it gets too long
            )
            label.grid(row=i + 1, column=0, sticky="nsew")

        # Create X-axis headers (MAC Addresses) in the specified order
        for j, mac in enumerate(self.mac_addresses):
            label = tk.Label(self.root, text=mac, relief=tk.RIDGE, width=20, font=bold_font)
            label.grid(row=0, column=j + 1, sticky="nsew")

        # Create the status cells
        for i, item_index in enumerate(self.schedule_items):
            self.grid_labels[item_index] = {}
            for j, mac in enumerate(self.mac_addresses):
                # Ensure all MACs from later steps are added to the grid, even if not in the first step
                if mac not in self.grid_labels[item_index]:
                    label = tk.Label(self.root, text="Not Started", relief=tk.RIDGE, width=20)
                    label.grid(row=i + 1, column=j + 1, sticky="nsew")
                    self.grid_labels[item_index][mac] = label

    def update_status(self, schedule_index, mac, status):
        """Updates the text and color of a specific cell in the grid."""
        if schedule_index in self.grid_labels and mac in self.grid_labels[schedule_index]:
            label = self.grid_labels[schedule_index][mac]
            color = self.STATUS_COLORS.get(status, "#FFFFFF") # Default to white
            label.config(text=status, bg=color, fg="white" if color != "#FFFFFF" and color != "#FFC107" else "black")

    def process_queue(self, status_queue):
        """
        Periodically checks the queue for status updates from the worker thread.
        """
        try:
            # Process all messages currently in the queue
            while True:
                schedule_index, mac, status = status_queue.get_nowait()
                self.update_status(schedule_index, mac, status)
        except queue.Empty:
            pass  # No new messages

        # Schedule this method to be called again after 100ms
        self.root.after(100, self.process_queue, status_queue)