import os
import subprocess
import sys

def build():
    # Define paths
    project_dir = os.path.dirname(os.path.abspath(__file__))
    main_script = os.path.join(project_dir, "main.py")
    icon_path = os.path.join(project_dir, "assets", "DawnGuardIco.ico")
    
    # PyInstaller command
    # --onefile: Bundle everything into a single .exe
    # --noconsole: Don't show a command prompt when running the app
    # --icon: Use the custom icon
    # --add-data: Include assets and sound_plugins folders
    # Note: On Windows, the separator for --add-data is ';'
    
    cmd = [
        "pyinstaller",
        "--onefile",
        "--noconsole",
        f"--icon={icon_path}",
        f"--add-data=assets;assets",
        f"--add-data=sound_plugins;sound_plugins",
        "--name=DawnGuard",
        main_script
    ]
    
    print(f"Running command: {' '.join(cmd)}")
    
    try:
        subprocess.check_call(cmd, cwd=project_dir)
        print("\nBuild successful! Your .exe is in the 'dist' folder.")
    except subprocess.CalledProcessError as e:
        print(f"\nBuild failed with error: {e}")

if __name__ == "__main__":
    build()
