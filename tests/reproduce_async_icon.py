import time
import os
import threading
import customtkinter as ctk
from services.asset_manager import AssetManager

def test_async_icon_loading():
    # Setup
    am = AssetManager()

    # Pick a dummy champion name that definitely needs downloading
    # or delete a known one.
    # Let's use "Aatrox" and delete it first to be sure.

    # We need to know where assets are.
    # AssetManager uses ~/Documents/LoLcache/assets
    # But we can't easily mock the path without subclassing.
    # Let's just use a real asset that is likely cached, delete it, then try.

    # Better: Use a fake name and mock _start_download?
    # But we want to test the REAL logic including download.
    # Let's use a real champion "Aatrox".

    cache_dir = os.path.join(os.path.expanduser("~"), "Documents", "LoLcache", "assets")
    aatrox_path = os.path.join(cache_dir, "champion_Aatrox.png")

    if os.path.exists(aatrox_path):
        os.remove(aatrox_path)
        print(f"Deleted {aatrox_path}")

    # Define callback
    result_container = {"image": None, "called": False}
    event = threading.Event()

    def callback(image):
        result_container["image"] = image
        result_container["called"] = True
        event.set()

    print("Requesting icon async...")
    # This should trigger download.
    # In current code: it queues download and calls callback(None) immediately (inside worker).
    # We want to see if it returns None.

    # We need to mock 'widget' to None so it calls callback directly from thread
    am.get_icon_async("champion", "Aatrox", callback, widget=None)

    # Wait for callback
    if not event.wait(timeout=10):
        print("Timeout waiting for callback")
        return False

    if result_container["image"] is None:
        print("FAILURE: Callback received None (Icon not loaded yet)")
        return False
    else:
        print("SUCCESS: Callback received Image")
        return True

if __name__ == "__main__":
    # Initialize CTk for CTkImage to work (requires root usually? No, CTkImage is wrapper)
    # But CTkImage might require a running app context for scaling?
    # CustomTkinter usually requires a root window for some things.
    # Let's try without first.
    try:
        if test_async_icon_loading():
            print("Test Passed")
            exit(0)
        else:
            print("Test Failed")
            exit(1)
    except Exception as e:
        print(f"Test Error: {e}")
        exit(1)
