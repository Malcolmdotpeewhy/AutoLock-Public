import os
import shutil
import PyInstaller.__main__

# Ensure we are in project root
if os.path.basename(os.getcwd()) == "scripts":
    os.chdir("..")

# Clean up previous builds
if os.path.exists("build"):
    shutil.rmtree("build")
if os.path.exists("dist"):
    shutil.rmtree("dist")

print("Starting Build Process...")

# Define paths relative to root
script_path = os.path.join("core", "main.py")
icon_path = os.path.join("assets", "app.ico")

PyInstaller.__main__.run(
    [
        script_path,
        "--name=LeagueAgent",
        "--onefile",
        "--windowed",
        "--uac-admin",
        f"--icon={icon_path}",
        "--add-data=assets;assets",
        "--add-data=config.json;.",
        "--add-data=rune_pages.json;.",
        "--collect-all=customtkinter",
        "--clean",
        "--log-level=INFO",
    ]
)

print("Build Complete. Executable is in /dist folder.")
