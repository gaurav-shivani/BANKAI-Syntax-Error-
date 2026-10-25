import os
import time
import threading
import urllib.request
from collections import deque

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# ======================================================================
# DISPLAY / CAMERA SIZE
# If your webcam lags or doesn't support 1080p, set CAM_W/CAM_H to 1280x720.
# The preview is always scaled up to DISPLAY_W x DISPLAY_H.
# ======================================================================
DISPLAY_W, DISPLAY_H = 1920, 1080
CAM_W, CAM_H = 1920, 1080

# ======================================================================
# 3 SENSITIVITY PRESETS (Press 'M' in test window or call set_sensitivity)
# ======================================================================
PRESETS = {
    "BALANCED": {
        "anchor_vis": 0.52,
        "limb_vis": 0.45,
        "rom_scale": 1.0,
        "hold_frames": 2,
    },
    "CONVENIENT": {
        "anchor_vis": 0.42,
        "limb_vis": 0.35,
        "rom_scale": 0.82,
        "hold_frames": 1,
    },
    "STRICT": {
        "anchor_vis": 0.65,
        "limb_vis": 0.58,
        "rom_scale": 1.12,
        "hold_frames": 3,
    },
}

SMOOTHING = 0.55

# ======================================================================
# MINIMUM TIME (seconds) BETWEEN TWO COUNTED REPS PER EXERCISE
# A rep can never be counted sooner than this after the previous one.
# Raise a number to make that exercise stricter, lower it to make it faster.
# ======================================================================
REP_COOLDOWN = {
    "ARM_RAISE": 0.8,
    "BICEP_CURL": 1.0,
    "SHOULDER_PRESS": 1.2,
    "SQUAT": 1.5,
    "PUSHUP": 1.4,
    "MARCH": 0.35,
    "JUMPING_JACK": 0.6,
    "JUMP_ROPE": 0.3,
    "PUNCH": 0.3,
    "JAB_CROSS": 0.3,
    "BLOCK": 0.8,
    "FRONT_KICK": 0.8,
    "HIGH_KICK": 0.8,
}

# ======================================================================
# THE 15 OFFICIAL GAME EXERCISES (Plus Legacy Aliases)
# ======================================================================
PLAYABLE_EXERCISES = [
    "STR_1_ARM_RAISES",      # 1. Arm Raise
    "STR_2_BICEP_CURLS",     # 2. Bicep Curl
    "STR_3_SHOULDER_PRESS",  # 3. Shoulder Press
    "STR_4_SQUATS",          # 4. Squats
    "STR_7_PUSHUPS",         # 5. Pushups (Fixed for side & angled view!)
    "STR_8_PLANK",           # 6. Plank
    "CAR_1_MARCHING",        # 7. Marching
    "CAR_3_JUMPING_JACKS",   # 8. Jumping Jack (Fixed: requires hands + leg jump!)
    "CAR_7_JUMP_ROPE",       # 9. Jumping Rope (Fixed: blocks walking forward/back!)
    "MA_2_PUNCHES",          # 10. Punch
    "MA_3_JAB_CROSS",        # 11. Jab Cross
    "MA_1_GUARD",            # 12. Guard (Fixed: requires BOTH hands up!)
    "MA_4_BLOCKS",           # 13. Block
    "MA_6_FRONT_KICKS",      # 14. Front Kick
    "MA_7_HIGH_KICKS",       # 15. High Kick (foot must go high, above the knee)
]

ALIAS_MAP = {
    "ARM_RAISES": "STR_1_ARM_RAISES",
    "ARM_RAISE": "STR_1_ARM_RAISES",
    "BICEP_CURLS": "STR_2_BICEP_CURLS",
    "BICEP_CURL": "STR_2_BICEP_CURLS",
    "SHOULDER_PRESS": "STR_3_SHOULDER_PRESS",
    "SQUATS": "STR_4_SQUATS",
    "SQUAT": "STR_4_SQUATS",
    "PUSHUPS": "STR_7_PUSHUPS",
    "PUSHUP": "STR_7_PUSHUPS",
    "PLANK": "STR_8_PLANK",
    "MARCHING": "CAR_1_MARCHING",
    "JUMPING_JACKS": "CAR_3_JUMPING_JACKS",
    "JUMPING_JACK": "CAR_3_JUMPING_JACKS",
    "JUMP_ROPE": "CAR_7_JUMP_ROPE",
    "JUMPING_ROPE": "CAR_7_JUMP_ROPE",
    "PUNCH": "MA_2_PUNCHES",
    "PUNCHES": "MA_2_PUNCHES",
    "JAB_CROSS": "MA_3_JAB_CROSS",
    "GUARD": "MA_1_GUARD",
    "BLOCK": "MA_4_BLOCKS",
    "BLOCKS": "MA_4_BLOCKS",
    "FRONT_KICK": "MA_6_FRONT_KICKS",
    "FRONT_KICKS": "MA_6_FRONT_KICKS",
    "HIGH_KICK": "MA_7_HIGH_KICKS",
    "HIGH_KICKS": "MA_7_HIGH_KICKS",
}

EXERCISES = PLAYABLE_EXERCISES + ["MA_POWER_PUNCHES"] + list(ALIAS_MAP.keys())


class SmoothPoint:
    def __init__(self, x, y, z, v):
        self.x, self.y, self.z, self.visibility = x, y, z, v


class VisionEngine:
    def __init__(self, sensitivity="BALANCED"):
        # ---- SHARED VARIABLES (teammates read these in Pygame) ----
        self.reps = 0
        self.stage = "UP"
        self.current_exercise = "STR_7_PUSHUPS"
        self.feedback = "Step into frame!"
        self.latest_frame = None       # RGB frame ready for Pygame
        self.in_frame = False          # True when a body is confidently detected
        self.debug_value = 0.0         # live metric being tracked
        self.progress = 0.0            # 0.0 to 1.0 progress bar for current rep
        self.sensitivity = sensitivity if sensitivity in PRESETS else "BALANCED"
        self.running = False
        self.thread = None

        # ---- SMOOTHING & AUTO-CALIBRATION TRACKERS ----
        self.smooth_lm = None
        self.base_sh_y = None
        self.base_sh_w = None
        self.calib_samples = deque(maxlen=15)

        self.x_center_hist = deque(maxlen=12)
        self.y_bounce_hist = deque(maxlen=8)   # Short window for crisp jump detection
        self.sh_w_hist = deque(maxlen=10)      # Tracks shoulder-width changes to reject forward/back walking
        self.pushup_ang_hist = deque(maxlen=3)
        self.hold_frames = 0
        self.last_rep_time = 0
        self.jump_air_time = 0.0

        self.hold_accum = 0.0
        self.grace_timer = 0.0
        self.last_frame_time = time.time()
        self.last_side = None

        # ---- ANTI-FAKE PUNCH STATE TRACKERS ----
        self.punch_state = {"L": "NEED_GUARD", "R": "NEED_GUARD"}
        self.guard_hold_frames = {"L": 0, "R": 0}
        self.guard_origin = {"L": None, "R": None}
        self.punch_start_time = {"L": 0.0, "R": 0.0}
        self.last_punch_speed = 0.0

        # ---- MODEL ----
        self.model_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "pose_landmarker_full.task"
        )
        if not os.path.exists(self.model_path):
            print("Downloading FULL AI Pose Model (~9MB)...")
            url = (
                "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
                "pose_landmarker_full/float16/latest/pose_landmarker_full.task"
            )
            urllib.request.urlretrieve(url, self.model_path)

        self.BODY_CONNECTIONS = [
            (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
            (11, 23), (12, 24), (23, 24),
            (23, 25), (25, 27), (24, 26), (26, 28),
        ]

    # ------------------------------------------------------------------
    # PUBLIC FUNCTIONS
    # ------------------------------------------------------------------
    def start(self):
        if self.thread is not None and self.thread.is_alive():
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

    def set_sensitivity(self, mode):
        if mode in PRESETS:
            self.sensitivity = mode
            self.feedback = f"Mode set to {mode}!"

    def recalibrate(self):
        self.base_sh_y = None
        self.base_sh_w = None
        self.calib_samples.clear()
        self.feedback = "Recalibrated to your current position!"

    def set_exercise(self, name):
        name = ALIAS_MAP.get(name, name)
        if name not in EXERCISES:
            raise ValueError(f"Unknown exercise {name}. Choose from PLAYABLE_EXERCISES.")

        self.current_exercise = name
        self.reps = 0
        self.hold_frames = 0
        self.hold_accum = 0.0
        self.grace_timer = 0.0
        self.progress = 0.0
        self.last_side = None
        self.x_center_hist.clear()
        self.y_bounce_hist.clear()
        self.sh_w_hist.clear()
        self.pushup_ang_hist.clear()
        self.punch_state = {"L": "NEED_GUARD", "R": "NEED_GUARD"}
        self.guard_hold_frames = {"L": 0, "R": 0}
        self.guard_origin = {"L": None, "R": None}
        self.stage = "UP"
        self.feedback = f"Ready: {name}!"

    def add_cheat_rep(self):
        self.reps += 1
        self.progress = 1.0
        self.feedback = "COMPLETED! (Demo Override)"

    # ------------------------------------------------------------------
    # CONFIDENCE GATING & GEOMETRY HELPERS
    # ------------------------------------------------------------------
    def _cfg(self):
        return PRESETS[self.sensitivity]

    def _smooth_landmarks(self, raw_lm):
        if self.smooth_lm is None:
            self.smooth_lm = [SmoothPoint(p.x, p.y, p.z, p.visibility) for p in raw_lm]
        else:
            a = SMOOTHING
            for i, p in enumerate(raw_lm):
                s = self.smooth_lm[i]
                s.x = a * p.x + (1.0 - a) * s.x
                s.y = a * p.y + (1.0 - a) * s.y
                s.z = a * p.z + (1.0 - a) * s.z
                s.visibility = a * p.visibility + (1.0 - a) * s.visibility
        return self.smooth_lm

    def _in_screen(self, p, margin=0.02):
        return margin < p.x < (1.0 - margin) and margin < p.y < (1.0 - margin)

    def _vis(self, lm, idx, min_v=None):
        if min_v is None:
            min_v = self._cfg()["limb_vis"]
        p = lm[idx]
        return p.visibility >= min_v and -0.05 < p.x < 1.05 and -0.05 < p.y < 1.05

    def _anchors_ready(self, lm):
        # Floor / side-profile exercises (Pushups & Plank) have lower nose visibility when looking at the floor
        if self.current_exercise in ("STR_7_PUSHUPS", "STR_8_PLANK"):
            sh_ok = (
                (lm[11].visibility >= 0.35 and self._in_screen(lm[11], 0.01)) or
                (lm[12].visibility >= 0.35 and self._in_screen(lm[12], 0.01))
            )
            return sh_ok

        av = self._cfg()["anchor_vis"]
        nose_ok = lm[0].visibility >= av and self._in_screen(lm[0], 0.02)
        sh_ok = (
            (lm[11].visibility >= av and self._in_screen(lm[11], 0.02)) or
            (lm[12].visibility >= av and self._in_screen(lm[12], 0.02))
        )
        sh_w = abs(lm[11].x - lm[12].x)
        return nose_ok and sh_ok and (sh_w < 0.72)

    def _either_arm_visible(self, lm, min_v=None):
        v = self._cfg()["limb_vis"] if min_v is None else min_v
        left_ok = self._vis(lm, 13, v) and self._vis(lm, 15, v) and self._in_screen(lm[15], 0.01)
        right_ok = self._vis(lm, 14, v) and self._vis(lm, 16, v) and self._in_screen(lm[16], 0.01)
        return left_ok or right_ok

    def _lower_body_visible(self, lm):
        v = self._cfg()["limb_vis"]
        hips = self._vis(lm, 23, v) or self._vis(lm, 24, v)
        knees = (self._vis(lm, 25, v) and lm[25].y < 0.96) or (self._vis(lm, 26, v) and lm[26].y < 0.96)
        return hips and knees

    def _scale(self, lm):
        sh_w = abs(lm[11].x - lm[12].x)
        sh_y = (lm[11].y + lm[12].y) / 2.0
        head_sh = abs(sh_y - lm[0].y) * 1.8
        if self._vis(lm, 23, 0.45) and self._vis(lm, 24, 0.45):
            hip_y = (lm[23].y + lm[24].y) / 2.0
            torso = float(np.hypot((lm[23].x + lm[24].x) / 2.0 - (lm[11].x + lm[12].x) / 2.0, hip_y - sh_y))
            return max(torso, sh_w * 1.2, head_sh, 0.12)
        return max(sh_w * 1.35, head_sh, 0.12)

    def _angle(self, a, b, c):
        a, b, c = np.array(a), np.array(b), np.array(c)
        rad = np.arctan2(c[1] - b[1], c[0] - b[0]) - np.arctan2(a[1] - b[1], a[0] - b[0])
        ang = np.abs(rad * 180.0 / np.pi)
        return 360.0 - ang if ang > 180.0 else ang

    def _xy(self, lm, idx):
        return [lm[idx].x, lm[idx].y]

    def _dist(self, lm, i, j):
        return float(np.hypot(lm[i].x - lm[j].x, lm[i].y - lm[j].y))

    def _best_arm(self, lm):
        """Picks the side (sh, el, wr, hip) with the highest ARM visibility (crucial for side push-ups)."""
        l_score = lm[11].visibility + lm[13].visibility + lm[15].visibility
        r_score = lm[12].visibility + lm[14].visibility + lm[16].visibility
        return (11, 13, 15, 23) if l_score >= r_score else (12, 14, 16, 24)

    def _update_baseline(self, lm):
        sh_y = (lm[11].y + lm[12].y) / 2.0
        sh_w = abs(lm[11].x - lm[12].x)
        if 0.12 < sh_y < 0.65 and 0.10 < sh_w < 0.55:
            self.calib_samples.append((sh_y, sh_w))
            if self.base_sh_y is None and len(self.calib_samples) >= 5:
                arr = np.array(self.calib_samples)
                self.base_sh_y = float(np.median(arr[:, 0]))
                self.base_sh_w = float(np.median(arr[:, 1]))
            elif self.base_sh_y is not None and self.stage == "UP":
                self.base_sh_y = 0.995 * self.base_sh_y + 0.005 * sh_y
                self.base_sh_w = 0.995 * self.base_sh_w + 0.005 * sh_w

    # ------------------------------------------------------------------
    # CORE EXERCISE ENGINES (Rep, Hold, Alternate)
    # ------------------------------------------------------------------
    def _count(self, at_top, at_bottom, now, cooldown, msg_bottom, msg_rep, hold=None):
        if hold is None:
            hold = self._cfg()["hold_frames"]

        if at_bottom:
            self.progress = 0.25
            if self.stage == "UP":
                self.hold_frames += 1
                if self.hold_frames >= hold:
                    self.stage = "DOWN"
                    self.hold_frames = 0
                    self.feedback = msg_bottom
        elif at_top:
            self.progress = 1.0
            if self.stage == "DOWN":
                self.hold_frames += 1
                if self.hold_frames >= hold and (now - self.last_rep_time > cooldown):
                    self.stage = "UP"
                    self.hold_frames = 0
                    self.reps += 1
                    self.last_rep_time = now
                    self.feedback = msg_rep
        else:
            self.hold_frames = 0
            self.progress = 0.6 if self.stage == "DOWN" else 0.1

    def _hold(self, in_pose, dt, pose_name, hint_msg):
        if in_pose:
            self.grace_timer = 0.35
            self.stage = "HOLDING"
            self.hold_accum += dt
            self.progress = min(1.0, (self.hold_accum % 1.0))
            self.debug_value = self.hold_accum
            new_seconds = int(self.hold_accum)
            if new_seconds > self.reps:
                self.reps = new_seconds
                self.progress = 1.0
            self.feedback = f"Holding {pose_name}... {self.hold_accum:.1f}s!"
        else:
            if self.grace_timer > 0:
                self.grace_timer -= dt
                self.hold_accum += dt
            else:
                self.stage = "ADJUST"
                self.progress = 0.0
                self.feedback = hint_msg

    def _alternate(self, left_active, right_active, now, cooldown, move_name):
        if left_active and not right_active and self.last_side != "LEFT":
            if now - self.last_rep_time > cooldown:
                self.last_side = "LEFT"
                self.stage = "LEFT"
                self.reps += 1
                self.progress = 1.0
                self.last_rep_time = now
                self.feedback = f"Left {move_name}! Now Right!"
        elif right_active and not left_active and self.last_side != "RIGHT":
            if now - self.last_rep_time > cooldown:
                self.last_side = "RIGHT"
                self.stage = "RIGHT"
                self.reps += 1
                self.progress = 1.0
                self.last_rep_time = now
                self.feedback = f"Right {move_name}! Now Left!"
        else:
            self.progress = 0.35

    def _draw(self, rgb, lm):
        h, w, _ = rgb.shape
        v_thresh = self._cfg()["limb_vis"]
        # Scale line thickness with resolution so the skeleton stays visible at 1080p
        thickness = max(3, int(h / 160))
        for s, e in self.BODY_CONNECTIONS:
            seen = lm[s].visibility >= v_thresh and lm[e].visibility >= v_thresh
            color = (0, 255, 0) if seen else (110, 110, 110)
            p1 = (int(lm[s].x * w), int(lm[s].y * h))
            p2 = (int(lm[e].x * w), int(lm[e].y * h))
            cv2.line(rgb, p1, p2, color, thickness)

    # ------------------------------------------------------------------
    # POSE DETECTORS
    # ------------------------------------------------------------------
    def _squat_metric(self, lm):
        if self._lower_body_visible(lm):
            knee_y = (lm[25].y + lm[26].y) / 2.0
            hip_y = (lm[23].y + lm[24].y) / 2.0
            sh_y = (lm[11].y + lm[12].y) / 2.0
            torso = max(abs(hip_y - sh_y), 0.12)
            return (knee_y - hip_y) / torso
        else:
            sh_y = (lm[11].y + lm[12].y) / 2.0
            base_y = self.base_sh_y if self.base_sh_y is not None else 0.38
            scale = self._scale(lm)
            drop = (sh_y - base_y) / scale
            return 0.80 - drop * 0.85

    def _pose_plank_or_lean(self, lm):
        sh, el, wr, hip = self._best_arm(lm)
        if self._vis(lm, hip, 0.35):
            # Side plank / push-up body angle
            if abs(lm[sh].x - lm[hip].x) > abs(lm[sh].y - lm[hip].y) * 0.48:
                return True
        hands_planted = self._either_arm_visible(lm, 0.30) and (lm[15].y > lm[11].y or lm[16].y > lm[12].y)
        sh_y = (lm[11].y + lm[12].y) / 2.0
        base_y = self.base_sh_y if self.base_sh_y is not None else 0.35
        return hands_planted and (sh_y > base_y + 0.08)

    def _evaluate_arm_punch(self, lm, side_char, sh_w, scale):
        sh, el, wr = (11, 13, 15) if side_char == "L" else (12, 14, 16)
        v_req = max(0.50, self._cfg()["limb_vis"])
        if not (self._vis(lm, sh, v_req) and self._vis(lm, el, v_req) and
                self._vis(lm, wr, v_req) and self._in_screen(lm[wr], 0.02)):
            return False, False, 0.0

        highest_allowed = lm[0].y - 0.15 * scale
        lowest_allowed = lm[sh].y + 0.25 * scale
        if not (highest_allowed <= lm[wr].y <= lowest_allowed):
            return False, False, 0.0

        ang = self._angle(self._xy(lm, sh), self._xy(lm, el), self._xy(lm, wr))
        reach = self._dist(lm, sh, wr) / max(sh_w, 0.10)
        nose_dist = self._dist(lm, 0, wr) / max(sh_w, 0.10)
        rom = self._cfg()["rom_scale"]

        # Guard: Elbow bent AND hand tucked near chin/cheek/shoulder (wrist above elbow)
        in_guard = (
            (ang < 110 and reach < 0.75 and lm[wr].y < lm[el].y - 0.01) or
            (nose_dist < 0.65 and reach < 0.72 and lm[wr].y < lm[el].y)
        )

        is_punch = False
        origin = self.guard_origin[side_char]
        if not in_guard and origin is not None:
            gx, gy, g_reach = origin
            wrist_travel = float(np.hypot(lm[wr].x - gx, lm[wr].y - gy)) / max(sh_w, 0.10)
            reach_gain = reach - g_reach

            extended_out = (ang > 136 * rom and reach > 0.90 * rom) or (ang > 128 * rom and reach > 1.05 * rom)
            traveled_enough = (wrist_travel >= 0.28 * rom) and (reach_gain >= 0.22 * rom)
            is_punch = extended_out and traveled_enough

        score = float(np.clip((reach - 0.55) / 0.50, 0.0, 1.0)) if not in_guard else 0.15
        return in_guard, is_punch, score

    # ------------------------------------------------------------------
    # MASTER ROUTER FOR THE 14 EXERCISES
    # ------------------------------------------------------------------
    def _process_exercise(self, lm, now, dt):
        if not self._anchors_ready(lm):
            self.stage = "STEP IN"
            self.hold_frames = 0
            self.feedback = "Center your upper body in the camera!"
            return

        # If we were stuck on the "STEP IN" label, go back to a real rep stage (otherwise no rep can ever count)
        if self.stage == "STEP IN":
            self.stage = "UP"

        self._update_baseline(lm)

        ex = self.current_exercise
        sh_y = (lm[11].y + lm[12].y) / 2.0
        sh_x = (lm[11].x + lm[12].x) / 2.0
        sh_w = abs(lm[11].x - lm[12].x) + 1e-6
        scale = self._scale(lm)
        rom = self._cfg()["rom_scale"]

        self.x_center_hist.append(sh_x)
        self.y_bounce_hist.append(sh_y)
        self.sh_w_hist.append(sh_w)

        # ==================== 1. ARM RAISE ====================
        if ex == "STR_1_ARM_RAISES":
            if not self._either_arm_visible(lm):
                self.feedback = "Show at least one hand in the frame!"
                return
            vis_wrists = [lm[i].y for i in (15, 16) if self._vis(lm, i) and self._in_screen(lm[i], 0.01)]
            if not vis_wrists:
                return
            top_hand = min(vis_wrists)
            self.debug_value = lm[0].y - top_hand
            self._count(top_hand < lm[0].y, top_hand > sh_y + 0.05 * scale,
                        now, REP_COOLDOWN["ARM_RAISE"], "Drop hand below shoulder, then raise above nose!", "Clean Arm Raise!")

        # ==================== 2. BICEP CURL ====================
        elif ex == "STR_2_BICEP_CURLS":
            if not self._either_arm_visible(lm):
                self.feedback = "Keep your arms & hands visible in frame!"
                return
            curled, extended, best_ang = False, False, 180.0
            for sh, el, wr in ((11, 13, 15), (12, 14, 16)):
                if self._vis(lm, el) and self._vis(lm, wr) and self._in_screen(lm[wr], 0.02):
                    ang = self._angle(self._xy(lm, sh), self._xy(lm, el), self._xy(lm, wr))
                    best_ang = min(best_ang, ang)
                    if lm[wr].y < lm[el].y - 0.02 * scale and ang < 112:
                        curled = True
                    if lm[wr].y > lm[el].y + 0.18 * scale and ang > 125:
                        extended = True
            self.debug_value = best_ang
            self._count(curled, extended, now, REP_COOLDOWN["BICEP_CURL"], "Curl hands UP toward your shoulders!", "Nice Bicep Curl!")

        # ==================== 3. SHOULDER PRESS ====================
        elif ex == "STR_3_SHOULDER_PRESS":
            if not (self._vis(lm, 15) and self._vis(lm, 16)):
                self.feedback = "Show BOTH hands for Shoulder Press!"
                return
            both_up = lm[15].y < lm[0].y - 0.02 and lm[16].y < lm[0].y - 0.02
            at_sh = (lm[0].y + 0.02 < lm[15].y < sh_y + 0.35 * scale) and (lm[0].y + 0.02 < lm[16].y < sh_y + 0.35 * scale)
            self._count(both_up, at_sh, now, REP_COOLDOWN["SHOULDER_PRESS"], "Bring hands to shoulders, then press OVERHEAD!", "Strong Shoulder Press!")

        # ==================== 4. SQUATS (ADAPTIVE: LEARNS YOUR OWN STANDING & BOTTOM HEIGHT) ====================
        elif ex == "STR_4_SQUATS":
            if self.stage not in ("UP", "DOWN"):
                self.stage = "UP"

            # Head + shoulder height is always visible (the anchors need it), so the signal never flickers.
            y_now = (lm[0].y + sh_y) / 2.0

            # Time-based window (last 4 seconds) so it works at any camera frame rate
            win = getattr(self, "_sq_win", None)
            if win is None:
                win = self._sq_win = deque(maxlen=600)
            win.append((now, y_now))
            while win and now - win[0][0] > 4.0:
                win.popleft()
            ys = np.array([v for _, v in win])

            # In image coordinates a SMALLER y means higher up on screen
            stand_y = float(np.percentile(ys, 3))        # standing tall (highest point)
            deep_y = float(np.percentile(ys, 97))        # squatted (lowest point)
            rng = deep_y - stand_y
            min_rng = 0.18 * scale * rom                 # must drop at least ~18% of your torso length

            if len(ys) < 10 or rng < min_rng:
                self.progress = 0.1 if self.stage == "UP" else 0.6
                if now - self.last_rep_time > 1.5:
                    self.feedback = "Stand tall, then squat down deep, then stand up!"
                return

            frac = (y_now - stand_y) / rng               # 0.0 = standing tall, 1.0 = deepest squat
            self.debug_value = frac
            self.progress = float(np.clip(0.25 + 0.75 * (1.0 - frac), 0.0, 1.0))

            # Stricter zones: really deep to go down, really tall to finish the rep
            near_bottom = frac > 0.80
            near_top = frac < 0.20

            # The needed position must be held briefly (0.15s), so a single noisy frame can't flip the stage
            want = near_bottom if self.stage == "UP" else near_top
            if want:
                if getattr(self, "_sq_hold_t", None) is None:
                    self._sq_hold_t = now
            else:
                self._sq_hold_t = None
            held = getattr(self, "_sq_hold_t", None) is not None and (now - self._sq_hold_t) >= 0.15

            if self.stage == "UP":
                if held:
                    self.stage = "DOWN"
                    self._sq_down_t = now
                    self._sq_hold_t = None
                    self.feedback = "Good depth! Stand all the way UP!"
                elif frac > 0.45:
                    self.feedback = "Go deeper! Sink your hips lower!"
            elif self.stage == "DOWN":
                # Rep counts only after standing fully tall, at least 0.6s after reaching the bottom
                if held and (now - getattr(self, "_sq_down_t", 0.0)) >= 0.6 \
                        and (now - self.last_rep_time > REP_COOLDOWN["SQUAT"]):
                    self.stage = "UP"
                    self._sq_hold_t = None
                    self.reps += 1
                    self.last_rep_time = now
                    self.feedback = "Great Squat!"
                elif not near_top:
                    self.feedback = "Good depth! Stand all the way UP!"

        # ==================== 5. PUSHUPS (ADAPTIVE: LEARNS YOUR OWN TOP/BOTTOM, ANY CAMERA ANGLE) ====================
        elif ex == "STR_7_PUSHUPS":
            sh, el, wr, hip = self._best_arm(lm)
            # Forgiving visibility threshold (0.25) because hands flat on the floor often score lower
            if not (self._vis(lm, sh, 0.35) and self._vis(lm, el, 0.30) and self._vis(lm, wr, 0.25)):
                self.pushup_ang_hist.clear()
                self.feedback = "Make sure your front arm (shoulder, elbow, hand) is in frame!"
                return

            # Hands should be at or below shoulder level (not raised overhead)
            if lm[wr].y < lm[sh].y - 0.08:
                self.pushup_ang_hist.clear()
                self.feedback = "Place hands on the floor/desk below your shoulders!"
                return

            # STRICT POSTURE GATE: the body must actually be leaning/horizontal (plank), not standing.
            # Needs the hip visible so we can measure how far the torso is tilted from vertical.
            lying_ok = False
            if self._vis(lm, hip, 0.35):
                t_dx = abs(lm[sh].x - lm[hip].x)
                t_dy = abs(lm[hip].y - lm[sh].y) + 1e-6
                lying_ok = t_dx > t_dy * 0.75      # torso tilted more than ~37 deg from vertical
            if not lying_ok:
                self.pushup_ang_hist.clear()
                win_old = getattr(self, "_pu_win", None)
                if win_old is not None:
                    win_old.clear()
                self.stage = "UP"
                self.progress = 0.0
                self.feedback = "Get into a push-up plank position (body low & horizontal, hips in view)!"
                return

            # Elbow angle: median of last 3 frames kills one-frame landmark spikes
            ang = self._angle(self._xy(lm, sh), self._xy(lm, el), self._xy(lm, wr))
            self.pushup_ang_hist.append(ang)
            smooth_ang = float(np.median(self.pushup_ang_hist))
            self.debug_value = smooth_ang

            # Rolling window of recent angles (about 3 seconds). The top and bottom of YOUR push-up
            # are learned from it, so it works from the side, at an angle, or on an incline.
            win = getattr(self, "_pu_win", None)
            if win is None:
                win = self._pu_win = deque(maxlen=75)
            win.append(smooth_ang)

            hi = float(np.percentile(win, 90))   # arms straight (top)
            lo = float(np.percentile(win, 10))   # elbows bent (bottom)
            rng = hi - lo
            min_rng = 22.0 * rom                 # must move at least ~22 degrees to count as a push-up

            if len(win) < 15 or rng < min_rng:
                self.progress = 0.1 if self.stage == "UP" else 0.6
                if now - self.last_rep_time > 1.5:
                    self.feedback = "Lower your chest (bend elbows), then push all the way up!"
                return

            frac = (smooth_ang - lo) / rng       # 0.0 = deepest, 1.0 = fully straight
            self.progress = float(np.clip(0.25 + 0.75 * frac, 0.0, 1.0))

            near_bottom = frac < 0.30 and smooth_ang < (140.0 / rom)
            near_top = frac > 0.70

            if self.stage == "UP":
                if near_bottom:
                    self.stage = "DOWN"
                    self.feedback = "Chest down! Now push UP!"
                elif not near_top:
                    self.feedback = "Go lower! Bend your elbows more for a full rep!"
            elif self.stage == "DOWN":
                if near_top and (now - self.last_rep_time > REP_COOLDOWN["PUSHUP"]):
                    self.stage = "UP"
                    self.reps += 1
                    self.last_rep_time = now
                    self.feedback = "Power Push-up!"

        # ==================== 6. PLANK ====================
        elif ex == "STR_8_PLANK":
            self._hold(self._pose_plank_or_lean(lm), dt, "Plank", "Hold a horizontal or incline plank position!")

        # ==================== 7. MARCHING ====================
        elif ex == "CAR_1_MARCHING":
            if self._lower_body_visible(lm):
                diff = (lm[26].y - lm[25].y) / scale
            else:
                diff = ((lm[16].y - lm[15].y) + (lm[12].y - lm[11].y)) / scale
            self.debug_value = diff
            thresh = 0.06 * rom
            self._alternate(diff > thresh, diff < -thresh, now, REP_COOLDOWN["MARCH"], "March Step")

        # ==================== 8. JUMPING JACK (FIXED: HANDS + LEG SPREAD/JUMP) ====================
        elif ex == "CAR_3_JUMPING_JACKS":
            if not (self._vis(lm, 15, 0.35) and self._vis(lm, 16, 0.35)):
                self.feedback = "Show BOTH hands in frame!"
                return

            # 1. Both hands must go overhead (top) and both drop below shoulders (bottom)
            hands_up = (lm[15].y < lm[0].y + 0.04) and (lm[16].y < lm[0].y + 0.04)
            hands_down = (lm[15].y > sh_y + 0.12 * scale) and (lm[16].y > sh_y + 0.12 * scale)

            # 2. Check Leg Spread (Ankles 27/28 or Knees 25/26)
            ankles_ok = self._vis(lm, 27, 0.35) and self._vis(lm, 28, 0.35)
            knees_ok = self._vis(lm, 25, 0.35) and self._vis(lm, 26, 0.35)

            if ankles_ok:
                leg_ratio = abs(lm[27].x - lm[28].x) / sh_w
                legs_wide = leg_ratio > (1.18 * rom)
                legs_closed = leg_ratio < (1.02 / rom)
            elif knees_ok:
                leg_ratio = abs(lm[25].x - lm[26].x) / sh_w
                legs_wide = leg_ratio > (0.86 * rom)
                legs_closed = leg_ratio < (0.76 / rom)
            else:
                self.feedback = "Step back slightly so your legs/knees are visible for Jumping Jacks!"
                return

            self.debug_value = leg_ratio

            # Helpful prompt if player only raises hands without jumping feet apart
            if hands_up and not legs_wide and self.stage == "DOWN":
                self.feedback = "Jump your FEET wide apart too, not just your hands!"
                return

            self._count(hands_up and legs_wide, hands_down and legs_closed,
                        now, REP_COOLDOWN["JUMPING_JACK"], "Now JUMP (both hands overhead + feet wide)!", "Jumping Jack!", hold=1)

        # ==================== 9. JUMPING ROPE (FIXED: REJECTS FORWARD/BACKWARD WALKING) ====================
        elif ex == "CAR_7_JUMP_ROPE":
            if len(self.y_bounce_hist) < 5 or len(self.sh_w_hist) < 5:
                self.feedback = "Stand still for a moment to lock jump baseline..."
                return

            # 1. ANTI-WALK SHIELD: Walking forward/backward changes apparent shoulder width (sh_w)
            #    and walking sideways shifts sh_x. Jumping in place keeps sh_w and sh_x steady!
            mean_w = float(np.mean(self.sh_w_hist))
            w_change_ratio = abs(sh_w - mean_w) / max(mean_w, 0.08)
            x_drift = abs(sh_x - float(np.mean(self.x_center_hist)))

            # Also check if knees are stepping alternately (walking gait) vs jumping together
            walking_knees = False
            if self._vis(lm, 25, 0.4) and self._vis(lm, 26, 0.4):
                walking_knees = abs(lm[25].y - lm[26].y) / scale > 0.08

            if w_change_ratio > 0.028 or x_drift > 0.032 or walking_knees:
                self.stage = "UP"
                self.hold_frames = 0
                self.feedback = "Stay in one spot and hop with both feet! (Walking ignored)"
                return

            # 2. ROPE-HOLD POSTURE CHECK: Wrists should be near waist/hip/rib level
            if self._either_arm_visible(lm, 0.35):
                wr_ok = (
                    (self._vis(lm, 15, 0.35) and (sh_y + 0.08 * scale < lm[15].y < sh_y + 1.25 * scale)) or
                    (self._vis(lm, 16, 0.35) and (sh_y + 0.08 * scale < lm[16].y < sh_y + 1.25 * scale))
                )
                if not wr_ok:
                    self.feedback = "Keep hands near waist height like holding a jump rope!"
                    return

            # 3. TRUE VERTICAL HOP DETECTOR (sensitive to small rope hops, scaled to body size)
            # Average nose + both shoulders so landmark noise cancels out and tiny hops show up clearly
            body_y = float(np.mean([lm[0].y, lm[11].y, lm[12].y]))
            jh = getattr(self, "_jr_hist", None)
            if jh is None:
                jh = self._jr_hist = deque(maxlen=10)
            jh.append(body_y)

            # Positive = body is higher than its recent average (airborne). Divided by body size so the
            # same small hop counts whether you stand close to the camera or far away.
            bounce = (float(np.mean(jh)) - body_y) / scale
            self.debug_value = bounce * 100.0

            hop_thr = 0.075 * rom          # minimum jump height (fraction of body size). Higher = needs a bigger jump
            hop_up = bounce > hop_thr

            if hop_up and self.stage == "UP" and (now - self.last_rep_time > REP_COOLDOWN["JUMP_ROPE"]):
                self.stage = "DOWN"        # Airborne!
                self.jump_air_time = now
                self._jr_peak = bounce
                self.progress = 0.5
                self.feedback = "Airborne! Land to complete hop!"
            elif self.stage == "DOWN":
                self._jr_peak = max(getattr(self, "_jr_peak", bounce), bounce)
                # Landed = came back down to under 40% of this hop's own peak (works for tiny and big hops)
                landed = bounce < 0.4 * self._jr_peak
                if (now - self.jump_air_time) > 0.55:
                    # Too slow to be a hop (a posture shift), so reset without counting
                    self.stage = "UP"
                elif landed:
                    self.stage = "UP"
                    self.reps += 1
                    self.progress = 1.0
                    self.last_rep_time = now
                    self.feedback = "Jump Rope Hop!"

        # ==================== 10 & 11. PUNCH & JAB CROSS ====================
        elif ex in ("MA_2_PUNCHES", "MA_3_JAB_CROSS", "MA_POWER_PUNCHES"):
            if not self._either_arm_visible(lm):
                self.feedback = "Bring your fists up into the camera frame!"
                return

            l_guard, l_punch, l_score = self._evaluate_arm_punch(lm, "L", sh_w, scale)
            r_guard, r_punch, r_score = self._evaluate_arm_punch(lm, "R", sh_w, scale)
            self.debug_value = max(l_score, r_score)
            self.progress = max(l_score, r_score)

            for side, is_g, wr_idx, sh_idx in (("L", l_guard, 15, 11), ("R", r_guard, 16, 12)):
                if is_g:
                    self.guard_hold_frames[side] += 1
                    if self.guard_hold_frames[side] >= 2:
                        self.punch_state[side] = "READY"
                        cur_reach = self._dist(lm, sh_idx, wr_idx) / max(sh_w, 0.10)
                        self.guard_origin[side] = (lm[wr_idx].x, lm[wr_idx].y, cur_reach)
                        self.punch_start_time[side] = now
                else:
                    self.guard_hold_frames[side] = 0

            def get_punch_speed(side):
                flight_time = max(0.05, now - self.punch_start_time[side])
                spd = float(np.clip((0.48 - flight_time) / 0.38 * 100.0, 10.0, 100.0))
                return flight_time, spd

            if ex in ("MA_2_PUNCHES", "MA_POWER_PUNCHES"):
                max_time = 0.35 if ex == "MA_POWER_PUNCHES" else 9.9
                self.stage = f"L:{self.punch_state['L'][0]} R:{self.punch_state['R'][0]}"

                if l_punch and self.punch_state["L"] == "READY" and (now - self.last_rep_time > REP_COOLDOWN["PUNCH"]):
                    self.punch_state["L"] = "PUNCHED"
                    ft, spd = get_punch_speed("L")
                    self.last_punch_speed = spd
                    if ft <= max_time:
                        self.reps += 1
                        self.progress = 1.0
                        self.last_rep_time = now
                        self.feedback = f"LEFT PUNCH! ({spd:.0f} PWR) Pull fist back to chin!"
                    else:
                        self.feedback = f"Too slow ({spd:.0f} PWR)! Snap punch faster!"

                elif r_punch and self.punch_state["R"] == "READY" and (now - self.last_rep_time > REP_COOLDOWN["PUNCH"]):
                    self.punch_state["R"] = "PUNCHED"
                    ft, spd = get_punch_speed("R")
                    self.last_punch_speed = spd
                    if ft <= max_time:
                        self.reps += 1
                        self.progress = 1.0
                        self.last_rep_time = now
                        self.feedback = f"RIGHT PUNCH! ({spd:.0f} PWR) Pull fist back to chin!"
                    else:
                        self.feedback = f"Too slow ({spd:.0f} PWR)! Snap punch faster!"

                elif self.punch_state["L"] != "READY" and self.punch_state["R"] != "READY":
                    self.feedback = "Tuck fists by your chin/cheeks (Guard) to reload!"
                elif (now - self.last_rep_time) > 1.0:
                    self.feedback = "Guard locked! Punch outward (slight angle works best)!"

            else:  # MA_3_JAB_CROSS
                self.stage = f"L:{self.punch_state['L'][0]} R:{self.punch_state['R'][0]}"
                if l_punch and self.punch_state["L"] == "READY" and self.last_side != "LEFT" and (now - self.last_rep_time > REP_COOLDOWN["JAB_CROSS"]):
                    self.punch_state["L"] = "PUNCHED"
                    self.last_side = "LEFT"
                    self.reps += 1
                    self.progress = 1.0
                    self.last_rep_time = now
                    self.feedback = "Left Jab! Now throw Right Cross!"
                elif r_punch and self.punch_state["R"] == "READY" and self.last_side != "RIGHT" and (now - self.last_rep_time > REP_COOLDOWN["JAB_CROSS"]):
                    self.punch_state["R"] = "PUNCHED"
                    self.last_side = "RIGHT"
                    self.reps += 1
                    self.progress = 1.0
                    self.last_rep_time = now
                    self.feedback = "Right Cross! Now throw Left Jab!"

        # ==================== 12. GUARD (FIXED: REQUIRES BOTH HANDS UP) ====================
        elif ex == "MA_1_GUARD":
            l_guard, _, _ = self._evaluate_arm_punch(lm, "L", sh_w, scale)
            r_guard, _, _ = self._evaluate_arm_punch(lm, "R", sh_w, scale)

            if (l_guard and not r_guard) or (r_guard and not l_guard):
                self.grace_timer = 0.0
                self.stage = "1 HAND ONLY"
                self.progress = 0.25
                self.feedback = "Raise BOTH fists up to your chin/cheeks (only 1 hand detected)!"
                return

            self._hold(l_guard and r_guard, dt, "Guard Stance", "Hold BOTH fists up near your chin/cheeks!")

        # ==================== 13. BLOCK ====================
        elif ex == "MA_4_BLOCKS":
            if not self._either_arm_visible(lm):
                self.feedback = "Show your arms in frame!"
                return
            high_block = (self._vis(lm, 15) and lm[15].y < lm[0].y + 0.06) or (self._vis(lm, 16) and lm[16].y < lm[0].y + 0.06)
            low_ready = (self._vis(lm, 15) and lm[15].y > sh_y + 0.06 * scale) or (self._vis(lm, 16) and lm[16].y > sh_y + 0.06 * scale)
            self._count(high_block, low_ready, now, REP_COOLDOWN["BLOCK"], "Raise forearms to block your face!", "Solid Block!", hold=1)

        # ==================== 14 & 15. FRONT KICK (LOWER BAR) / HIGH KICK (FOOT HIGH & ABOVE ITS OWN KNEE) ====================
        elif ex in ("MA_6_FRONT_KICKS", "MA_7_HIGH_KICKS"):
            is_high = (ex == "MA_7_HIGH_KICKS")
            kick_name = "High Kick" if is_high else "Front Kick"
            cd_key = "HIGH_KICK" if is_high else "FRONT_KICK"
            # Needs hips, knees and ankles in frame (step back from the camera)
            if not (self._vis(lm, 27, 0.30) and self._vis(lm, 28, 0.30) and
                    self._vis(lm, 25, 0.30) and self._vis(lm, 26, 0.30)):
                self.feedback = "Step back so your whole legs (hips to feet) are in frame!"
                return

            # How high each foot is above the OTHER foot, as a fraction of torso size (0 = both on the floor)
            rise_l = (lm[28].y - lm[27].y) / scale
            rise_r = (lm[27].y - lm[28].y) / scale
            # How far each foot is above its OWN knee (a real front kick puts the foot above the knee;
            # a high-knee march keeps the foot hanging below it)
            above_l = (lm[25].y - lm[27].y) / scale
            above_r = (lm[26].y - lm[28].y) / scale

            if is_high:
                need_rise, need_above = 0.45 * rom, 0.05   # HIGH KICK: foot clearly high, above the knee
            else:
                need_rise, need_above = 0.18 * rom, -0.10  # FRONT KICK: low bar, foot only needs to lift a bit (just below knee level is OK)
            act_l = rise_l > need_rise and above_l > need_above
            act_r = rise_r > need_rise and above_r > need_above
            self.debug_value = max(rise_l, rise_r)
            self.progress = float(np.clip(max(rise_l, rise_r) / (need_rise * 1.5), 0.0, 1.0))

            st = getattr(self, "_fk", None)
            if st is None or getattr(self, "_fk_ex", None) != ex:
                st = self._fk = {"L": None, "R": None}   # time the kick started (None = leg is down)
                self._fk_ex = ex

            both_up = act_l and act_r                    # both feet high = a jump, not a kick: ignore
            for side, act in (("L", act_l), ("R", act_r)):
                if act and not both_up:
                    if st[side] is None:
                        st[side] = now
                        self.stage = f"{side} KICK"
                elif not act and st[side] is not None:
                    dur = now - st[side]
                    st[side] = None
                    self.stage = "UP"
                    # Kick = foot went up, then came back down (not a leg held in the air)
                    if 0.10 <= dur <= 1.5 and (now - self.last_rep_time > REP_COOLDOWN[cd_key]):
                        self.reps += 1
                        self.progress = 1.0
                        self.last_rep_time = now
                        self.feedback = ("Left" if side == "L" else "Right") + f" {kick_name}! Pull the leg back!"

            if now - self.last_rep_time > 2.0 and not (act_l or act_r):
                self.feedback = ("Kick high: lift your foot above your knee!" if is_high
                                 else "Kick forward: lift your foot up and out in front of you!")


    # ------------------------------------------------------------------
    # BACKGROUND THREAD
    # ------------------------------------------------------------------
    def _loop(self):
        detector = None
        cap = None
        try:
            options = vision.PoseLandmarkerOptions(
                base_options=python.BaseOptions(model_asset_path=self.model_path),
                running_mode=vision.RunningMode.VIDEO,
                min_pose_detection_confidence=0.55,
                min_pose_presence_confidence=0.55,
                min_tracking_confidence=0.55,
            )
            detector = vision.PoseLandmarker.create_from_options(options)

            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                self.feedback = "Camera not found!"
                return

            # Ask the webcam for 1080p (it may fall back to a lower size if unsupported)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_W)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_H)

            start_time = time.time()
            self.last_frame_time = start_time
            last_ts = 0

            while self.running:
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.01)
                    continue

                now = time.time()
                dt = min(now - self.last_frame_time, 0.1)
                self.last_frame_time = now

                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                ts = int((now - start_time) * 1000)
                if ts <= last_ts:
                    ts = last_ts + 1
                last_ts = ts

                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                results = detector.detect_for_video(mp_image, ts)

                if results.pose_landmarks:
                    lm = self._smooth_landmarks(results.pose_landmarks[0])
                    self.in_frame = self._anchors_ready(lm)
                    self._draw(rgb, lm)
                    self._process_exercise(lm, now, dt)
                else:
                    self.in_frame = False
                    self.smooth_lm = None
                    self.feedback = "No body detected, step into the frame!"

                self.latest_frame = rgb
        finally:
            if cap is not None:
                cap.release()
            if detector is not None:
                detector.close()
            self.running = False


# ======================================================================
# TEST WINDOW FOR YOUR 14 CHOSEN EXERCISES: run `python vision_engine.py`
# Keys: [N/P]=Next/Prev | [M]=Mode | [C]=Calibrate | [Space]=Cheat | [Q]=Quit
# ======================================================================
if __name__ == "__main__":
    WIN = "VisionEngine - 14 Core Exercises"

    engine = VisionEngine(sensitivity="BALANCED")
    engine.start()
    playable = PLAYABLE_EXERCISES
    modes = ["BALANCED", "CONVENIENT", "STRICT"]
    mode_idx = 0
    idx = playable.index("STR_7_PUSHUPS")
    engine.set_exercise(playable[idx])

    # Resizable window set to 1920x1080
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, DISPLAY_W, DISPLAY_H)

    while engine.running:
        if engine.latest_frame is not None:
            preview = cv2.cvtColor(engine.latest_frame, cv2.COLOR_RGB2BGR)
            preview = cv2.resize(preview, (DISPLAY_W, DISPLAY_H))

            cv2.rectangle(preview, (0, 0), (DISPLAY_W, 200), (20, 20, 20), -1)
            cv2.putText(preview, f"({idx+1}/{len(playable)}) {engine.current_exercise} | Reps: {engine.reps}",
                        (30, 55), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
            cv2.putText(preview, engine.feedback, (30, 105),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 0), 2)
            cv2.putText(preview, f"Stage:[{engine.stage}] Mode:[{engine.sensitivity}](M) | N/P=Switch | Space=Cheat",
                        (30, 145), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)

            # Progress bar
            cv2.rectangle(preview, (30, 160), (DISPLAY_W - 30, 190), (60, 60, 60), -1)
            bar_w = int((DISPLAY_W - 60) * np.clip(engine.progress, 0.0, 1.0))
            bar_color = (0, 255, 120) if engine.in_frame else (0, 80, 255)
            cv2.rectangle(preview, (30, 160), (30 + bar_w, 190), bar_color, -1)

            cv2.imshow(WIN, preview)

        key = cv2.waitKey(15) & 0xFF
        if key == ord('q'):
            engine.stop()
            break
        elif key == ord('n'):
            idx = (idx + 1) % len(playable)
            engine.set_exercise(playable[idx])
        elif key == ord('p'):
            idx = (idx - 1) % len(playable)
            engine.set_exercise(playable[idx])
        elif key == ord('m'):
            mode_idx = (mode_idx + 1) % len(modes)
            engine.set_sensitivity(modes[mode_idx])
        elif key == ord('c'):
            engine.recalibrate()
        elif key == ord(' '):
            engine.add_cheat_rep()

    cv2.destroyAllWindows()