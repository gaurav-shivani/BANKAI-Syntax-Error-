import os
import pygame

# Global cache for sounds
_SOUNDS = {}
_CURRENT_MUSIC = None
_SOUND_MUTED = False
_MUSIC_MUTED = False

SOUND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds")

def init_audio():
    """Initializes pygame mixer if not already initialized."""
    if not pygame.mixer.get_init():
        try:
            pygame.mixer.pre_init(44100, -16, 2, 1024)
            pygame.mixer.init()
            pygame.mixer.set_num_channels(16)
        except Exception as e:
            print(f"[AUDIO] Mixer init failed: {e}")

def get_sound(name):
    """Loads and caches a Sound object."""
    if name in _SOUNDS:
        return _SOUNDS[name]
    
    # Try direct path or in SOUND_DIR
    candidates = [
        name,
        os.path.join(SOUND_DIR, name),
        os.path.join(SOUND_DIR, "FX", name),
        os.path.join(SOUND_DIR, f"{name}.wav"),
        os.path.join(SOUND_DIR, f"{name}.ogg"),
        os.path.join(SOUND_DIR, f"{name}.mp3"),
        os.path.join(SOUND_DIR, "FX", f"{name}.wav"),
        os.path.join(SOUND_DIR, "FX", f"{name}.ogg"),
    ]
    
    for path in candidates:
        if os.path.exists(path):
            try:
                snd = pygame.mixer.Sound(path)
                _SOUNDS[name] = snd
                return snd
            except Exception as e:
                pass
    _SOUNDS[name] = None
    return None

def play_sound(name, volume=1.0):
    """Plays a sound effect by name or filename safely without throwing errors."""
    if _SOUND_MUTED:
        return None
    try:
        snd = get_sound(name)
        if snd:
            snd.set_volume(volume)
            return snd.play()
    except Exception as e:
        pass
    return None

def play_music(filename, volume=0.5, loop=-1):
    """Plays background music safely."""
    global _CURRENT_MUSIC
    if _MUSIC_MUTED:
        return
    
    candidates = [
        filename,
        os.path.join(SOUND_DIR, filename),
    ]
    for path in candidates:
        if os.path.exists(path):
            if _CURRENT_MUSIC == path and pygame.mixer.music.get_busy():
                return
            try:
                pygame.mixer.music.load(path)
                pygame.mixer.music.set_volume(volume)
                pygame.mixer.music.play(loop)
                _CURRENT_MUSIC = path
                return
            except Exception as e:
                print(f"[AUDIO] Failed to play music {filename}: {e}")

def stop_music():
    global _CURRENT_MUSIC
    try:
        pygame.mixer.music.stop()
        _CURRENT_MUSIC = None
    except Exception:
        pass

def fadeout_music(ms=500):
    global _CURRENT_MUSIC
    try:
        pygame.mixer.music.fadeout(ms)
        _CURRENT_MUSIC = None
    except Exception:
        pass
