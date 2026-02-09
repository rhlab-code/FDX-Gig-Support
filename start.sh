#!/bin/bash
echo "Starting AmpPoll. A tool for polling multiple measurement points in a FDX Amp."

echo "Starting Jump UI..."
jump -ui && \
echo "Jump UI started successfully." || \
echo "Failed to start Jump UI."
echo "Running app.py..."
python app.py && \
echo "app.py executed successfully." || \
echo "Failed to execute app.py."