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
```

## Usage
Run the script from your terminal. By default, it will launch the live analyzer and overlay.

```bash
# Normal Mode: Launches the overlay and live analysis
python ow2_killfeed.py

# Record Mode: Silently saves kill feed crops to a /kf_samples folder
python ow2_killfeed.py --record

# Replay Mode: Replays saved frames offline to test HSV and logic 
python ow2_killfeed.py --replay

# Calibrate Mode: Live HSV mask viewer (useful for tuning color bounds)
python ow2_killfeed.py --calibrate
```

## Configuration
Depending on your monitor resolution and in-game UI settings, you may need to tweak the variables at the top of the script:

* `SCREEN_REGION`: Adjust the crop coordinates (default is (0, 0, 420, 220) for 1080p).
* `ALLY_HSV_LOW` / `ENEMY_HSV_LOW`: Adjust these if you use custom colorblind UI colors in Overwatch.
