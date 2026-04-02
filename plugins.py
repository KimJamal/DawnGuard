import os
import importlib.util

SOUND_PLUGINS = {}

def load_sound_plugins():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_dir = os.path.join(base_dir, "sound_plugins")
    if not os.path.exists(plugin_dir):
        os.makedirs(plugin_dir, exist_ok=True)
        with open(os.path.join(plugin_dir, "example_plugin.py"), "w") as f:
            f.write("""def play(sound_path, volume=80, fade_in=True):
    print(f"[Plugin] Playing {sound_path} at {volume}%")
""")
    for file in os.listdir(plugin_dir):
        if file.endswith(".py"):
            name = file[:-3]
            spec = importlib.util.spec_from_file_location(name, os.path.join(plugin_dir, file))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, "play"):
                SOUND_PLUGINS[name] = module.play
    print(f"Loaded {len(SOUND_PLUGINS)} sound plugins")

def get_sound_player(sound_path=None):
    return SOUND_PLUGINS.get("example_plugin", None)
