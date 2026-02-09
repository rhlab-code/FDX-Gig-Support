#!/bin/bash
echo "Starting AmpPoll. A tool for polling multiple measurement points in a FDX Amp."

echo "Starting Jump UI..."
jump -ui && \
echo "Jump UI started successfully." || \
echo "Failed to start Jump UI."
echo "Pulling latest code from repository..."
git pull && \
echo "Updated code from repository."
echo "Running app.py..."
python app.py && \
echo "app.py executed successfully." || \
echo "Failed to execute app.py."