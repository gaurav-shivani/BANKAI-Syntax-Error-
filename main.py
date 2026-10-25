import pygame
import sys
import os
import socket
import json
from menu import MainMenu, LevelSelectMenu, SettingsMenu, safe_font, load_bg_image, draw_wood_button
from menu import ACCENT_GOLD, TEXT_WHITE, TEXT_MUTED, BG_COLOR, WOOD_DARK, WOOD_BORDER
from game import run_game
from train import run_training
from sound_manager import play_music

# --- ASSET PATHS & SAVE FILE ---
ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
BG_DIR = os.path.join(ASSET_DIR, "backgrounds")
SAVE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "save_data.json")

# --- SAVE / LOAD LOGIC ---
DEFAULT_STATS = {
    "name": "Player_2766",
    "level": 1,
    "unlocked_stage": 1,
    "active_stage": 1,  
    "xp": 0,
    "max_hp": 150,
    "attack_power": 10,
    "training_level": 0,
    "unlocked_abilities": [],
}

def load_player_stats():
    """Load player stats from disk or return default values."""
    if os.path.exists(SAVE_FILE):
        try:
            with open(SAVE_FILE, "r") as f:
                saved = json.load(f)
                # Merge with default keys in case new fields were added in updates
                stats = DEFAULT_STATS.copy()
                stats.update(saved)
                return stats
        except Exception as e:
            print(f"Failed to load save file, using defaults: {e}")
    return DEFAULT_STATS.copy()

def save_player_stats(stats):
    """Write player stats to local JSON file."""
    try:
        with open(SAVE_FILE, "w") as f:
            json.dump(stats, f, indent=4)
    except Exception as e:
        print(f"Failed to save player stats: {e}")

# Pygame Setup - Standard 16:9 Desktop HD Resolution
pygame.init()
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SCALED | pygame.FULLSCREEN)
pygame.display.set_caption("Bankai — Motion Kombat")
clock = pygame.time.Clock()

menu = MainMenu(SCREEN_WIDTH, SCREEN_HEIGHT)
level_select = LevelSelectMenu(SCREEN_WIDTH, SCREEN_HEIGHT)
settings_menu = SettingsMenu(SCREEN_WIDTH, SCREEN_HEIGHT)

# Waiting screen assets
waiting_bg = load_bg_image(["waiting_bg.png"], SCREEN_WIDTH, SCREEN_HEIGHT)
font_waiting_title = safe_font("Rogue.ttf", 38, bold=True)
font_waiting_sub = safe_font("rubik.ttf", 20)
font_waiting_hint = safe_font("rubik.ttf", 14)

# Load persistent user data
player_stats = load_player_stats()

app_state = "HOME"
net_socket = None
local_id = None
waiting_anim_counter = 0


def connect_to_server(server_ip, player_stats, chosen_character_sprite):
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client_socket.settimeout(1.0)  # Give a slight buffer for the initial handshake
        client_socket.connect((server_ip, 5555))
        
        init_data = client_socket.recv(2048).decode('utf-8')
        init_packet = json.loads(init_data)
        local_id = init_packet.get("player_id")
        
        setup_packet = json.dumps({
            "type": "INIT_SETUP",
            "player_id": local_id,
            "player_name": player_stats["name"],
            "character_sheet": chosen_character_sprite
        })
        client_socket.sendall(setup_packet.encode('utf-8'))
        client_socket.settimeout(0.01)  # Non-blocking polling for the game loop
        
        return client_socket, local_id

    except (socket.timeout, TimeoutError):
        print(f"Connection to {server_ip}:5555 timed out. Is the server running?")
        client_socket.close()
        return None, None

    except Exception as e:
        print(f"Connection failed: {e}")
        try:
            client_socket.close()
        except Exception:
            pass
        return None, None


def draw_waiting_screen(surface, counter):
    """Draw themed waiting-for-opponent screen."""
    if waiting_bg:
        surface.blit(waiting_bg, (0, 0))
    else:
        surface.fill(BG_COLOR)

    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((15, 10, 5, 140))
    surface.blit(overlay, (0, 0))

    panel_w, panel_h = 600, 220
    panel_rect = pygame.Rect((SCREEN_WIDTH - panel_w) // 2,
                             (SCREEN_HEIGHT - panel_h) // 2,
                             panel_w, panel_h)
    pygame.draw.rect(surface, WOOD_DARK, panel_rect, border_radius=10)
    pygame.draw.rect(surface, WOOD_BORDER, panel_rect, 3, border_radius=10)
    pygame.draw.line(surface, (100, 68, 35),
                     (panel_rect.left + 10, panel_rect.top + 4),
                     (panel_rect.right - 10, panel_rect.top + 4), 2)

    dots = "." * ((counter // 30) % 4)
    title = font_waiting_title.render(f"AWAITING OPPONENT{dots}", True, ACCENT_GOLD)
    surface.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, panel_rect.centery - 30)))

    sub = font_waiting_sub.render("Searching for a worthy challenger...", True, TEXT_WHITE)
    surface.blit(sub, sub.get_rect(center=(SCREEN_WIDTH // 2, panel_rect.centery + 20)))

    hint = font_waiting_hint.render("Press ESC to cancel", True, TEXT_MUTED)
    surface.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, panel_rect.bottom - 25)))


# Start the main menu music on launch
play_music("home.mp3", volume=0.45, loop=-1)

running = True

while running:
    clock.tick(60)
    events = pygame.event.get()

    for event in events:
        if event.type == pygame.QUIT:
            save_player_stats(player_stats)
            running = False
            sys.exit()

    if app_state == "HOME":
        action = menu.update(events, screen, mode="MAIN", player_stats=player_stats)
        if action == "BATTLE":
            app_state = "LEVEL_SELECTION"
        elif action == "ONLINE":
            server_ip = "10.61.40.92" 
            chosen_sprite = "fighter.png"
            net_socket, local_id = connect_to_server(server_ip, player_stats, chosen_sprite)
            if net_socket:
                app_state = "WAITING_FOR_OPPONENT"
                waiting_anim_counter = 0
            else:
                app_state = "HOME"
        elif action == "TRAIN":
            run_training(screen, clock, player_stats)
            # Save stats immediately after training completes
            save_player_stats(player_stats)
            # Restart menu music when returning from the training screen
            play_music("home.mp3", volume=0.45, loop=-1)
        elif action == "SETTINGS":
            app_state = "SETTINGS"
        elif action == "QUIT":
            save_player_stats(player_stats)
            running = False
            sys.exit()

    elif app_state == "SETTINGS":
        menu.update([], screen, mode="MAIN", player_stats=player_stats)
        action = settings_menu.update(events, screen)
        
        if action == "VOLUMES_CHANGED":
            try:
                pygame.mixer.music.set_volume(settings_menu.music_slider.val)
                for i in range(pygame.mixer.get_num_channels()):
                    pygame.mixer.Channel(i).set_volume(settings_menu.sfx_slider.val)
            except Exception:
                pass
                
        elif action == "BACK":
            app_state = "HOME"
            
        elif action == "QUIT":
            save_player_stats(player_stats)
            running = False
            sys.exit()

    elif app_state == "WAITING_FOR_OPPONENT":
        waiting_anim_counter += 1
        draw_waiting_screen(screen, waiting_anim_counter)

        try:
            data = net_socket.recv(2048)
            if data:
                player_stats["active_stage"] = 1
                result = run_game(
                    screen, clock, player_stats, 
                    is_online=True, 
                    local_player_id=local_id, 
                    network_socket=net_socket
                )
                
                play_music("home.mp3", volume=0.45, loop=-1)
                
                if result == "MATCH_WON":
                    app_state = "WIN_SCREEN"
                elif result == "MATCH_LOST":
                    app_state = "LOSS_SCREEN"
                else:
                    app_state = "HOME"
        except BlockingIOError:
            pass
        except Exception:
            pass

        for event in events:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                if net_socket:
                    net_socket.close()
                app_state = "HOME"

    elif app_state == "LEVEL_SELECTION":
        action = level_select.update(events, screen, player_stats["unlocked_stage"])
        
        target_stage = None
        if action == "BACK_HOME":
            app_state = "HOME"
        elif action == "CONTINUE_CURRENT":
            target_stage = player_stats["unlocked_stage"]
        elif action and action.startswith("PLAY_LVL_"):
            target_stage = int(action.split("_")[-1])

        if target_stage is not None:
            player_stats["active_stage"] = target_stage
            result = run_game(screen, clock, player_stats, is_online=False)
            
            play_music("home.mp3", volume=0.45, loop=-1)
            
            if result == "MATCH_WON":
                if target_stage == player_stats["unlocked_stage"] and player_stats["unlocked_stage"] < 5:
                    player_stats["unlocked_stage"] += 1
                save_player_stats(player_stats)
                app_state = "WIN_SCREEN"
            elif result == "MATCH_LOST":
                app_state = "LOSS_SCREEN"
            elif result == "BACK_TO_MENU":
                app_state = "HOME"

    elif app_state == "WIN_SCREEN":
        action = menu.update(events, screen, mode="WIN", player_stats=player_stats)
        if action == "NEXT_LEVEL":
            current_stage = player_stats.get("active_stage", 1)
            if current_stage >= 5:
                app_state = "HOME"
            else:
                player_stats["active_stage"] = current_stage + 1
                result = run_game(screen, clock, player_stats, is_online=False)

                play_music("home.mp3", volume=0.45, loop=-1)

                if result == "MATCH_WON":
                    if player_stats["active_stage"] == player_stats["unlocked_stage"] and player_stats["unlocked_stage"] < 5:
                        player_stats["unlocked_stage"] += 1
                    save_player_stats(player_stats)
                    app_state = "WIN_SCREEN"
                elif result == "MATCH_LOST":
                    app_state = "LOSS_SCREEN"
                elif result == "BACK_TO_MENU":
                    app_state = "HOME"
        elif action == "HOME":
            app_state = "HOME"

    elif app_state == "LOSS_SCREEN":
        action = menu.update(events, screen, mode="LOSS", player_stats=player_stats)
        if action == "RETRY":
            result = run_game(screen, clock, player_stats, is_online=False)
            
            play_music("home.mp3", volume=0.45, loop=-1)
            
            if result == "MATCH_WON":
                if player_stats["active_stage"] == player_stats["unlocked_stage"] and player_stats["unlocked_stage"] < 5:
                    player_stats["unlocked_stage"] += 1
                save_player_stats(player_stats)
                app_state = "WIN_SCREEN"
            elif result == "MATCH_LOST":
                app_state = "LOSS_SCREEN"
            elif result == "BACK_TO_MENU":
                app_state = "HOME"
        elif action == "HOME":
            app_state = "HOME"

    pygame.display.update()

save_player_stats(player_stats)
pygame.quit()