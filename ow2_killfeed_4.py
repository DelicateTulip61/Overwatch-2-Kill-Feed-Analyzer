"""
OW2 Kill Feed Analyzer
----------------------
Captures the kill feed (top-left), reads team-colored event borders,
computes a fight advantage score, and shows a floating overlay.

Requirements:
    pip install dxcam opencv-python numpy pillow

Usage:
    python ow2_killfeed.py               # normal mode: overlay + live analysis
    python ow2_killfeed.py --record      # silently saves kill feed crops to kf_samples/
    python ow2_killfeed.py --replay      # replays saved frames, tests HSV + logic offline
    python ow2_killfeed.py --calibrate   # live HSV mask viewer (needs alt-tab)
"""

import time
import threading
import collections
import tkinter as tk
import os
import glob
import sys

import cv2
import numpy as np

try:
    import dxcam
    DXCAM_AVAILABLE = True
except ImportError:
    DXCAM_AVAILABLE = False
    print("[WARN] dxcam not found — falling back to mock frames for testing.")


# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

SCREEN_REGION    = (0, 0, 420, 220)   # kill feed crop (1920x1080). adjust if needed.
FPS              = 10
WINDOW_SECONDS   = 8
ATTACK_THRESHOLD = 1

ALLY_HSV_LOW   = np.array([100, 100, 100])
ALLY_HSV_HIGH  = np.array([130, 255, 255])
ENEMY_HSV_LOW  = np.array([0,   120, 120])
ENEMY_HSV_HIGH = np.array([10,  255, 255])

MIN_CONTOUR_AREA = 40

RECORD_DIR  = "kf_samples"
RECORD_FPS  = 2    # frames per second saved during --record


# ─────────────────────────────────────────────
# KILL EVENT DETECTION
# ─────────────────────────────────────────────

def count_colored_blobs(frame, hsv_low, hsv_high):
    hsv  = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, hsv_low, hsv_high)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return sum(1 for c in contours if cv2.contourArea(c) >= MIN_CONTOUR_AREA)


def analyze_frame(frame):
    ally  = count_colored_blobs(frame, ALLY_HSV_LOW,  ALLY_HSV_HIGH)
    enemy = count_colored_blobs(frame, ENEMY_HSV_LOW, ENEMY_HSV_HIGH)
    return ally, enemy


# ─────────────────────────────────────────────
# DECISION LOGIC
# ─────────────────────────────────────────────

class FightAdvisor:
    def __init__(self, window_sec=WINDOW_SECONDS):
        self.window_sec  = window_sec
        self._samples    = collections.deque()
        self.ally_total  = 0
        self.enemy_total = 0
        self.verdict     = "NEUTRAL"
        self.reason      = "Waiting for data…"

    def push(self, ally, enemy):
        now = time.time()
        self._samples.append((now, ally, enemy))
        self._evict(now)
        self._compute()

    def _evict(self, now):
        cutoff = now - self.window_sec
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def _compute(self):
        if not self._samples:
            self.verdict = "NEUTRAL"
            self.reason  = "No events yet"
            return

        ally_sum  = sum(s[1] for s in self._samples)
        enemy_sum = sum(s[2] for s in self._samples)
        diff      = ally_sum - enemy_sum

        self.ally_total  = ally_sum
        self.enemy_total = enemy_sum

        if diff >= ATTACK_THRESHOLD:
            self.verdict = "ATTACK"
            self.reason  = f"Team ahead  (+{diff} in {self.window_sec}s)"
        elif diff <= -ATTACK_THRESHOLD:
            self.verdict = "DEFEND"
            self.reason  = f"Enemy ahead  ({diff:+d} in {self.window_sec}s)"
        else:
            self.verdict = "NEUTRAL"
            self.reason  = f"Even fight  (diff={diff:+d})"


# ─────────────────────────────────────────────
# OVERLAY UI
# ─────────────────────────────────────────────

COLORS = {
    "ATTACK":  {"bg": "#1a3a1a", "fg": "#4dff6e", "fg_dim": "#2a8a40", "label": "⚔  ATTACK"},
    "DEFEND":  {"bg": "#3a1a1a", "fg": "#ff6e6e", "fg_dim": "#8a3030", "label": "🛡  DEFEND"},
    "NEUTRAL": {"bg": "#1e1e2e", "fg": "#aaaacc", "fg_dim": "#555577", "label": "◈  NEUTRAL"},
}


class Overlay:
    def __init__(self, advisor: FightAdvisor):
        self.advisor = advisor
        self.root    = tk.Tk()
        self.root.title("KF Advisor")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.88)
        self.root.geometry("300x110+20+20")

        self._drag_x = self._drag_y = 0

        self.verdict_var = tk.StringVar(value="⚙  Loading…")
        self.verdict_lbl = tk.Label(
            self.root, textvariable=self.verdict_var,
            font=("Consolas", 22, "bold"), bg="#1e1e2e", fg="#aaaacc", pady=6,
        )
        self.verdict_lbl.pack(fill="x")

        self.reason_var = tk.StringVar(value="")
        self.reason_lbl = tk.Label(
            self.root, textvariable=self.reason_var,
            font=("Consolas", 10), bg="#1e1e2e", fg="#555577",
        )
        self.reason_lbl.pack(fill="x")

        self.counts_var = tk.StringVar(value="")
        self.counts_lbl = tk.Label(
            self.root, textvariable=self.counts_var,
            font=("Consolas", 11), bg="#1e1e2e", fg="#555577",
        )
        self.counts_lbl.pack(fill="x")

        for w in (self.verdict_lbl, self.reason_lbl, self.counts_lbl):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>",     self._do_drag)

        self.root.bind("<Button-3>", lambda _: self.root.destroy())
        self._refresh()

    def _start_drag(self, e):
        self._drag_x = e.x_root - self.root.winfo_x()
        self._drag_y = e.y_root - self.root.winfo_y()

    def _do_drag(self, e):
        self.root.geometry(f"+{e.x_root - self._drag_x}+{e.y_root - self._drag_y}")

    def _refresh(self):
        v = self.advisor.verdict
        c = COLORS[v]
        self.verdict_var.set(c["label"])
        self.verdict_lbl.config(bg=c["bg"], fg=c["fg"])
        self.reason_lbl.config( bg=c["bg"], fg=c["fg_dim"])
        self.counts_lbl.config( bg=c["bg"], fg=c["fg_dim"])
        self.root.config(bg=c["bg"])
        self.reason_var.set(self.advisor.reason)
        self.counts_var.set(
            f"  allies: {self.advisor.ally_total}  |  enemies: {self.advisor.enemy_total}"
        )
        self.root.after(300, self._refresh)

    def run(self):
        self.root.mainloop()


# ─────────────────────────────────────────────
# CAPTURE LOOP  (live mode)
# ─────────────────────────────────────────────

def capture_loop(advisor: FightAdvisor, stop_event: threading.Event):
    if DXCAM_AVAILABLE:
        camera = dxcam.create(output_color="BGR")
        camera.start(region=SCREEN_REGION, target_fps=FPS)
        print("[INFO] Capture started. Right-click overlay to quit.")
        while not stop_event.is_set():
            frame = camera.get_latest_frame()
            if frame is None:
                time.sleep(0.02)
                continue
            ally, enemy = analyze_frame(frame)
            advisor.push(ally, enemy)
            time.sleep(1 / FPS)
        camera.stop()
    else:
        print("[INFO] Running in MOCK MODE — install dxcam for real capture.")
        sequence = (
            [(2, 0)] * 15 +
            [(0, 0)] * 10 +
            [(0, 3)] * 15 +
            [(1, 1)] * 10
        )
        i = 0
        while not stop_event.is_set():
            ally, enemy = sequence[i % len(sequence)]
            advisor.push(ally, enemy)
            i += 1
            time.sleep(1 / FPS)


# ─────────────────────────────────────────────
# RECORD MODE  —  python ow2_killfeed.py --record
# ─────────────────────────────────────────────

def record_mode():
    """
    Silently saves kill feed crops to kf_samples/ while you play.
    No window, no alt-tab needed — just runs in the background.
    Press Ctrl+C in the terminal to stop.
    """
    if not DXCAM_AVAILABLE:
        print("[ERROR] dxcam is required for --record mode.")
        return

    os.makedirs(RECORD_DIR, exist_ok=True)

    existing = glob.glob(os.path.join(RECORD_DIR, "frame_*.png"))
    start_i  = len(existing)

    camera = dxcam.create(output_color="BGR")
    camera.start(region=SCREEN_REGION, target_fps=RECORD_FPS)

    print(f"[RECORD] Saving frames to '{RECORD_DIR}/'")
    print(f"[RECORD] Starting at frame index {start_i}  (existing frames kept)")
    print("[RECORD] Press Ctrl+C to stop.\n")

    i = start_i
    try:
        while True:
            frame = camera.get_latest_frame()
            if frame is not None:
                path = os.path.join(RECORD_DIR, f"frame_{i:05d}.png")
                cv2.imwrite(path, frame)
                i += 1
                print(f"\r[RECORD] {i - start_i} frames saved", end="", flush=True)
            time.sleep(1 / RECORD_FPS)
    except KeyboardInterrupt:
        print(f"\n[RECORD] Stopped. {i - start_i} frames saved to '{RECORD_DIR}/'")
        print(f"[RECORD] Run  python ow2_killfeed.py --replay  to inspect them.")
    finally:
        camera.stop()


# ─────────────────────────────────────────────
# REPLAY MODE  —  python ow2_killfeed.py --replay
# ─────────────────────────────────────────────

def replay_mode():
    """
    Replays saved frames from kf_samples/ through the analyzer offline.

    Shows a CV2 window:  Original | Ally mask (green) | Enemy mask (red)
    Terminal prints detections and verdict for every frame that has activity.

    Controls:
      SPACE  — pause / resume
      N      — step one frame forward (while paused)
      Q      — quit
    """
    frames = sorted(glob.glob(os.path.join(RECORD_DIR, "frame_*.png")))
    if not frames:
        print(f"[ERROR] No frames found in '{RECORD_DIR}/'. Run --record first.")
        return

    print(f"[REPLAY] {len(frames)} frames found in '{RECORD_DIR}/'")
    print("  SPACE=pause/resume   N=next frame (paused)   Q=quit\n")

    advisor = FightAdvisor()
    paused  = False

    verdict_colors = {
        "ATTACK":  (0,   200,  50),
        "DEFEND":  (50,   50, 200),
        "NEUTRAL": (160, 160, 160),
    }

    for idx, path in enumerate(frames):
        frame = cv2.imread(path)
        if frame is None:
            continue

        ally, enemy = analyze_frame(frame)
        advisor.push(ally, enemy)

        # build colored masks for visualization
        hsv           = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        ally_mask     = cv2.inRange(hsv, ALLY_HSV_LOW,  ALLY_HSV_HIGH)
        enemy_mask    = cv2.inRange(hsv, ENEMY_HSV_LOW, ENEMY_HSV_HIGH)
        ally_colored  = np.zeros_like(frame)
        enemy_colored = np.zeros_like(frame)
        ally_colored[ ally_mask  > 0] = (0,   220,  60)
        enemy_colored[enemy_mask > 0] = (60,   60, 220)

        combined = np.hstack([frame, ally_colored, enemy_colored])
        h, w     = combined.shape[:2]

        vcol = verdict_colors.get(advisor.verdict, (160, 160, 160))
        cv2.putText(combined,
                    f"[{idx+1}/{len(frames)}]  ally={ally}  enemy={enemy}  → {advisor.verdict}",
                    (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, vcol, 1, cv2.LINE_AA)
        cv2.putText(combined, "Original",
                    (8, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (130, 130, 130), 1)
        cv2.putText(combined, "Ally mask",
                    (frame.shape[1] + 8, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 180, 60), 1)
        cv2.putText(combined, "Enemy mask",
                    (frame.shape[1] * 2 + 8, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (60, 60, 200), 1)

        cv2.imshow("REPLAY  |  Original | Ally mask | Enemy mask", combined)

        if ally or enemy:
            print(f"  frame {idx+1:>4}  ally={ally}  enemy={enemy}"
                  f"  verdict={advisor.verdict}  ({advisor.reason})")

        delay = 0 if paused else max(1, int(1000 / RECORD_FPS))
        key   = cv2.waitKey(delay) & 0xFF

        if key == ord("q"):
            break
        elif key == ord(" "):
            paused = not paused
            print(f"  {'[PAUSED]' if paused else '[RESUMED]'}")
        elif key == ord("n") and paused:
            continue

    cv2.destroyAllWindows()
    print("\n[REPLAY] Done.")


# ─────────────────────────────────────────────
# CALIBRATE MODE  —  python ow2_killfeed.py --calibrate
# ─────────────────────────────────────────────

def calibration_mode():
    """Live HSV mask viewer. Requires alt-tabbing — use --replay instead when playing fullscreen."""
    if not DXCAM_AVAILABLE:
        print("[ERROR] dxcam required for --calibrate mode.")
        return

    camera = dxcam.create(output_color="BGR")
    camera.start(region=SCREEN_REGION, target_fps=FPS)
    print("Calibration mode — press Q to quit.")

    while True:
        frame = camera.get_latest_frame()
        if frame is None:
            continue
        hsv        = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        ally_mask  = cv2.cvtColor(cv2.inRange(hsv, ALLY_HSV_LOW,  ALLY_HSV_HIGH), cv2.COLOR_GRAY2BGR)
        enemy_mask = cv2.cvtColor(cv2.inRange(hsv, ENEMY_HSV_LOW, ENEMY_HSV_HIGH), cv2.COLOR_GRAY2BGR)
        cv2.imshow("Original | Ally mask | Enemy mask", np.hstack([frame, ally_mask, enemy_mask]))
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    camera.stop()
    cv2.destroyAllWindows()


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    if "--calibrate" in sys.argv:
        calibration_mode()
    elif "--record" in sys.argv:
        record_mode()
    elif "--replay" in sys.argv:
        replay_mode()
    else:
        advisor    = FightAdvisor()
        stop_event = threading.Event()

        capture_thread = threading.Thread(
            target=capture_loop, args=(advisor, stop_event), daemon=True
        )
        capture_thread.start()

        overlay = Overlay(advisor)
        try:
            overlay.run()
        finally:
            stop_event.set()
            print("[INFO] Stopped.")
