import pygame
import os
from sound_manager import play_sound, play_music, fadeout_music, stop_music

# --- ASSET PATH HELPERS ---
ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
BG_DIR = os.path.join(ASSET_DIR, "backgrounds")
FONT_DIR = os.path.join(ASSET_DIR, "fonts")
PORTRAIT_DIR = os.path.join(ASSET_DIR, "portraits")

# --- STYLE THEME PALETTE - Japanese Pixel Art ---
BG_COLOR = (25, 16, 10)            
CARD_BG = (42, 28, 18, 220)        
CARD_BG_SOLID = (42, 28, 18)
BTN_BG = (58, 38, 22, 0)           
BTN_HOVER = (180, 120, 40, 60)     
BORDER_COLOR = (90, 62, 35, 0)     
BORDER_HOVER = (218, 165, 32, 180) 

WOOD_DARK = (62, 40, 20)
WOOD_MID = (100, 65, 30)
WOOD_LIGHT = (140, 95, 45)
WOOD_HIGHLIGHT = (180, 130, 60)
WOOD_BORDER = (45, 28, 12)

TEXT_WHITE = (248, 240, 220)        
ACCENT_GOLD = (218, 165, 32)       
ACCENT_RED = (178, 34, 34)         
TEXT_MUTED = (140, 125, 100)       
VICTORY_CYAN = (100, 200, 220)     
DANGER_RED = (200, 50, 50)         

LVL_UNLOCKED_BG = (45, 70, 35)    
LVL_LOCKED_BG = (35, 25, 18)      
LVL_LOCKED_BORDER = (55, 40, 28)  


def safe_font(font_filename, size, bold=False):
    search_paths = [
        font_filename,
        os.path.join(FONT_DIR, font_filename),
        os.path.join("Fonts", font_filename),
    ]
    for p in search_paths:
        if os.path.exists(p):
            try:
                return pygame.font.Font(p, size)
            except Exception:
                pass
    return pygame.font.SysFont("dejavusans", size, bold=bold)


def load_bg_image(filenames, width, height):
    for filename in filenames:
        candidates = [filename, os.path.join(BG_DIR, filename)]
        for path in candidates:
            if os.path.exists(path):
                try:
                    img = pygame.image.load(path).convert_alpha()
                    return pygame.transform.scale(img, (width, height))
                except Exception:
                    continue
    return None


class MenuButton:
    def __init__(self, x, y, width, height, text, font, action_name,
                 is_enabled=True, is_invisible_text=False):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.font = font
        self.action_name = action_name
        self.is_enabled = is_enabled
        self.is_hovered = False
        self.is_invisible_text = is_invisible_text

    def update(self, mouse_pos):
        if self.is_enabled:
            self.is_hovered = self.rect.collidepoint(mouse_pos)
        else:
            self.is_hovered = False

    def draw(self, surface, custom_bg=None, custom_border=None):
        if not self.is_enabled:
            bg = LVL_LOCKED_BG
            border = LVL_LOCKED_BORDER
            text_color = TEXT_MUTED
            is_visible = True
        else:
            bg = custom_bg if custom_bg else (BTN_HOVER if self.is_hovered else BTN_BG)
            border = custom_border if custom_border else (BORDER_HOVER if self.is_hovered else BORDER_COLOR)
            text_color = ACCENT_GOLD if self.is_hovered else TEXT_WHITE
            is_visible = not self.is_invisible_text or self.is_hovered

        if is_visible:
            if self.is_invisible_text:
                glow_surf = pygame.Surface((self.rect.width, self.rect.height), pygame.SRCALPHA)
                pygame.draw.rect(glow_surf, (218, 165, 32, 40), glow_surf.get_rect(), border_radius=8)
                pygame.draw.rect(glow_surf, (218, 165, 32, 140), glow_surf.get_rect(), 3, border_radius=8)
                surface.blit(glow_surf, self.rect.topleft)
            else:
                pygame.draw.rect(surface, bg, self.rect, border_radius=8)
                pygame.draw.rect(surface, border, self.rect, 2, border_radius=8)

                text_surf = self.font.render(self.text, True, text_color)
                surface.blit(text_surf, text_surf.get_rect(center=self.rect.center))

    def is_clicked(self, event):
        if self.is_enabled and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.is_hovered:
                play_sound("sound_click.wav", 0.6)
                return self.action_name
        return None


def draw_wood_button(surface, rect, text, font, is_hovered=False, is_enabled=True,
                     accent_color=None):
    if not is_enabled:
        bg_top, bg_bot = (50, 35, 22), (38, 25, 15)
        border = (60, 42, 25)
        text_color = TEXT_MUTED
    elif is_hovered:
        bg_top = (145, 100, 50)
        bg_bot = (110, 72, 35)
        border = ACCENT_GOLD
        text_color = ACCENT_GOLD
    else:
        bg_top = WOOD_MID
        bg_bot = WOOD_DARK
        border = WOOD_BORDER
        text_color = accent_color if accent_color else TEXT_WHITE

    top_rect = pygame.Rect(rect.x, rect.y, rect.width, rect.height // 2)
    bot_rect = pygame.Rect(rect.x, rect.y + rect.height // 2, rect.width, rect.height // 2)
    pygame.draw.rect(surface, bg_top, top_rect, border_radius=6)
    pygame.draw.rect(surface, bg_bot, bot_rect, border_radius=6)
    pygame.draw.rect(surface, border, rect, 3, border_radius=6)

    if is_enabled:
        highlight = pygame.Surface((rect.width - 10, 2), pygame.SRCALPHA)
        highlight.fill((255, 220, 160, 60))
        surface.blit(highlight, (rect.x + 5, rect.y + 3))

    text_surf = font.render(text, True, text_color)
    surface.blit(text_surf, text_surf.get_rect(center=rect.center))


def draw_floating_card(surface, width, height, card_w=480, card_h=420):
    dim_overlay = pygame.Surface((width, height), pygame.SRCALPHA)
    dim_overlay.fill((10, 8, 5, 180))
    surface.blit(dim_overlay, (0, 0))

    card_x = (width - card_w) // 2
    card_y = (height - card_h) // 2
    card_rect = pygame.Rect(card_x, card_y, card_w, card_h)

    card_surface = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
    card_surface.fill((42, 28, 18, 235))
    surface.blit(card_surface, (card_x, card_y))

    pygame.draw.rect(surface, WOOD_BORDER, card_rect, 4, border_radius=12)
    inner = card_rect.inflate(-8, -8)
    pygame.draw.rect(surface, (90, 62, 35), inner, 2, border_radius=10)

    bar_rect = pygame.Rect(card_x + 20, card_y + 8, card_w - 40, 4)
    pygame.draw.rect(surface, ACCENT_GOLD, bar_rect, border_radius=2)

    return card_rect


class Slider:
    """A custom interactive volume slider widget."""
    def __init__(self, x, y, w, h, initial_val=1.0):
        self.rect = pygame.Rect(x, y, w, h)
        self.val = initial_val
        self.is_dragging = False

    def update(self, event, mouse_pos):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            hitbox = self.rect.inflate(20, 30) # Generous clicking area
            if hitbox.collidepoint(mouse_pos):
                self.is_dragging = True
                self._update_val(mouse_pos[0])
                return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.is_dragging:
                self.is_dragging = False
                return True
        elif event.type == pygame.MOUSEMOTION:
            if self.is_dragging:
                self._update_val(mouse_pos[0])
                return True
        return False

    def _update_val(self, mx):
        rel_x = mx - self.rect.x
        self.val = max(0.0, min(1.0, rel_x / self.rect.width))

    def draw(self, surface, font, label):
        # Empty track
        pygame.draw.rect(surface, (25, 16, 10), self.rect, border_radius=self.rect.height//2)
        
        # Filled volume track
        fill_w = int(self.val * self.rect.width)
        fill_rect = pygame.Rect(self.rect.x, self.rect.y, fill_w, self.rect.height)
        if fill_w > 0:
            pygame.draw.rect(surface, ACCENT_GOLD, fill_rect, border_radius=self.rect.height//2)
        
        # Track border
        pygame.draw.rect(surface, WOOD_BORDER, self.rect, 2, border_radius=self.rect.height//2)

        # Draggable Handle
        hx = self.rect.x + fill_w
        pygame.draw.circle(surface, TEXT_WHITE, (hx, self.rect.centery), int(self.rect.height * 0.9))
        pygame.draw.circle(surface, WOOD_HIGHLIGHT, (hx, self.rect.centery), int(self.rect.height * 0.9), 2)

        # Volume Text Label
        lbl = font.render(f"{label}: {int(self.val * 100)}%", True, TEXT_WHITE)
        surface.blit(lbl, (self.rect.x, self.rect.y - 28))


class SettingsMenu:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.font_title = safe_font("Rogue.ttf", 48, bold=True)
        self.font_btn = safe_font("stalin.ttf", 22)
        self.font_label = safe_font("stalin.ttf", 16)

        card_w, card_h = 420, 430
        cx = (width - card_w) // 2
        cy = (height - card_h) // 2

        # Sliders
        slider_x = cx + 60
        slider_w = 300
        self.music_slider = Slider(slider_x, cy + 130, slider_w, 18, 0.45)
        self.sfx_slider = Slider(slider_x, cy + 220, slider_w, 18, 1.0)

        # Buttons
        self.btn_back = MenuButton(cx + 70, cy + 290, 280, 50, "CLOSE", self.font_btn, "BACK")
        self.btn_quit = MenuButton(cx + 70, cy + 355, 280, 50, "QUIT GAME", self.font_btn, "QUIT")
        self.buttons = [self.btn_back, self.btn_quit]

    def update(self, events, surface):
        mouse_pos = pygame.mouse.get_pos()
        action_triggered = None
        volumes_changed = False

        card_rect = draw_floating_card(surface, self.width, self.height, 420, 440)

        title = self.font_title.render("SETTINGS", True, ACCENT_GOLD)
        surface.blit(title, title.get_rect(center=(self.width // 2, card_rect.top + 55)))

        div_y = card_rect.top + 85
        pygame.draw.line(surface, WOOD_LIGHT, (card_rect.left + 40, div_y), (card_rect.right - 40, div_y), 2)

        for event in events:
            # Update Sliders
            if self.music_slider.update(event, mouse_pos):
                volumes_changed = True
            if self.sfx_slider.update(event, mouse_pos):
                volumes_changed = True

            # Update Buttons
            for btn in self.buttons:
                act = btn.is_clicked(event)
                if act:
                    action_triggered = act

        self.music_slider.draw(surface, self.font_label, "MUSIC VOLUME")
        self.sfx_slider.draw(surface, self.font_label, "SFX VOLUME")

        for btn in self.buttons:
            btn.update(mouse_pos)
            if btn.action_name == "QUIT":
                draw_wood_button(surface, btn.rect, btn.text, btn.font, btn.is_hovered, accent_color=DANGER_RED)
            else:
                draw_wood_button(surface, btn.rect, btn.text, btn.font, btn.is_hovered)

        if action_triggered:
            return action_triggered
        elif volumes_changed:
            return "VOLUMES_CHANGED"
        return None


class PauseMenu:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.font_title = safe_font("Rogue.ttf", 38, bold=True)
        self.font_btn = safe_font("stalin.ttf", 22)

        card_w, card_h = 420, 320
        cx = (width - 280) // 2
        cy = (height - card_h) // 2

        self.buttons = [
            MenuButton(cx, cy + 120, 280, 54, "RESUME MATCH", self.font_btn, "RESUME"),
            MenuButton(cx, cy + 195, 280, 54, "HOME SCREEN", self.font_btn, "HOME"),
        ]

    def update(self, events, surface):
        mouse_pos = pygame.mouse.get_pos()
        action_triggered = None

        card_rect = draw_floating_card(surface, self.width, self.height, 420, 320)

        title = self.font_title.render("GAME PAUSED", True, ACCENT_GOLD)
        surface.blit(title, title.get_rect(center=(self.width // 2, card_rect.top + 55)))

        div_y = card_rect.top + 85
        pygame.draw.line(surface, WOOD_LIGHT, (card_rect.left + 40, div_y),
                         (card_rect.right - 40, div_y), 2)

        for event in events:
            for btn in self.buttons:
                act = btn.is_clicked(event)
                if act:
                    action_triggered = act

        for btn in self.buttons:
            btn.update(mouse_pos)
            draw_wood_button(surface, btn.rect, btn.text, btn.font, btn.is_hovered)

        return action_triggered


class LevelSelectMenu:
    def __init__(self, width, height):
        self.width = width
        self.height = height

        self.font_title = safe_font("Rogue.ttf", 40, bold=True)
        self.font_btn = safe_font("stalin.ttf", 20)
        self.font_lock = safe_font("Ryzes.ttf", 14)
        self.font_stage_name = safe_font("stalin.ttf", 16)

        self.bg_img = load_bg_image(
            ["level_select_bg.png", "level_menu_bg.png", "level_bg.png"], width, height)

        self.back_btn = MenuButton(40, 30, 130, 48, "< BACK", self.font_btn, "BACK_HOME")
        self.continue_btn = MenuButton(width - 260, height - 90, 220, 58,
                                       "CONTINUE >", self.font_btn, "CONTINUE_CURRENT")

        stage_names = ["Bamboo\nGrove", "Sky\nBridge", "Shadow\nTemple",
                       "Dragon\nPeak", "Sakura\nThrone"]

        self.level_nodes = []
        node_w, node_h = 150, 150
        spacing = 45
        start_x = (width - (5 * node_w + 4 * spacing)) // 2
        y_pos = height // 2 - node_h // 2 

        for idx in range(1, 6):
            x_pos = start_x + (idx - 1) * (node_w + spacing)
            self.level_nodes.append({
                "level_num": idx,
                "name": stage_names[idx - 1],
                "button": MenuButton(x_pos, y_pos, node_w, node_h,
                                     f"STAGE {idx}", self.font_btn, f"PLAY_LVL_{idx}")
            })

    def update(self, events, surface, current_unlocked_level):
        mouse_pos = pygame.mouse.get_pos()
        action_triggered = None

        for event in events:
            act = self.back_btn.is_clicked(event)
            if act:
                action_triggered = act

            act = self.continue_btn.is_clicked(event)
            if act:
                action_triggered = act

            for node in self.level_nodes:
                lvl = node["level_num"]
                node["button"].is_enabled = (lvl <= current_unlocked_level)
                act = node["button"].is_clicked(event)
                if act:
                    action_triggered = act

        if self.bg_img:
            surface.blit(self.bg_img, (0, 0))
        else:
            surface.fill(BG_COLOR)

        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((15, 10, 5, 100))
        surface.blit(overlay, (0, 0))

        title_w, title_h = 520, 65
        title_rect = pygame.Rect((self.width - title_w) // 2, 25, title_w, title_h)
        pygame.draw.rect(surface, WOOD_DARK, title_rect, border_radius=8)
        pygame.draw.rect(surface, WOOD_BORDER, title_rect, 3, border_radius=8)
        pygame.draw.line(surface, (120, 82, 40),
                         (title_rect.left + 10, title_rect.top + 4),
                         (title_rect.right - 10, title_rect.top + 4), 2)

        title = self.font_title.render("SELECT CAMPAIGN", True, ACCENT_GOLD)
        surface.blit(title, title.get_rect(center=title_rect.center))

        self.back_btn.update(mouse_pos)
        draw_wood_button(surface, self.back_btn.rect, self.back_btn.text,
                         self.back_btn.font, self.back_btn.is_hovered)

        self.continue_btn.update(mouse_pos)
        draw_wood_button(surface, self.continue_btn.rect, self.continue_btn.text,
                         self.continue_btn.font, self.continue_btn.is_hovered,
                         accent_color=ACCENT_GOLD)

        for node in self.level_nodes:
            lvl = node["level_num"]
            btn = node["button"]
            btn.update(mouse_pos)

            r = btn.rect
            if lvl < current_unlocked_level:
                bg_top = (55, 85, 40) if btn.is_hovered else (45, 70, 35)
                bg_bot = (35, 55, 25) if btn.is_hovered else (30, 48, 20)
                border = (80, 160, 60) if btn.is_hovered else (60, 120, 45)
                name_color = (130, 200, 100)
            elif lvl == current_unlocked_level:
                bg_top = WOOD_MID if btn.is_hovered else (85, 55, 28)
                bg_bot = WOOD_DARK if btn.is_hovered else (55, 36, 18)
                border = ACCENT_GOLD
                name_color = ACCENT_GOLD
            else:
                bg_top = (40, 28, 16)
                bg_bot = (28, 18, 10)
                border = (55, 38, 22)
                name_color = TEXT_MUTED

            top_r = pygame.Rect(r.x, r.y, r.width, r.height // 2)
            pygame.draw.rect(surface, bg_top, top_r, border_radius=8)
            bot_r = pygame.Rect(r.x, r.y + r.height // 2, r.width, r.height // 2)
            pygame.draw.rect(surface, bg_bot, bot_r, border_radius=8)
            pygame.draw.rect(surface, border, r, 3, border_radius=8)

            if lvl <= current_unlocked_level:
                num_text = self.font_btn.render(f"STAGE {lvl}", True,
                                                ACCENT_GOLD if btn.is_hovered else TEXT_WHITE)
            else:
                num_text = self.font_btn.render(f"STAGE {lvl}", True, TEXT_MUTED)
            surface.blit(num_text, num_text.get_rect(center=(r.centerx, r.centery - 25)))

            pygame.draw.line(surface, border, (r.left + 18, r.centery), (r.right - 18, r.centery), 1)

            nm_text = self.font_stage_name.render(node["name"], True, name_color)
            surface.blit(nm_text, nm_text.get_rect(center=(r.centerx, r.centery + 28)))

            if lvl > current_unlocked_level:
                lock_lbl = self.font_lock.render("[ LOCKED ]", True, TEXT_MUTED)
                surface.blit(lock_lbl, lock_lbl.get_rect(center=(r.centerx, r.bottom + 20)))

            if lvl < current_unlocked_level:
                check = self.font_btn.render("V", True, (100, 200, 80))
                surface.blit(check, (r.right - 28, r.top + 6))

        return action_triggered


class MainMenu:
    def __init__(self, width, height):
        self.width = width
        self.height = height

        self.font_title = safe_font("Rogue.ttf", 96, bold=True)
        self.font_subtitle = safe_font("Rogue.ttf", 30)
        self.font_btn = safe_font("stalin.ttf", 26)
        self.font_stats = safe_font("stalin.ttf", 16)

        self.show_profile = False
        self.is_editing_name = False
        self.name_rect = pygame.Rect(40, 137, 280, 42)

        self.main_buttons = [
            MenuButton(505, 377, 270, 72, "BATTLE", self.font_btn, "BATTLE", is_invisible_text=True),
            MenuButton(505, 469, 270, 72, "ONLINE", self.font_btn, "ONLINE", is_invisible_text=True),
            MenuButton(77, 450, 245, 140, "TRAIN", self.font_btn, "TRAIN", is_invisible_text=True),
            MenuButton(1148, 20, 108, 110, "QUIT", self.font_btn, "SETTINGS", is_invisible_text=True),
            MenuButton(24, 22, 312, 115, "PROFILE", self.font_btn, "PROFILE", is_invisible_text=True),
        ]

        modal_cx = (width - 320) // 2
        modal_cy = (height - 380) // 2

        self.win_buttons = [
            MenuButton(modal_cx, modal_cy + 200, 320, 54, "NEXT LEVEL", self.font_btn, "NEXT_LEVEL"),
            MenuButton(modal_cx, modal_cy + 270, 320, 54, "HOME SCREEN", self.font_btn, "HOME"),
        ]

        self.final_win_buttons = [
            MenuButton(modal_cx, modal_cy + 240, 320, 54, "RETURN TO HOME", self.font_btn, "HOME")
        ]

        self.loss_buttons = [
            MenuButton(modal_cx, modal_cy + 200, 320, 54, "RETRY BATTLE", self.font_btn, "RETRY"),
            MenuButton(modal_cx, modal_cy + 270, 320, 54, "HOME SCREEN", self.font_btn, "HOME"),
        ]

        self.main_bg = load_bg_image(
            ["homescreen.png", "main_menu_bg.png", "homescreen_custom.png"], width, height)
        self.victory_bg = load_bg_image(
            ["victory_bg.png", "win_bg.png"], width, height)
        self.defeat_bg = load_bg_image(
            ["defeat_bg.png", "loss_bg.png"], width, height)

    def draw_stats_panel(self, surface, player_stats):
        px, py = 40, 142
        panel_rect = pygame.Rect(px, py, 280, 130)

        p_surf = pygame.Surface((280, 130), pygame.SRCALPHA)
        p_surf.fill((42, 28, 18, 210))
        surface.blit(p_surf, (px, py))

        border_col = (218, 165, 32) if self.is_editing_name else WOOD_BORDER
        pygame.draw.rect(surface, border_col, panel_rect, 3, border_radius=10)
        inner = panel_rect.inflate(-6, -6)
        pygame.draw.rect(surface, (65, 45, 25), inner, 1, border_radius=8)

        p_name = player_stats.get("name", "Player_2766")
        lvl = player_stats.get("level", 1)
        xp = player_stats.get("xp", 0)
        hp = player_stats.get("max_hp", 150)
        pwr = player_stats.get("attack_power", 10)

        display_name = f"{p_name}|" if self.is_editing_name else f"NAME: {p_name}"
        txt_name = self.font_stats.render(display_name, True,
                                          (218, 165, 32) if self.is_editing_name else ACCENT_GOLD)
        txt_lvl = self.font_stats.render(f"FITNESS LVL: {lvl}", True, TEXT_WHITE)
        txt_xp = self.font_stats.render(f"XP: {xp} / {lvl * 100}", True, TEXT_WHITE)
        txt_hp = self.font_stats.render(f"MAX HP: {hp}", True, TEXT_WHITE)
        txt_pwr = self.font_stats.render(f"ATTACK PWR: {pwr}", True, TEXT_WHITE)

        surface.blit(txt_name, (px + 14, py + 12))
        surface.blit(txt_lvl, (px + 14, py + 34))
        surface.blit(txt_xp, (px + 14, py + 56))
        surface.blit(txt_hp, (px + 14, py + 78))
        surface.blit(txt_pwr, (px + 14, py + 100))

    def update(self, events, surface, mode="MAIN", player_stats=None):
        mouse_pos = pygame.mouse.get_pos()
        action_triggered = None

        if mode == "MAIN":
            active_buttons = self.main_buttons
        elif mode == "WIN":
            if player_stats and player_stats.get("active_stage", 1) >= 5:
                active_buttons = self.final_win_buttons
            else:
                active_buttons = self.win_buttons
        else:
            active_buttons = self.loss_buttons

        for event in events:
            if mode == "MAIN" and player_stats:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self.main_buttons[4].rect.collidepoint(mouse_pos):
                        self.show_profile = not self.show_profile
                        self.is_editing_name = False
                    elif self.show_profile and self.name_rect.collidepoint(mouse_pos):
                        self.is_editing_name = True
                    else:
                        self.is_editing_name = False

                if self.is_editing_name and event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        self.is_editing_name = False
                    elif event.key == pygame.K_BACKSPACE:
                        player_stats["name"] = player_stats["name"][:-1]
                    else:
                        if len(player_stats["name"]) < 14 and (event.unicode.isalnum() or event.unicode in "_-"):
                            player_stats["name"] += event.unicode

            for btn in active_buttons:
                act = btn.is_clicked(event)
                if act:
                    action_triggered = act

        if mode == "MAIN":
            if self.main_bg:
                surface.blit(self.main_bg, (0, 0))
            else:
                surface.fill(BG_COLOR)

            if player_stats and self.show_profile:
                self.draw_stats_panel(surface, player_stats)

            for btn in self.main_buttons:
                btn.update(mouse_pos)
                btn.draw(surface)

        elif mode == "WIN":
            if self.victory_bg:
                surface.blit(self.victory_bg, (0, 0))
            else:
                surface.fill(BG_COLOR)

            card_rect = draw_floating_card(surface, self.width, self.height, 500, 380)

            title = self.font_title.render("VICTORY!", True, ACCENT_GOLD)
            surface.blit(title, title.get_rect(center=(self.width // 2, card_rect.top + 55)))

            div_y = card_rect.top + 95
            pygame.draw.line(surface, WOOD_LIGHT,
                             (card_rect.left + 40, div_y), (card_rect.right - 40, div_y), 2)

            if player_stats and player_stats.get("active_stage", 1) >= 5:
                subtitle = self.font_subtitle.render("Champion! All stages conquered!", True, ACCENT_GOLD)
            else:
                subtitle = self.font_subtitle.render("Stage Cleared!", True, TEXT_WHITE)
            surface.blit(subtitle, subtitle.get_rect(center=(self.width // 2, card_rect.top + 130)))

            for btn in active_buttons:
                btn.update(mouse_pos)
                draw_wood_button(surface, btn.rect, btn.text, btn.font, btn.is_hovered)

        elif mode == "LOSS":
            if self.defeat_bg:
                surface.blit(self.defeat_bg, (0, 0))
            else:
                surface.fill(BG_COLOR)

            card_rect = draw_floating_card(surface, self.width, self.height, 500, 380)

            title = self.font_title.render("DEFEAT!", True, DANGER_RED)
            surface.blit(title, title.get_rect(center=(self.width // 2, card_rect.top + 55)))

            div_y = card_rect.top + 95
            pygame.draw.line(surface, (120, 50, 30),
                             (card_rect.left + 40, div_y), (card_rect.right - 40, div_y), 2)

            subtitle = self.font_subtitle.render("Rise Again, Warrior!", True, TEXT_WHITE)
            surface.blit(subtitle, subtitle.get_rect(center=(self.width // 2, card_rect.top + 130)))

            for btn in active_buttons:
                btn.update(mouse_pos)
                draw_wood_button(surface, btn.rect, btn.text, btn.font, btn.is_hovered)

        return action_triggered