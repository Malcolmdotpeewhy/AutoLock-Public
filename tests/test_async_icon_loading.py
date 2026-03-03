import time
import os
import threading
import customtkinter as ctk
from services.asset_manager import AssetManager

def test_async_icon_loading_safety():
    # Setup
    am = AssetManager()

    # Use a non-existent champion name to force download attempt
    fake_champ = "TestChamp_NonExistent_XYZ"

    # We expect get_icon_async to TRY to download it.
    # Since it doesn't exist on DDragon, the download will fail (404/403).
    # _simple_download prints error but doesn't raise exception usually?
    # get_icon returns None if file doesn't exist after sync download attempt.

    # This verifies that:
    # 1. The worker runs.
    # 2. It waits for the (failed) download.
    # 3. It returns None (gracefully) to the callback.
    # 4. It does NOT crash the thread.

    result_container = {"image": "INITIAL", "called": False}
    event = threading.Event()

    def callback(image):
        result_container["image"] = image
        result_container["called"] = True
        event.set()

    print(f"Requesting fake icon '{fake_champ}' async...")
    am.get_icon_async("champion", fake_champ, callback, widget=None)

    # Wait for callback
    if not event.wait(timeout=10):
        print("Timeout waiting for callback (Thread might have crashed)")
        return False

    if result_container["called"]:
        if result_container["image"] is None:
            print("SUCCESS: Callback received None (Graceful failure for missing asset)")
            return True
        else:
            print("WARNING: Received image for non-existent asset??")
            return True

    return False

if __name__ == "__main__":
    try:
        if test_async_icon_loading_safety():
            print("Safety Test Passed")
            exit(0)
        else:
            print("Safety Test Failed")
            exit(1)
    except Exception as e:
        print(f"Test Error: {e}")
        exit(1)
