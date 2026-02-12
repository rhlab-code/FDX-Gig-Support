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

def setup_logging(output_dir):
    """Sets up file and stream logging to the specified directory."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    log_filename = os.path.join(output_dir, f"workflow_log_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log")
    
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
        
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    file_handler = logging.FileHandler(log_filename)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    
    return log_filename