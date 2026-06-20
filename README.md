# Overwatch 2 Kill Feed Analyzer

A real-time, computer vision-based overlay for Overwatch 2. This script captures the kill feed, detects team-colored event borders using HSV masking, computes a fight advantage score, and displays a floating HUD to advise you whether to Attack, Defend, or play Neutral.

## Features
* **Live Overlay:** A transparent, non-intrusive Tkinter widget that stays on top of your game.
* **Smart Analysis:** Tracks kills over a rolling 8-second window.
* **Recording Mode:** Silently runs in the background saving kill feed crops for offline analysis.
* **Replay Mode:** Step through recorded frames to test and visualize your HSV masking logic offline.
* **Calibration Mode:** Live visualizer to help you tweak HSV color ranges for your specific game settings.

## Prerequisites
You will need Python installed. This tool relies on `dxcam` for high-performance screen capture, meaning it currently works best on Windows.

Install the required dependencies:
```bash
pip install dxcam opencv-python numpy pillow
