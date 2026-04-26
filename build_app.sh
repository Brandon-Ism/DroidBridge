#!/bin/bash
# DroidBridge build script

echo "Setting up virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo "Installing requirements..."
pip install -r requirements.txt

echo "Building DroidBridge.app..."
pyinstaller --name "DroidBridge" \
            --windowed \
            --noconsole \
            --clean \
            macdroid_app.py

echo "Build complete. Check the 'dist' folder for DroidBridge.app"
