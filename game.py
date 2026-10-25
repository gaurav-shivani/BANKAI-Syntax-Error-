import pygame
import random
import os
import sys
import json
import socket
from menu import PauseMenu, safe_font, load_bg_image, ACCENT_GOLD, TEXT_WHITE, WOOD_DARK, WOOD_BORDER, WOOD_MID, TEXT_MUTED

# --- SAFE AUDIO IMPORTS ---
try:
    from sound_manager import play_sound, play_music, fadeout_music, stop_music
except ImportError:
    try:
        from menu import play_sound, play_music
    except ImportError:
        def play_sound(file, vol=1.0): pass
        def play_music(file, volume=1.0, loop=-1): pass

# --- ASSET PATH HELPERS ---
ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
BG_DIR = os.path.join(ASSET_DIR, "backgrounds")
SPRITE_DIR = os.path.join(ASSET_DIR, "sprites")
PORTRAIT_DIR = os.path.join(ASSET_DIR, "portraits")

# --- STAGE CONFIGURATIONS ---
LEVEL_CONFIGS = {
    1: {"bg": "level_1_bg.png", "floor": 610},
    2: {"bg": "level_2_bg.png", "floor": 640},
    3: {"bg": "level_3_bg.png", "floor": 635},
    4: {"bg": "level_4_bg.png", "floor": 630},
    5: {"bg": "level_5_bg.png", "floor": 580}
}


def find_asset(filename, *extra_dirs):
    """Search for an asset file in root, assets/, and extra directories."""
    candidates = [filename]
    for d in extra_dirs:
        candidates.append(os.path.join(d, filename))
    # Also try root-level fallback
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), filename))
    for path in candidates:
        if os.path.exists(path):
            return path
    return filename  # Return as-is for fallback


class Fighter:
    def __init__(self, x, y, controls, sprite_sheet_path, max_health=100, damage=10, 
                 flip=False, is_bot=False, difficulty="EASY", floor_level=610,
                 unlocked_abilities=None):
        # Narrower pushbox width (36 instead of 75) so fighters can get close enough for punches to connect visually
        self.rect = pygame.Rect((x, y, 36, 160))
        self.base_height = 160
        self.crouch_height = 100
        self.vel_x = 0
        self.vel_y = 0
        self.jump = False
        
        self.max_health = max_health
        self.health = max_health
        self.damage_power = damage
        
        self.controls = controls
        self.flip = flip
        self.is_bot = is_bot
        self.difficulty = difficulty
        self.floor_level = floor_level
        self.unlocked_abilities = unlocked_abilities  # None = all unlocked (bots)

        # Combat & Stance States
        self.is_crouching = False
        self.is_attacking = False
        self.is_blocking = False
        self.is_hit = False
        self.is_dead = False
        self.hit_cooldown = 0
        self.attack_type = None
        self.attack_cooldown = 0
        self.attack_rect = None
        self.hit_registered = False
        self.pending_damage_event = None
        self.prev_keys = None
        self.took_damage_this_frame = False

        # Impact timing & attacker recoil variables (INCLUDES YOUR BUGFIX)
        self.current_attack_target = None
        self.active_hit_frame = 0
        self.attacker_recoil_x = 0
        self.attack_data = None
        
        self.action = "idle"
        self.frame_index = 0
        self.update_time = pygame.time.get_ticks()

        # Spritesheet & Animation Setup
        self.char_w, self.char_h = 160, 240
        self.animations = {
            "idle": [], "run": [], "jump": [], "crouch": [], 
            "punch": [], "kick": [], "hit": [], "dead": [], "block": []
        }
        
        sheet_config = (16, 3, 128, 128)
        animation_ranges = {
            "idle": (20, 25),
            "run": (38, 45),
            "jump": (26, 35),
            "crouch": (17, 19),
            "block": (36, 37),
            "punch": (0, 2),
            "kick": (7, 13),
            "hit": (17, 19),
            "dead": (14, 16)
        }
        self.load_all_animations(sprite_sheet_path, sheet_config, animation_ranges)
        self.set_action("idle")
        self.image = self.animations[self.action][self.frame_index]

    def load_all_animations(self, sheet_path, sheet_config, ranges):
        master_frames = []
        # Try finding sprite sheet in multiple locations
        actual_path = find_asset(sheet_path, SPRITE_DIR)
        if os.path.exists(actual_path):
            try:
                cols, rows, fw, fh = sheet_config
                master_sheet = pygame.image.load(actual_path).convert_alpha()
                for r in range(rows):
                    for c in range(cols):
                        cell_rect = pygame.Rect(c * fw, r * fh, fw, fh)
                        frame_surf = pygame.Surface((fw, fh), pygame.SRCALPHA)
                        frame_surf.blit(master_sheet, (0, 0), cell_rect)
                        master_frames.append(pygame.transform.scale(frame_surf, (self.char_w, self.char_h)))
            except Exception:
                master_frames = []

        for action, f_range in ranges.items():
            start_f, end_f = f_range
            sliced = master_frames[start_f : end_f + 1] if len(master_frames) > end_f else []
            if not sliced:
                for _ in range(3):
                    surf = pygame.Surface((self.char_w, self.char_h), pygame.SRCALPHA)
                    color = (0, 100, 255) if not self.is_bot else (255, 50, 50)
                    pygame.draw.rect(surf, color, (40, 40, 80, 160))
                    sliced.append(surf)
            self.animations[action] = sliced

    def set_action(self, new_action):
        if self.action != new_action:
            self.action = new_action
            self.frame_index = 0
            self.update_time = pygame.time.get_ticks()

    def move(self, target, arena_width=1800):
        dx = 0
        running_this_frame = False
        distance = abs(self.rect.centerx - target.rect.centerx)

        if not self.is_attacking and not self.is_dead and not self.is_hit:
            self.flip = self.rect.centerx >= target.rect.centerx

        if self.is_dead or self.is_hit:
            self.vel_x *= 0.8
            dx += int(self.vel_x)
            self.vel_y += 1.5
            dy = self.vel_y
            if self.rect.bottom + dy > self.floor_level:
                dy = self.floor_level - self.rect.bottom
                self.vel_y = 0
            
            if self.rect.left + dx < 0:
                dx = -self.rect.left
            elif self.rect.right + dx > arena_width:
                dx = arena_width - self.rect.right

            self.rect.x += dx
            self.rect.y += dy

            if self.hit_cooldown > 0:
                self.hit_cooldown -= 1
                if self.hit_cooldown == 0 and not self.is_dead:
                    self.is_hit = False
                    self.set_action("idle")
            return

        self.is_blocking = False
        self.is_crouching = False

        if not self.is_attacking:
            if self.is_bot:
                dx = self.process_bot_ai(target, distance)
                if abs(dx) > 0:
                    running_this_frame = True
            elif self.controls is not None:
                keys = pygame.key.get_pressed()

                if keys[self.controls['block']] and (self.unlocked_abilities is None or "block" in self.unlocked_abilities):
                    self.is_blocking = True
                elif keys[self.controls['crouch']] and not self.jump and (self.unlocked_abilities is None or "crouch" in self.unlocked_abilities):
                    self.is_crouching = True

                if self.is_blocking:
                    speed = 3
                elif self.is_crouching:
                    speed = 4
                elif self.unlocked_abilities is None or "run" in self.unlocked_abilities:
                    speed = 8
                else:
                    speed = 4  # Walk speed without run ability

                if keys[self.controls['left']]:
                    dx = -speed
                    running_this_frame = True
                if keys[self.controls['right']]:
                    dx = speed
                    running_this_frame = True

                if keys[self.controls['jump']] and not self.jump and not self.is_blocking and not self.is_crouching:
                    if self.unlocked_abilities is None or "jump" in self.unlocked_abilities:
                        self.vel_y = -30
                        self.jump = True
                        play_sound("jump.wav", 0.5)

        target_height = self.crouch_height if self.is_crouching else self.base_height
        if self.rect.height != target_height:
            ground_bottom = self.rect.bottom
            self.rect.height = target_height
            self.rect.bottom = ground_bottom

        self.vel_x *= 0.8
        dx += int(self.vel_x)

        self.vel_y += 1.5
        dy = self.vel_y

        if self.rect.bottom + dy > self.floor_level:
            dy = self.floor_level - self.rect.bottom
            self.jump = False
            self.vel_y = 0

        if self.rect.left + dx < 0:
            dx = -self.rect.left
        elif self.rect.right + dx > arena_width:
            dx = arena_width - self.rect.right

        self.rect.x += dx
        self.rect.y += dy

        if not self.is_attacking and not self.is_dead and not self.is_hit:
            if self.is_blocking:
                self.set_action("block")
            elif self.is_crouching:
                self.set_action("crouch")
            elif self.jump:
                self.set_action("jump")
            elif running_this_frame:
                self.set_action("run")
            else:
                self.set_action("idle")

        if self.attack_cooldown > 0:
            self.attack_cooldown -= 1
        else:
            if self.is_attacking:
                self.is_attacking = False
                self.set_action("idle")
                self.attack_rect = None
                self.hit_registered = False

    def process_bot_ai(self, target, distance):
        dx = 0
        if self.difficulty == "EASY":
            speed, attack_chance, block_chance, dodge_chance = 4, 3, 10, 8
        elif self.difficulty == "MEDIUM":
            speed, attack_chance, block_chance, dodge_chance = 6, 6, 25, 20
        else:
            speed, attack_chance, block_chance, dodge_chance = 8, 10, 45, 35

        retreat_dir = speed if not self.flip else -speed

        # Reaction to player's attack (Dodge, Jump, or Block)
        if target.is_attacking and distance < 85:
            roll = random.randint(1, 100)
            
            # 1. Jump-dodge backward to leap over kicks/punches
            if roll <= dodge_chance and not self.jump and self.attack_cooldown == 0:
                self.vel_y = -26
                self.jump = True
                self.vel_x = retreat_dir * 1.4
                return retreat_dir

            # 2. Block incoming hit
            elif roll <= (dodge_chance + block_chance):
                self.is_blocking = True
                return retreat_dir * 0.5

            # 3. Ground back-dash/retreat
            elif roll <= (dodge_chance + block_chance + 15):
                return retreat_dir * 1.2

        # Movement when neutral or out of range
        if distance > 38:
            dx = speed if self.rect.centerx < target.rect.centerx else -speed
        else:
            if random.randint(1, 100) <= attack_chance and self.attack_cooldown == 0:
                # Bot also utilizes jump kicks if it just dodged into the air
                if self.jump:
                    self.trigger_attack(target, "kick")
                else:
                    attack_kind = "kick" if random.random() < 0.45 else "punch"
                    self.trigger_attack(target, attack_kind)
        return dx

    def trigger_attack(self, target, attack_type):
        if not self.is_attacking and self.attack_cooldown == 0 and not self.is_blocking and not self.is_dead and not self.is_hit:
            self.is_attacking = True
            play_sound("whoosh.wav", 0.5)
            self.attack_type = attack_type
            self.set_action(attack_type)
            self.frame_index = 0
            self.hit_registered = False
            self.current_attack_target = target

            is_jump_kick = (attack_type == "kick" and self.jump)

            # Punch hits quickly on frame 1; kicks extend on frame 3
            if attack_type == "punch":
                self.attack_cooldown = 26
                self.active_hit_frame = 1
                reach = 34
                dmg_mult = 1.0
                knockback_x = 5
                knockback_y = 0
                self.attacker_recoil_x = 1.5   # Subtle punch recoil
            elif is_jump_kick:
                self.attack_cooldown = 34
                self.active_hit_frame = 3      # Hits at peak extension
                reach = 58
                dmg_mult = 2.2
                knockback_x = 24
                knockback_y = -14
                self.attacker_recoil_x = 6.0   # Airborne recoil pushing kicker back
            else:
                self.attack_cooldown = 36
                self.active_hit_frame = 3      # Hits on full leg extension
                reach = 48
                dmg_mult = 1.5
                knockback_x = 16
                knockback_y = -8
                self.attacker_recoil_x = 4.0   # Ground kick recoil pushback

            self.attack_data = {
                "reach": reach,
                "is_jump_kick": is_jump_kick,
                "dmg_mult": dmg_mult,
                "knockback_x": knockback_x,
                "knockback_y": knockback_y
            }

    def check_attack_hit(self):
        target = self.current_attack_target
        if not self.is_attacking or self.hit_registered or target is None or target.is_dead:
            return

        # INCLUDES YOUR BUGFIX: Guard against crash if attack_data is not set
        if self.attack_data is None:
            return

        data = self.attack_data
        reach = data.get("reach", 40)
        is_jump_kick = data.get("is_jump_kick", False)
        dmg_mult = data.get("dmg_mult", 1.0)
        knockback_x = data.get("knockback_x", 10)
        knockback_y = data.get("knockback_y", 0)

        hitbox_x = self.rect.right - 10 if not self.flip else self.rect.left - reach + 10
        hitbox_y = self.rect.y + 60 if is_jump_kick else self.rect.y + 45
        self.attack_rect = pygame.Rect(hitbox_x, hitbox_y, reach, 50)

        if self.attack_rect.colliderect(target.rect):
            self.hit_registered = True
            kb_dir = 1 if not self.flip else -1

            # Recoil knockback applied backwards to the attacker
            recoil_dir = -kb_dir
            self.vel_x = recoil_dir * self.attacker_recoil_x

            # Delayed impact applied to the target
            if target.is_blocking:
                final_damage = max(1, int(self.damage_power * dmg_mult * 0.20))
                target.vel_x = kb_dir * knockback_x * 0.5
                target.take_damage(final_damage, chip_only=True)
                play_sound("block.wav", 0.7)
            else:
                final_damage = int(self.damage_power * dmg_mult)
                target.vel_x = kb_dir * knockback_x
                if knockback_y < 0:
                    target.vel_y = knockback_y
                    target.jump = True
                target.take_damage(final_damage, chip_only=False)
                play_sound("hit.ogg", 0.8)
                if random.random() < 0.5:
                    play_sound("damage 1.wav", 0.6)
                else:
                    play_sound("damage 2.wav", 0.6)

            self.pending_damage_event = {
                "damage": final_damage,
                "chip_only": target.is_blocking,
                "knockback_x": target.vel_x,
                "knockback_y": knockback_y if not target.is_blocking else 0
            }

    def take_damage(self, damage, chip_only=False):
        if self.is_dead:
            return
        self.health = max(0, self.health - damage)
        if not chip_only and damage > 0:
            self.took_damage_this_frame = True

        if self.health == 0:
            self.is_dead = True
            self.is_attacking = False
            self.set_action("dead")
            # MANAS'S AUDIO FIX
            play_sound("death.wav", 0.8)
        elif not chip_only:
            self.is_hit = True
            self.set_action("hit")
            self.hit_cooldown = 15
            self.is_attacking = False

    def handle_player_inputs(self, target):
        keys = pygame.key.get_pressed()
        
        if self.is_bot or self.is_blocking or self.is_dead or self.is_hit or self.controls is None:
            self.prev_keys = keys
            return
            
        # Require the key to be released and pressed again to trigger a new attack
        if keys[self.controls['punch']] and (self.unlocked_abilities is None or "punch" in self.unlocked_abilities):
            if self.prev_keys is None or not self.prev_keys[self.controls['punch']]:
                self.trigger_attack(target, "punch")
        elif keys[self.controls['kick']] and (self.unlocked_abilities is None or "kick" in self.unlocked_abilities):
            if self.prev_keys is None or not self.prev_keys[self.controls['kick']]:
                self.trigger_attack(target, "kick")
                
        self.prev_keys = keys

    def update_animation(self):
        # Slightly slower dead animation so the fall feels dramatic during the KO delay
        anim_speed_ms = 180 if self.action == "dead" else 100
        act = self.action if self.action in self.animations else "idle"
        anim_frames = self.animations[act]

        if self.is_dead and self.frame_index >= len(anim_frames) - 1:
            self.image = anim_frames[-1]
            return

        if (self.is_blocking or self.is_crouching) and self.frame_index >= len(anim_frames) - 1:
            self.image = anim_frames[-1]
            return

        if self.frame_index >= len(anim_frames):
            self.frame_index = 0

        self.image = anim_frames[self.frame_index]

        if pygame.time.get_ticks() - self.update_time > anim_speed_ms:
            self.frame_index += 1
            self.update_time = pygame.time.get_ticks()

            # Check for strike contact at the designated animation extension frame
            if self.is_attacking and self.frame_index == self.active_hit_frame:
                self.check_attack_hit()

            if self.frame_index >= len(anim_frames):
                if self.is_attacking:
                    self.is_attacking = False
                    self.set_action("idle")
                    self.attack_rect = None
                    self.current_attack_target = None
                if not self.is_dead:
                    self.frame_index = 0
                else:
                    self.frame_index = len(anim_frames) - 1

    def draw(self, surface, camera_x, shake_y=0):
        rendered_image = pygame.transform.flip(self.image, self.flip, False)
        img_rect = rendered_image.get_rect()
        
        # Anchors the feet to the bottom of the bounding box instead of the center
        img_rect.midbottom = (self.rect.centerx - camera_x, self.rect.bottom + shake_y)
        
        surface.blit(rendered_image, img_rect)


class FightingMatch:
    def __init__(self, width, height, current_level=1, p1_max_hp=100, p1_dmg=10, 
                 bot_max_hp=100, bot_dmg=10, player_name="Player_2766", 
                 is_online=False, local_player_id=1, network_socket=None,
                 unlocked_abilities=None):
        self.width = width
        self.height = height
        self.arena_width = 1800 
        self.camera_x = 0
        self.player_name = player_name
        self.current_level = current_level
        self.is_online = is_online
        self.local_player_id = local_player_id
        self.network_socket = network_socket
        
        if self.network_socket:
            self.network_socket.setblocking(False)

        self.font_large = safe_font("Rogue.ttf", 90, bold=True)
        self.font_hud_name = safe_font("stalin.ttf", 20, bold=True)
        self.font_hint = safe_font("stalin.ttf", 13)
            
        self.intro_timer = 90  
        self.ko_timer = 110      # ~1.85 seconds at 60 FPS for KO banner & dying animation
        self.ko_triggered = False
        self.game_over = False
        self.screen_shake = 0    # Frames of screen shake remaining when user takes damage

        stage_data = LEVEL_CONFIGS.get(current_level, LEVEL_CONFIGS[1])
        self.floor_level = stage_data["floor"]
        bg_path = stage_data["bg"]

        p1_inputs = {
            'left': pygame.K_a, 'right': pygame.K_d, 'jump': pygame.K_w, 
            'crouch': pygame.K_s, 'punch': pygame.K_j, 'kick': pygame.K_i, 
            'block': pygame.K_l
        }
        bot_diff = "EASY" if current_level == 1 else ("MEDIUM" if current_level == 2 else "HARD")
        sprite_path = "fighter.png"

        spawn_y = self.floor_level - 160
        self.player1 = Fighter(300, spawn_y, p1_inputs if (not is_online or local_player_id == 1) else None, 
                               sprite_path, max_health=p1_max_hp, damage=p1_dmg, flip=False, 
                               floor_level=self.floor_level,
                               unlocked_abilities=unlocked_abilities)
        self.player2 = Fighter(1200, spawn_y, p1_inputs if (is_online and local_player_id == 2) else None, 
                               sprite_path, max_health=bot_max_hp, damage=bot_dmg, flip=True, 
                               is_bot=not is_online, difficulty=bot_diff, floor_level=self.floor_level)

        self.p1_display_health = float(p1_max_hp)
        self.p2_display_health = float(bot_max_hp)

        self.p1_img = self._load_portrait("player_portrait.png")
        self.p2_img = self._load_portrait("bot_portrait.png")
        self.p2_name = f"STAGE {self.current_level} BOT" if not is_online else "OPPONENT"

        # Load stage background
        self.bg_img = None
        bg_candidates = [bg_path, f"level_{current_level}_bg.png", "level_bg.png"]
        for candidate in bg_candidates:
            for search_dir in [BG_DIR, os.path.dirname(os.path.abspath(__file__))]:
                full_path = os.path.join(search_dir, candidate)
                if os.path.exists(full_path):
                    try:
                        img = pygame.image.load(full_path).convert_alpha()
                        self.bg_img = pygame.transform.scale(img, (self.arena_width, height))
                        break
                    except Exception:
                        continue
            if self.bg_img:
                break

    def _load_portrait(self, filename):
        """Load portrait from assets/portraits/ or root."""
        for path in [os.path.join(PORTRAIT_DIR, filename), filename]:
            if os.path.exists(path):
                try:
                    img = pygame.image.load(path).convert_alpha()
                    return pygame.transform.scale(img, (85, 85))
                except Exception:
                    pass
        return None

    def update_camera(self):
        midpoint_x = (self.player1.rect.centerx + self.player2.rect.centerx) // 2
        target_camera_x = midpoint_x - self.width // 2
        self.camera_x += (target_camera_x - self.camera_x) * 0.1
        self.camera_x = max(0, min(self.camera_x, self.arena_width - self.width))

    def resolve_pushbox_collision(self):
        if self.player1.rect.colliderect(self.player2.rect):
            overlap = (self.player1.rect.width + self.player2.rect.width) // 2 - abs(self.player1.rect.centerx - self.player2.rect.centerx)
            push = max(1, overlap // 2)
            if self.player1.rect.centerx < self.player2.rect.centerx:
                self.player1.rect.x -= push
                self.player2.rect.x += push
            else:
                self.player1.rect.x += push
                self.player2.rect.x -= push

    def sync_network(self):
        if not self.is_online or not self.network_socket:
            return

        local_fighter = self.player1 if self.local_player_id == 1 else self.player2
        remote_fighter = self.player2 if self.local_player_id == 1 else self.player1

        dmg_event = local_fighter.pending_damage_event
        local_fighter.pending_damage_event = None

        packet = {
            "id": self.local_player_id,
            "x": local_fighter.rect.x,
            "y": local_fighter.rect.y,
            "hp": local_fighter.health,
            "action": local_fighter.action,
            "flip": local_fighter.flip,
            "is_blocking": local_fighter.is_blocking,
            "is_crouching": local_fighter.is_crouching,
            "damage_event": dmg_event
        }
        try:
            msg = (json.dumps(packet) + "\n").encode("utf-8")
            self.network_socket.sendall(msg)
        except Exception:
            pass

        try:
            raw_data = self.network_socket.recv(4096).decode("utf-8")
            if raw_data:
                for line in raw_data.strip().split("\n"):
                    if not line:
                        continue
                    remote_data = json.loads(line)
                    
                    if remote_data.get("type") == "DISCONNECTED":
                        self.game_over = True
                        remote_fighter.health = 0
                        return

                    remote_fighter.rect.x = remote_data["x"]
                    remote_fighter.rect.y = remote_data["y"]
                    remote_fighter.set_action(remote_data["action"])
                    remote_fighter.flip = remote_data["flip"]
                    remote_fighter.is_blocking = remote_data.get("is_blocking", False)
                    remote_fighter.is_crouching = remote_data.get("is_crouching", False)

                    remote_dmg = remote_data.get("damage_event")
                    if remote_dmg:
                        local_fighter.take_damage(
                            remote_dmg["damage"], 
                            chip_only=remote_dmg["chip_only"]
                        )
                        local_fighter.vel_x = remote_dmg["knockback_x"]
                        kb_y = remote_dmg.get("knockback_y", 0)
                        if kb_y < 0:
                            local_fighter.vel_y = kb_y
                            local_fighter.jump = True
        except (BlockingIOError, socket.error):
            pass
        except Exception:
            pass

    def draw_hud(self, surface):
        """Draw the in-game HUD with Japanese wooden frame theme."""
        bar_w = 400
        bar_h = 22
        portrait_size = 82

        # --- Wood-themed HUD colors ---
        bar_bg = (35, 22, 12)           # Dark wood for bar background
        bar_border = (90, 60, 30)       # Wood border
        hp_green = (80, 180, 60)        # Health green
        hp_yellow = (218, 165, 32)      # Damage lag (gold)
        hp_low = (200, 50, 50)          # Low health red
        portrait_border = (100, 65, 30) # Wood portrait frame

        if self.local_player_id == 1:
            left_p, right_p = self.player1, self.player2
            left_name, right_name = self.player_name, self.p2_name
            self.p1_display_health += (left_p.health - self.p1_display_health) * 0.1
            self.p2_display_health += (right_p.health - self.p2_display_health) * 0.1
            left_lag, right_lag = self.p1_display_health, self.p2_display_health
            left_img, right_img = self.p1_img, self.p2_img
        else:
            left_p, right_p = self.player2, self.player1
            left_name, right_name = self.p2_name, self.player_name
            self.p2_display_health += (left_p.health - self.p2_display_health) * 0.1
            self.p1_display_health += (right_p.health - self.p1_display_health) * 0.1
            left_lag, right_lag = self.p2_display_health, self.p1_display_health
            left_img, right_img = self.p2_img, self.p1_img

        # --- LEFT PLAYER HUD ---
        p1_portrait_x, p1_portrait_y = 30, 20
        p1_bar_x = p1_portrait_x + portrait_size + 14
        p1_bar_y = 32

        # Portrait wood frame
        p1_box = pygame.Rect(p1_portrait_x - 3, p1_portrait_y - 3, portrait_size + 6, portrait_size + 6)
        pygame.draw.rect(surface, WOOD_DARK, p1_box, border_radius=4)
        if left_img:
            surface.blit(left_img, (p1_portrait_x, p1_portrait_y))
        pygame.draw.rect(surface, portrait_border, p1_box, 3, border_radius=4)

        # Health bar with wood container
        p1_container = pygame.Rect(p1_bar_x - 4, p1_bar_y - 4, bar_w + 8, bar_h + 8)
        pygame.draw.rect(surface, WOOD_DARK, p1_container, border_radius=6)
        pygame.draw.rect(surface, bar_border, p1_container, 2, border_radius=6)
        pygame.draw.rect(surface, bar_bg, (p1_bar_x, p1_bar_y, bar_w, bar_h), border_radius=4)
        
        p1_curr_ratio = max(0, left_p.health / max(1, left_p.max_health))
        p1_lag_ratio = max(0, left_lag / max(1, left_p.max_health))
        
        # Lag bar (gold)
        if int(p1_lag_ratio * bar_w) > 0:
            pygame.draw.rect(surface, hp_yellow, (p1_bar_x, p1_bar_y, int(p1_lag_ratio * bar_w), bar_h), border_radius=4)
        # Current health bar
        hp_color = hp_low if p1_curr_ratio < 0.25 else hp_green
        if int(p1_curr_ratio * bar_w) > 0:
            pygame.draw.rect(surface, hp_color, (p1_bar_x, p1_bar_y, int(p1_curr_ratio * bar_w), bar_h), border_radius=4)

        p1_name_surf = self.font_hud_name.render(left_name, True, ACCENT_GOLD)
        surface.blit(p1_name_surf, (p1_bar_x, p1_bar_y + bar_h + 6))

        # --- RIGHT PLAYER HUD ---
        p2_portrait_x = self.width - 30 - portrait_size
        p2_portrait_y = 20
        p2_bar_x = p2_portrait_x - bar_w - 14
        p2_bar_y = 32

        # Portrait wood frame
        p2_box = pygame.Rect(p2_portrait_x - 3, p2_portrait_y - 3, portrait_size + 6, portrait_size + 6)
        pygame.draw.rect(surface, WOOD_DARK, p2_box, border_radius=4)
        if right_img:
            surface.blit(right_img, (p2_portrait_x, p2_portrait_y))
        pygame.draw.rect(surface, portrait_border, p2_box, 3, border_radius=4)

        # Health bar
        p2_container = pygame.Rect(p2_bar_x - 4, p2_bar_y - 4, bar_w + 8, bar_h + 8)
        pygame.draw.rect(surface, WOOD_DARK, p2_container, border_radius=6)
        pygame.draw.rect(surface, bar_border, p2_container, 2, border_radius=6)
        pygame.draw.rect(surface, bar_bg, (p2_bar_x, p2_bar_y, bar_w, bar_h), border_radius=4)

        p2_curr_ratio = max(0, right_p.health / max(1, right_p.max_health))
        p2_lag_ratio = max(0, right_lag / max(1, right_p.max_health))
        p2_lag_w = int(p2_lag_ratio * bar_w)
        p2_curr_w = int(p2_curr_ratio * bar_w)
        
        if p2_lag_w > 0:
            pygame.draw.rect(surface, hp_yellow, (p2_bar_x + (bar_w - p2_lag_w), p2_bar_y, p2_lag_w, bar_h), border_radius=4)
        hp_color = hp_low if p2_curr_ratio < 0.25 else hp_green
        if p2_curr_w > 0:
            pygame.draw.rect(surface, hp_color, (p2_bar_x + (bar_w - p2_curr_w), p2_bar_y, p2_curr_w, bar_h), border_radius=4)

        p2_name_surf = self.font_hud_name.render(right_name, True, (200, 60, 60))
        surface.blit(p2_name_surf, (p2_bar_x + bar_w - p2_name_surf.get_width(), p2_bar_y + bar_h + 6))

        # Controls hint bar (wood panel at bottom)
        hint_panel = pygame.Surface((self.width, 30), pygame.SRCALPHA)
        hint_panel.fill((25, 16, 10, 160))
        surface.blit(hint_panel, (0, self.height - 30))
        hint_surf = self.font_hint.render(
            "A/D: Move | W: Jump | S: Sneak | J: Punch | I: Kick (Bonus in Air) | L: Block | ESC: Pause",
            True, TEXT_MUTED)
        surface.blit(hint_surf, (35, self.height - 26))

    def draw_text_centered(self, text, font, color, y_offset, surface, shadow_color=(20, 10, 5)):
        # Drop shadow for crisp arcade readability
        shadow_surf = font.render(text, True, shadow_color)
        text_surf = font.render(text, True, color)
        x = (self.width // 2) - (text_surf.get_width() // 2)
        y = (self.height // 2) - (text_surf.get_height() // 2) + y_offset
        surface.blit(shadow_surf, (x + 4, y + 4))
        surface.blit(text_surf, (x, y))

    def update(self, surface):
        local_fighter = self.player1 if self.local_player_id == 1 else self.player2

        # Active combat phase (before KO)
        if self.intro_timer <= 0 and not self.ko_triggered and not self.game_over:
            self.player1.move(self.player2, self.arena_width)
            self.player2.move(self.player1, self.arena_width)
            
            self.resolve_pushbox_collision()
            
            if not self.is_online:
                self.player1.handle_player_inputs(self.player2)
            else:
                if self.local_player_id == 1:
                    self.player1.handle_player_inputs(self.player2)
                else:
                    self.player2.handle_player_inputs(self.player1)
                self.sync_network()

            self.update_camera()
        elif self.ko_triggered and not self.game_over:
            # Keep gravity & knockback physics running during KO fall
            self.player1.move(self.player2, self.arena_width)
            self.player2.move(self.player1, self.arena_width)
            if self.is_online:
                self.sync_network()

        # Trigger screen shake when the local user takes damage
        if local_fighter.took_damage_this_frame:
            self.screen_shake = 12
            local_fighter.took_damage_this_frame = False
        # Clear bot's flag
        self.player1.took_damage_this_frame = False
        self.player2.took_damage_this_frame = False

        self.player1.update_animation()
        self.player2.update_animation()
        
        # Check for KO state and count down the KO delay before ending the match
        if not self.game_over:
            if self.player1.health <= 0 or self.player2.health <= 0:
                self.ko_triggered = True
                if self.ko_timer > 0:
                    self.ko_timer -= 1
                else:
                    self.game_over = True

        # Calculate screen shake offsets
        shake_x, shake_y = 0, 0
        if self.screen_shake > 0:
            self.screen_shake -= 1
            shake_x = random.randint(-7, 7)
            shake_y = random.randint(-5, 5)

        effective_cam_x = int(self.camera_x) - shake_x

        if self.bg_img:
            surface.blit(self.bg_img, (-effective_cam_x, shake_y))
        else:
            surface.fill((40, 40, 40))
            pygame.draw.rect(surface, (100, 100, 100), (0, self.floor_level + shake_y, self.width, self.height - self.floor_level)) 
        
        if self.local_player_id == 1:
            self.player1.draw(surface, effective_cam_x, shake_y)
            self.player2.draw(surface, effective_cam_x, shake_y)
        else:
            self.player2.draw(surface, effective_cam_x, shake_y)
            self.player1.draw(surface, effective_cam_x, shake_y)

        self.draw_hud(surface)
        
        if self.intro_timer > 0:
            # MANAS'S AUDIO FIX
            if self.intro_timer == 90:
                play_sound("Fight.wav", 0.9)
            # "FIGHT!" banner in Japanese style
            self.draw_text_centered("FIGHT!", self.font_large, ACCENT_GOLD, -50, surface)
            self.intro_timer -= 1
        elif self.ko_triggered:
            # "K.O.!" banner while the dying animation plays out
            self.draw_text_centered("K.O.!", self.font_large, (220, 38, 38), -50, surface)

        keys = pygame.key.get_pressed()
        if keys[pygame.K_ESCAPE]:
            return "PAUSE_MENU"
            
        return "RUNNING"


def run_game(screen, clock, player_stats, is_online=False, local_player_id=1, network_socket=None):
    # MANAS'S AUDIO FIX
    play_music("battle.wav", volume=0.45, loop=-1)
    
    chosen_stage = player_stats.get("active_stage", 1)
    
    bot_hp = 150 + (chosen_stage * 50)
    bot_dmg = 5 + (chosen_stage * 4)

    match = FightingMatch(
        width=screen.get_width(),
        height=screen.get_height(),
        current_level=chosen_stage,
        p1_max_hp=max(150, player_stats.get("max_hp", 250)),
        p1_dmg=player_stats.get("attack_power", 10),
        bot_max_hp=bot_hp,
        bot_dmg=bot_dmg,
        player_name=player_stats.get("name", "Player_2766"),
        is_online=is_online,
        local_player_id=local_player_id,
        network_socket=network_socket,
        unlocked_abilities=player_stats.get("unlocked_abilities", None),
    )

    pause_menu = PauseMenu(screen.get_width(), screen.get_height())

    playing = True
    while playing:
        clock.tick(60)
        events = pygame.event.get()
        
        for event in events:
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                paused = True
                while paused:
                    clock.tick(60)
                    pause_events = pygame.event.get()
                    for p_event in pause_events:
                        if p_event.type == pygame.QUIT:
                            pygame.quit()
                            sys.exit()

                    action = pause_menu.update(pause_events, screen)
                    if action == "RESUME":
                        paused = False
                    elif action == "HOME":
                        return "BACK_TO_MENU"
                        
                    pygame.display.flip()

        status = match.update(screen)
        if status == "PAUSE_MENU":
            return "PAUSE_MENU"

        if match.game_over:
            local_won = (match.player1.health > 0) if local_player_id == 1 else (match.player2.health > 0)
            return "MATCH_WON" if local_won else "MATCH_LOST"

        pygame.display.flip()