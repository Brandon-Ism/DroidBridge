# DroidBridge

DroidBridge is a native macOS desktop application that allows you to seamlessly transfer files between your Mac and your Android device using ADB (Android Debug Bridge), bypassing the often unreliable MTP protocol. 

It provides a dual-pane interface similar to classic file managers, allowing you to browse your local macOS filesystem on one side and your Android device on the other.

## Features

- Dual-pane interface (Local Mac and Android Device)
- Drag and drop file transfers in both directions
- Support for selecting and transferring multiple files
- Keyboard shortcuts for quick actions (e.g., F5 to Copy)
- Integrated image thumbnail previews (QuickLook support)
- Simple ADB integration

## Prerequisites

- macOS
- Python 3.x
- ADB installed and added to your system PATH

To use the application, you must enable USB Debugging on your Android device and authorize your Mac when prompted.

## Setup and Installation

1. Clone this repository or download the source code.
2. Ensure ADB is installed and accessible from your terminal.
3. Run the build script to set up the environment and compile the app:

```bash
chmod +x build_app.sh
./build_app.sh
```

4. Once the build completes, you can find the `DroidBridge.app` executable inside the newly created `dist` directory.

## Usage

You can launch the packaged `DroidBridge.app` directly or run the Python script during development:

```bash
source venv/bin/activate
python macdroid_app.py
```

Use the address bar or the ".." button to navigate directories. You can transfer files by either dragging and dropping them between the left and right panes, or by selecting them and pressing F5.

## License

See the LICENSE file for details.
