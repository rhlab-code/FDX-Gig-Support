#!/bin/bash
echo "Starting AmpPoll. A tool for polling multiple measurement points in a FDX Amp."

echo "Starting Jump..."
jump_output=$(jump -ui 2>&1)
if [ -z "$jump_output" ]; then
    echo "Failed to start Jump. No output received."
    exit 1
fi
echo "Jump started successfully."
echo "Pulling latest code from repository..."
git pull && \
echo "Updated code from repository."
echo "Installing any missing dependencies..."
pip install -r requirements.txt && \
echo "Dependencies installed."
echo "Running app.py..."
python app.py && \
echo "app.py executed successfully." || \
echo "Failed to execute app.py."