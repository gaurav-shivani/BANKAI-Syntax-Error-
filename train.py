import pygame
import sys
import math
import time
import os
from vision_engine import VisionEngine
from sound_manager import play_sound, play_music, fadeout_music
from menu import (safe_font, load_bg_image, draw_wood_button, draw_floating_card,
                  ACCENT_GOLD, TEXT_WHITE, TEXT_MUTED, WOOD_DARK, WOOD_MID, WOOD_LIGHT,
                  WOOD_BORDER, WOOD_HIGHLIGHT, BG_COLOR, DANGER_RED)

# --- ASSET PATHS ---
ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
BG_DIR = os.path.join(ASSET_DIR, "backgrounds")

# ============================================================
# UI COLOR PALETTE (Japanese pixel-art theme, consistent with menu.py)
# ============================================================
CARD_BG = (42, 28, 18)
CARD_BORDER = (90, 62, 35)
ACCENT_CYAN = (100, 180, 200)       # Muted cyan (more earthy)
ACCENT_GREEN = (80, 170, 60)        # Forest green
ACCENT_RED = (178, 34, 34)          # Deep samurai red
ACCENT_ORANGE = (200, 120, 30)      # Amber/warm orange
LOCKED_BG = (28, 18, 10)
LOCKED_BORDER = (50, 35, 20)

# ============================================================
# TRAINING LEVEL DEFINITIONS
# Each level contains a list of exercises to complete and
# the combat abilities that are unlocked upon completion.
# ============================================================
TRAINING_LEVELS = [
    {
        "name": "Rookie Warmup",
        "exercises": [
            {"id": "ARM_RAISES", "label": "Arm Raises",  "target": 5},
            {"id": "PUNCH",      "label": "Punches",      "target": 10},
            {"id": "JUMP_ROPE",  "label": "Jump Rope",    "target": 10},
        ],
        "unlocks": ["punch", "jump"],
        "unlock_label": "PUNCH + JUMP",
    },
    {
        "name": "Combat Basics",
        "exercises": [
            {"id": "SQUATS",     "label": "Squats",       "target": 10},
            {"id": "FRONT_KICK", "label": "Front Kicks",  "target": 8},
            {"id": "BLOCK",      "label": "Blocks",       "target": 8},
        ],
        "unlocks": ["kick", "block"],
        "unlock_label": "KICK + BLOCK",
    },
    {
        "name": "Warrior\nConditioning",
        "exercises": [
            {"id": "BICEP_CURL",     "label": "Bicep Curls",    "target": 10},
            {"id": "SHOULDER_PRESS", "label": "Shoulder\nPress",  "target": 8},
            {"id": "JAB_CROSS",      "label": "Jab Cross",       "target": 10},
        ],
        "unlocks": ["crouch", "run"],
        "unlock_label": "CROUCH + RUN",
    },
    {
        "name": "Elite Training",
        "exercises": [
            {"id": "PUSHUP",       "label": "Push-ups",      "target": 8},
            {"id": "JUMPING_JACK", "label": "Jumping\nJacks", "target": 10},
            {"id": "GUARD",        "label": "Guard Hold",    "target": 10, "unit": "sec"},
        ],
        "unlocks": ["atk_boost"],
        "unlock_label": "+50% ATTACK\n     POWER",
        "stat_bonus": {"attack_power_mult": 1.5},
    },
    {
        "name": "Master Tier",
        "exercises": [
            {"id": "MARCHING", "label": "Marching",   "target": 15},
            {"id": "PLANK",    "label": "Plank Hold",  "target": 15, "unit": "sec"},
            {"id": "SQUATS",   "label": "Squats",      "target": 12},
        ],
        "unlocks": ["hp_boost"],
        "unlock_label": "+100 MAX HP",
        "stat_bonus": {"max_hp_add": 100},
    },
]

# All ability keys and their display names
ALL_ABILITIES = [
    ("punch", "PUNCH"), ("jump", "JUMP"), ("kick", "KICK"),
    ("block", "BLOCK"), ("crouch", "CROUCH"), ("run", "RUN"),
    ("atk_boost", "ATK+"), ("hp_boost", "HP+"),
]


def _ex_target_str(ex):
    """Format an exercise target for display, e.g. '×10' or '15s'."""
    if ex.get("unit") == "sec":
        return f"{ex['target']}s"
    return f"\u00d7{ex['target']}"


# ============================================================
# TRAINING HUB — Level selection screen (Japanese Dojo theme)
# ============================================================
class TrainingHub:
    def __init__(self, width, height, player_stats):
        self.width = width
        self.height = height
        self.stats = player_stats
        play_sound("Training.wav", 0.7)

        self.font_title = safe_font("Rogue.ttf", 40, bold=True)
        self.font_level = safe_font("rubik.ttf", 20, bold=True)
        self.font_name = safe_font("rubik.ttf", 15, bold=True)
        self.font_body = safe_font("rubik.ttf", 13)
        self.font_badge = safe_font("rubik.ttf", 13, bold=True)
        self.font_btn = safe_font("rubik.ttf", 13, bold=True)
        self.font_status = safe_font("rubik.ttf", 14, bold=True)

        # Background
        self.bg_img = load_bg_image(["training_bg.png"], width, height)

        self.back_btn = pygame.Rect(40, 20, 120, 38)

        # Build 5 level cards
        card_w, card_h = 215, 365
        gap = 16
        total_w = 5 * card_w + 4 * gap
        start_x = (width - total_w) // 2
        start_y = 95

        self.cards = []
        for i in range(5):
            self.cards.append(pygame.Rect(
                start_x + i * (card_w + gap), start_y, card_w, card_h))

    # ---- helpers ----
    def _level_status(self, idx):
        completed = self.stats.get("training_level", 0)
        if idx < completed:
            return "COMPLETED"
        elif idx == completed:
            return "AVAILABLE"
        return "LOCKED"

    # ---- update ----
    def update(self, events):
        mouse_pos = pygame.mouse.get_pos()
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.back_btn.collidepoint(mouse_pos):
                    return "BACK"
                for i, rect in enumerate(self.cards):
                    if self._level_status(i) != "LOCKED" and rect.collidepoint(mouse_pos):
                        return i
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return "BACK"
        return None

    # ---- draw ----
    def draw(self, surface):
        # Background
        if self.bg_img:
            surface.blit(self.bg_img, (0, 0))
            # Semi-transparent overlay for readability
            overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            overlay.fill((15, 10, 5, 140))
            surface.blit(overlay, (0, 0))
        else:
            surface.fill(BG_COLOR)

        mouse_pos = pygame.mouse.get_pos()

        # Title banner (wood plank)
        title_w, title_h = 420, 55
        title_rect = pygame.Rect((self.width - title_w) // 2, 12, title_w, title_h)
        pygame.draw.rect(surface, WOOD_DARK, title_rect, border_radius=8)
        pygame.draw.rect(surface, WOOD_BORDER, title_rect, 3, border_radius=8)
        pygame.draw.line(surface, (120, 82, 40),
                         (title_rect.left + 10, title_rect.top + 4),
                         (title_rect.right - 10, title_rect.top + 4), 2)

        title = self.font_title.render("TRAINING DOJO", True, ACCENT_GOLD)
        surface.blit(title, title.get_rect(center=title_rect.center))

        sub = self.font_body.render(
            "Complete exercises to unlock combat abilities", True, TEXT_MUTED)
        surface.blit(sub, sub.get_rect(center=(self.width // 2, 78)))

        # Back button (wood style)
        hov_back = self.back_btn.collidepoint(mouse_pos)
        draw_wood_button(surface, self.back_btn, "< MENU",
                         self.font_btn, hov_back)

        # Level cards
        for i, rect in enumerate(self.cards):
            level = TRAINING_LEVELS[i]
            status = self._level_status(i)
            hov = rect.collidepoint(mouse_pos) and status != "LOCKED"

            if status == "LOCKED":
                bg_top, bg_bot = (28, 18, 10), (20, 12, 6)
                border = LOCKED_BORDER
            elif status == "COMPLETED":
                bg_top = (35, 62, 30) if hov else (30, 52, 25)
                bg_bot = (22, 42, 18) if hov else (20, 38, 15)
                border = ACCENT_GREEN if hov else (60, 130, 50)
            else:
                bg_top = WOOD_MID if hov else (75, 50, 25)
                bg_bot = WOOD_DARK if hov else (50, 32, 16)
                border = ACCENT_GOLD if hov else CARD_BORDER

            # Card background (gradient wood)
            top_r = pygame.Rect(rect.x, rect.y, rect.width, rect.height // 2)
            bot_r = pygame.Rect(rect.x, rect.y + rect.height // 2, rect.width, rect.height // 2)
            pygame.draw.rect(surface, bg_top, top_r, border_radius=8)
            pygame.draw.rect(surface, bg_bot, bot_r, border_radius=8)
            pygame.draw.rect(surface, border, rect, 3, border_radius=8)

            # Inner highlight
            if status != "LOCKED":
                hl = pygame.Surface((rect.width - 12, 2), pygame.SRCALPHA)
                hl.fill((255, 220, 160, 40))
                surface.blit(hl, (rect.x + 6, rect.y + 4))

            x, y, w = rect.x, rect.y, rect.width

            # Level number
            txt_c = TEXT_MUTED if status == "LOCKED" else ACCENT_GOLD
            lv = self.font_level.render(f"LEVEL {i + 1}", True, txt_c)
            surface.blit(lv, lv.get_rect(center=(x + w // 2, y + 22)))

            # Divider
            div_c = border if status != "LOCKED" else LOCKED_BORDER
            pygame.draw.line(surface, div_c, (x + 12, y + 40), (x + w - 12, y + 40), 2)

            # Name
            nm = self.font_name.render(level["name"], True,
                                       TEXT_MUTED if status == "LOCKED" else TEXT_WHITE)
            surface.blit(nm, nm.get_rect(center=(x + w // 2, y + 57)))

            # Exercise list
            ey = y + 80
            for ex in level["exercises"]:
                clr = TEXT_MUTED if status == "LOCKED" else TEXT_WHITE
                pfx = "\u2713" if status == "COMPLETED" else "\u2022"
                if status == "COMPLETED":
                    clr = ACCENT_GREEN
                label = f"{pfx} {ex['label']} {_ex_target_str(ex)}"
                surface.blit(self.font_body.render(label, True, clr), (x + 14, ey))
                ey += 20

            # Divider
            pygame.draw.line(surface, div_c, (x + 12, ey + 6), (x + w - 12, ey + 6), 2)

            # Unlock rewards
            surface.blit(self.font_body.render("UNLOCKS:", True, TEXT_MUTED),
                         (x + 14, ey + 16))
            ulk_c = TEXT_MUTED if status == "LOCKED" else ACCENT_GOLD
            ulk = self.font_badge.render(level["unlock_label"], True, ulk_c)
            surface.blit(ulk, ulk.get_rect(center=(x + w // 2, ey + 48)))

            # Status badge at bottom (wood button style)
            badge = pygame.Rect(x + 18, rect.bottom - 46, w - 36, 32)
            if status == "COMPLETED":
                pygame.draw.rect(surface, (45, 100, 35), badge, border_radius=6)
                pygame.draw.rect(surface, ACCENT_GREEN, badge, 2, border_radius=6)
                bt = self.font_btn.render("COMPLETED \u2713", True, ACCENT_GREEN)
            elif status == "AVAILABLE":
                bg_c = WOOD_LIGHT if hov else WOOD_MID
                pygame.draw.rect(surface, bg_c, badge, border_radius=6)
                pygame.draw.rect(surface, ACCENT_GOLD, badge, 2, border_radius=6)
                bt = self.font_btn.render("START TRAINING", True, (30, 20, 10))
            else:
                pygame.draw.rect(surface, LOCKED_BG, badge, border_radius=6)
                pygame.draw.rect(surface, LOCKED_BORDER, badge, 1, border_radius=6)
                bt = self.font_btn.render("\U0001f512 LOCKED", True, TEXT_MUTED)
            surface.blit(bt, bt.get_rect(center=badge.center))

        # ---- Bottom status bar: unlocked abilities (wood panel) ----
        bar_y = self.height - 62
        bar_panel = pygame.Surface((self.width, 62), pygame.SRCALPHA)
        bar_panel.fill((25, 16, 10, 180))
        surface.blit(bar_panel, (0, bar_y - 8))
        pygame.draw.line(surface, CARD_BORDER, (40, bar_y - 8), (self.width - 40, bar_y - 8), 2)

        abilities = self.stats.get("unlocked_abilities", [])
        surface.blit(self.font_status.render("ABILITIES:", True, TEXT_MUTED), (40, bar_y + 2))

        bx = 150
        for key, display in ALL_ABILITIES:
            unlocked = key in abilities
            pill = pygame.Rect(bx, bar_y, 60, 24)
            if unlocked:
                pygame.draw.rect(surface, (35, 60, 28), pill, border_radius=5)
                pygame.draw.rect(surface, ACCENT_GREEN, pill, 1, border_radius=5)
                clr = ACCENT_GREEN
            else:
                pygame.draw.rect(surface, LOCKED_BG, pill, border_radius=5)
                pygame.draw.rect(surface, LOCKED_BORDER, pill, 1, border_radius=5)
                clr = TEXT_MUTED
            t = self.font_body.render(display, True, clr)
            surface.blit(t, t.get_rect(center=pill.center))
            bx += 68

        # Stats
        atk = self.stats.get("attack_power", 10)
        hp = self.stats.get("max_hp", 150)
        st = self.font_status.render(f"ATK: {atk}   HP: {hp}", True, ACCENT_GOLD)
        surface.blit(st, (self.width - st.get_width() - 40, bar_y + 2))

        # Hint
        hint = self.font_body.render(
            "Click a level to begin  |  ESC = Back to Menu", True, TEXT_MUTED)
        surface.blit(hint, hint.get_rect(center=(self.width // 2, self.height - 14)))


# ============================================================
# DRILL SCREEN — Active exercise with live camera feed
# ============================================================
class DrillScreen:
    def __init__(self, width, height, level_data, level_idx, player_stats):
        self.width = width
        self.height = height
        self.level_data = level_data
        self.level_idx = level_idx
        self.stats = player_stats

        self.font_title = safe_font("rubik.ttf", 22, bold=True)
        self.font_exercise = safe_font("Rogue.ttf", 30, bold=True)
        self.font_reps = safe_font("Rogue.ttf", 52, bold=True)
        self.font_body = safe_font("rubik.ttf", 15)
        self.font_bold = safe_font("rubik.ttf", 15, bold=True)
        self.font_queue = safe_font("rubik.ttf", 14)
        self.font_big = safe_font("Rogue.ttf", 44, bold=True)
        self.font_sub = safe_font("rubik.ttf", 20)

        # Exercise state
        self.exercises = level_data["exercises"]
        self.current_ex_idx = 0
        self.exercise_complete = [False] * len(self.exercises)
        self.exercise_final_reps = [0] * len(self.exercises)
        self.last_sound_rep = 0

        # Transition animation
        self.transition_timer = 0.0
        self.transition_msg = ""
        self.transition_sub = ""
        self.all_complete = False

        # Vision engine
        self.engine = VisionEngine()
        self.engine.set_exercise(self.exercises[0]["id"])
        self.engine.start()

    def update(self, events):
        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return "QUIT"
                elif event.key == pygame.K_SPACE:
                    self.engine.add_cheat_rep()

        # Check for rep increase sound
        if self.engine.reps > self.last_sound_rep:
            play_sound("rep_ding.wav", 0.6)
            self.last_sound_rep = self.engine.reps

        # --- Check if current exercise hit its target ---
        if not self.all_complete and self.transition_timer <= 0:
            cur = self.exercises[self.current_ex_idx]
            if self.engine.reps >= cur["target"]:
                self.exercise_complete[self.current_ex_idx] = True
                self.exercise_final_reps[self.current_ex_idx] = self.engine.reps

                if self.current_ex_idx < len(self.exercises) - 1:
                    play_sound("Great.wav", 0.8)
                    nxt = self.exercises[self.current_ex_idx + 1]
                    self.transition_timer = 2.0
                    self.transition_msg = f"{cur['label']} COMPLETE!"
                    self.transition_sub = f"Next up: {nxt['label']} {_ex_target_str(nxt)}"
                else:
                    play_sound("Complete.wav", 0.85)
                    self.all_complete = True
                    self.transition_timer = 2.5
                    self.transition_msg = "ALL EXERCISES COMPLETE!"
                    self.transition_sub = "Level finished — unlocking abilities..."

        # --- Advance after transition ---
        if self.transition_timer > 0:
            self.transition_timer -= 1.0 / 60.0
            if self.transition_timer <= 0:
                if self.all_complete:
                    return "COMPLETE"
                self.current_ex_idx += 1
                self.last_sound_rep = 0
                self.engine.set_exercise(self.exercises[self.current_ex_idx]["id"])

        return None

    def draw(self, surface):
        surface.fill(BG_COLOR)

        # ---- Title bar (wood panel) ----
        title_bar = pygame.Surface((self.width, 48), pygame.SRCALPHA)
        title_bar.fill((42, 28, 18, 200))
        surface.blit(title_bar, (0, 0))
        pygame.draw.line(surface, CARD_BORDER, (0, 48), (self.width, 48), 2)

        title = self.font_title.render(
            f"LEVEL {self.level_idx + 1}: {self.level_data['name'].upper()}", True, ACCENT_GOLD)
        surface.blit(title, (30, 13))
        esc = self.font_body.render("ESC = Quit Training", True, TEXT_MUTED)
        surface.blit(esc, (self.width - esc.get_width() - 30, 16))

        # ---- Camera card (left) — wood-framed ----
        cam_card = pygame.Rect(25, 55, 770, 510)
        pygame.draw.rect(surface, CARD_BG, cam_card, border_radius=8)
        pygame.draw.rect(surface, CARD_BORDER, cam_card, 3, border_radius=8)

        vp = pygame.Rect(35, 65, 750, 440)
        if self.engine.latest_frame is not None:
            frame = self.engine.latest_frame
            h, w, _ = frame.shape
            cam_surf = pygame.image.frombuffer(frame.tobytes(), (w, h), "RGB")
            cam_surf = pygame.transform.scale(cam_surf, (vp.width, vp.height))
            surface.blit(cam_surf, vp.topleft)
        else:
            pygame.draw.rect(surface, (18, 12, 8), vp, border_radius=6)
            ld = self.font_body.render(
                "Initializing camera feed & AI model...", True, TEXT_MUTED)
            surface.blit(ld, ld.get_rect(center=vp.center))
        pygame.draw.rect(surface, CARD_BORDER, vp, 2, border_radius=6)

        # Feedback row under camera
        sg_c = ACCENT_GREEN if self.engine.stage == "UP" else ACCENT_GOLD
        surface.blit(self.font_bold.render(f"[{self.engine.stage}]", True, sg_c), (35, 518))
        surface.blit(self.font_body.render(self.engine.feedback, True, TEXT_WHITE), (115, 520))

        # Cheat hint
        surface.blit(self.font_body.render(
            "Space = Cheat Rep  |  ESC = Quit", True, TEXT_MUTED), (35, 545))

        # ---- Right panel (wood card) ----
        panel = pygame.Rect(810, 55, 445, 610)
        pygame.draw.rect(surface, CARD_BG, panel, border_radius=8)
        pygame.draw.rect(surface, CARD_BORDER, panel, 3, border_radius=8)
        # Inner highlight
        pygame.draw.line(surface, (80, 55, 30),
                         (panel.left + 10, panel.top + 4),
                         (panel.right - 10, panel.top + 4), 2)

        px, py = 830, 70

        # Current exercise header
        surface.blit(self.font_body.render(
            f"Exercise {self.current_ex_idx + 1} of {len(self.exercises)}", True, TEXT_MUTED),
            (px, py))

        cur = self.exercises[self.current_ex_idx]
        surface.blit(self.font_exercise.render(
            cur["label"].upper(), True, ACCENT_GOLD), (px, py + 25))

        # Rep counter
        reps = min(self.engine.reps, cur["target"])
        target = cur["target"]
        is_sec = cur.get("unit") == "sec"
        unit = "s" if is_sec else ""
        reps_str = f"{reps}{unit} / {target}{unit}"
        reps_color = ACCENT_GREEN if reps >= target else TEXT_WHITE
        rt = self.font_reps.render(reps_str, True, reps_color)
        surface.blit(rt, rt.get_rect(center=(px + 210, py + 115)))

        # Progress bar (wood-themed)
        bar_x, bar_y, bar_w, bar_h = px, py + 160, 400, 18
        pygame.draw.rect(surface, (30, 20, 12),
                         (bar_x, bar_y, bar_w, bar_h), border_radius=6)
        pygame.draw.rect(surface, CARD_BORDER,
                         (bar_x - 2, bar_y - 2, bar_w + 4, bar_h + 4), 2, border_radius=6)
        fill = int(bar_w * min(1.0, reps / max(target, 1)))
        if fill > 0:
            bar_c = ACCENT_GREEN if reps >= target else ACCENT_GOLD
            pygame.draw.rect(surface, bar_c,
                             (bar_x, bar_y, fill, bar_h), border_radius=6)

        # Divider
        dy = py + 200
        pygame.draw.line(surface, CARD_BORDER, (px, dy), (px + 400, dy), 2)

        # Exercise queue
        surface.blit(self.font_bold.render("EXERCISE QUEUE", True, ACCENT_GOLD),
                     (px, dy + 14))
        qy = dy + 40
        for i, ex in enumerate(self.exercises):
            if self.exercise_complete[i]:
                pfx, clr = "\u2713", ACCENT_GREEN
                info = f"({self.exercise_final_reps[i]}/{ex['target']})"
            elif i == self.current_ex_idx:
                pfx, clr = "\u25b6", ACCENT_GOLD
                r = self.engine.reps
                info = f"({r}/{ex['target']})"
            else:
                pfx, clr = "\u25cb", TEXT_MUTED
                info = f"(0/{ex['target']})"
            line = f" {pfx}  {ex['label']}  {_ex_target_str(ex)}  {info}"
            surface.blit(self.font_queue.render(line, True, clr), (px, qy))
            qy += 26

        # Divider
        pygame.draw.line(surface, CARD_BORDER, (px, qy + 10), (px + 400, qy + 10), 2)

        # Unlock preview
        surface.blit(self.font_body.render(
            "COMPLETING THIS LEVEL UNLOCKS:", True, TEXT_MUTED), (px, qy + 24))
        surface.blit(self.font_bold.render(
            self.level_data["unlock_label"], True, ACCENT_GOLD), (px, qy + 46))

        # ---- Transition overlay ----
        if self.transition_timer > 0:
            overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            overlay.fill((10, 8, 5, 180))
            surface.blit(overlay, (0, 0))

            mc = ACCENT_GREEN if self.all_complete else ACCENT_GOLD
            mt = self.font_big.render(self.transition_msg, True, mc)
            surface.blit(mt, mt.get_rect(center=(self.width // 2, self.height // 2 - 20)))

            if self.transition_sub:
                st = self.font_sub.render(self.transition_sub, True, TEXT_WHITE)
                surface.blit(st, st.get_rect(
                    center=(self.width // 2, self.height // 2 + 30)))


# ============================================================
# LEVEL COMPLETE SCREEN — Celebration + ability unlock
# ============================================================
class LevelCompleteScreen:
    def __init__(self, width, height, level_data, level_idx, player_stats):
        self.width = width
        self.height = height
        self.level_data = level_data
        self.level_idx = level_idx
        self.stats = player_stats
        self.start_time = time.time()

        self.font_title = safe_font("Rogue.ttf", 50, bold=True)
        self.font_subtitle = safe_font("rubik.ttf", 22, bold=True)
        self.font_body = safe_font("rubik.ttf", 17)
        self.font_btn = safe_font("rubik.ttf", 20, bold=True)
        self.font_unlock = safe_font("Rogue.ttf", 36, bold=True)

        self.continue_btn = pygame.Rect(
            (width - 280) // 2, height - 110, 280, 52)

        # Background
        self.bg_img = load_bg_image(["training_bg.png"], width, height)

        play_sound("unlock.wav", 0.8)
        self._apply_rewards()

    def _apply_rewards(self):
        prev = self.stats.get("training_level", 0)
        new_level = self.level_idx + 1
        first_time = new_level > prev

        # Always update training level and abilities
        self.stats["training_level"] = max(prev, new_level)

        abilities = self.stats.get("unlocked_abilities", [])
        for ab in self.level_data["unlocks"]:
            if ab not in abilities:
                abilities.append(ab)
        self.stats["unlocked_abilities"] = abilities

        # Stat bonuses only on first completion (prevent stacking)
        if first_time:
            bonus = self.level_data.get("stat_bonus", {})
            if "attack_power_mult" in bonus:
                self.stats["attack_power"] = int(
                    self.stats["attack_power"] * bonus["attack_power_mult"])
            if "max_hp_add" in bonus:
                self.stats["max_hp"] += bonus["max_hp_add"]

            # XP reward scales with level
            xp_reward = new_level * 50
            self.stats["xp"] = self.stats.get("xp", 0) + xp_reward
            xp_needed = self.stats.get("level", 1) * 100
            while self.stats["xp"] >= xp_needed:
                self.stats["level"] = self.stats.get("level", 1) + 1
                self.stats["xp"] -= xp_needed
                xp_needed = self.stats["level"] * 100

    def update(self, events):
        mouse_pos = pygame.mouse.get_pos()
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.continue_btn.collidepoint(mouse_pos):
                    return "CONTINUE"
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return "CONTINUE"
        return None

    def draw(self, surface):
        # Background
        if self.bg_img:
            surface.blit(self.bg_img, (0, 0))
            overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            overlay.fill((15, 10, 5, 160))
            surface.blit(overlay, (0, 0))
        else:
            surface.fill(BG_COLOR)

        mouse_pos = pygame.mouse.get_pos()

        # Pulsing glow
        elapsed = time.time() - self.start_time
        pulse = int(abs(math.sin(elapsed * 2.5)) * 40)

        # Title
        t = self.font_title.render("LEVEL COMPLETE!", True, ACCENT_GOLD)
        surface.blit(t, t.get_rect(center=(self.width // 2, 80)))

        nm = self.font_subtitle.render(
            f"Level {self.level_idx + 1}: {self.level_data['name']}", True, TEXT_WHITE)
        surface.blit(nm, nm.get_rect(center=(self.width // 2, 130)))

        # Unlock box (wood panel style)
        bw, bh = 520, 150
        box = pygame.Rect((self.width - bw) // 2, 180, bw, bh)
        glow_border = (min(255, 140 + pulse), min(255, 95 + pulse // 2), min(255, 30 + pulse // 3))
        pygame.draw.rect(surface, CARD_BG, box, border_radius=10)
        pygame.draw.rect(surface, glow_border, box, 3, border_radius=10)
        # Inner highlight
        pygame.draw.line(surface, (100, 70, 35),
                         (box.left + 10, box.top + 4), (box.right - 10, box.top + 4), 2)

        hdr = self.font_body.render("NEW ABILITY UNLOCKED!", True, ACCENT_GOLD)
        surface.blit(hdr, hdr.get_rect(center=(self.width // 2, 220)))

        ulk = self.font_unlock.render(self.level_data["unlock_label"], True, ACCENT_GOLD)
        surface.blit(ulk, ulk.get_rect(center=(self.width // 2, 275)))

        # Exercises summary
        sy = 370
        surface.blit(self.font_subtitle.render(
            "Exercises Completed:", True, TEXT_WHITE),
            self.font_subtitle.render("Exercises Completed:", True, TEXT_WHITE).get_rect(
                center=(self.width // 2, sy)))

        ey = sy + 35
        for ex in self.level_data["exercises"]:
            line = f"\u2713  {ex['label']}  {_ex_target_str(ex)}"
            et = self.font_body.render(line, True, ACCENT_GREEN)
            surface.blit(et, et.get_rect(center=(self.width // 2, ey)))
            ey += 28

        # Stats after rewards
        ey += 15
        atk = self.stats.get("attack_power", 10)
        hp = self.stats.get("max_hp", 150)
        stat_txt = self.font_body.render(
            f"ATK: {atk}   |   HP: {hp}   |   XP: {self.stats.get('xp', 0)}", True, TEXT_MUTED)
        surface.blit(stat_txt, stat_txt.get_rect(center=(self.width // 2, ey)))

        # Continue button (wood style)
        hov = self.continue_btn.collidepoint(mouse_pos)
        draw_wood_button(surface, self.continue_btn, "CONTINUE",
                         self.font_btn, hov, accent_color=ACCENT_GOLD)

        hint = self.font_body.render(
            "Press ENTER or click to continue", True, TEXT_MUTED)
        surface.blit(hint, hint.get_rect(center=(self.width // 2, self.height - 40)))


# ============================================================
# MAIN ENTRY POINT — State machine managing the three screens
# ============================================================
def run_training(screen, clock, player_stats):
    play_music("SDM_FightingBack.mp3", volume=0.4, loop=-1)
    state = "HUB"
    hub = TrainingHub(screen.get_width(), screen.get_height(), player_stats)
    drill = None
    complete = None

    while True:
        clock.tick(60)
        events = pygame.event.get()

        for event in events:
            if event.type == pygame.QUIT:
                if drill is not None:
                    drill.engine.stop()
                pygame.quit()
                sys.exit()

        # ---- HUB: Level selection ----
        if state == "HUB":
            result = hub.update(events)
            if result == "BACK":
                return
            elif isinstance(result, int):
                level_idx = result
                drill = DrillScreen(
                    screen.get_width(), screen.get_height(),
                    TRAINING_LEVELS[level_idx], level_idx, player_stats)
                state = "DRILL"
                continue
            hub.draw(screen)

        # ---- DRILL: Active exercise ----
        elif state == "DRILL":
            result = drill.update(events)
            if result == "QUIT":
                drill.engine.stop()
                drill = None
                hub = TrainingHub(screen.get_width(), screen.get_height(), player_stats)
                state = "HUB"
                continue
            elif result == "COMPLETE":
                level_data = drill.level_data
                level_idx = drill.level_idx
                drill.engine.stop()
                drill = None
                complete = LevelCompleteScreen(
                    screen.get_width(), screen.get_height(),
                    level_data, level_idx, player_stats)
                state = "COMPLETE"
                continue
            drill.draw(screen)

        # ---- COMPLETE: Celebration ----
        elif state == "COMPLETE":
            result = complete.update(events)
            if result == "CONTINUE":
                complete = None
                hub = TrainingHub(screen.get_width(), screen.get_height(), player_stats)
                state = "HUB"
                continue
            complete.draw(screen)

        pygame.display.flip()
