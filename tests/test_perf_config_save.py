
import time
import os
import json
import shutil
from services.asset_manager import ConfigManager

# Mocking ConfigManager to avoid overwriting actual config file
TEST_CONFIG_FILE = "test_benchmark_config.json"

# We need to monkeypatch the CONFIG_FILE in services.asset_manager or just swap it temporarily if possible.
# Since it is a global variable in the module, we can patch it.

import services.asset_manager
services.asset_manager.CONFIG_FILE = TEST_CONFIG_FILE

def benchmark():
    # Setup
    if os.path.exists(TEST_CONFIG_FILE):
        os.remove(TEST_CONFIG_FILE)

    config = ConfigManager()

    # Initialize keys
    keys = [
        "auto_requeue",
        "auto_accept",
        "auto_set_roles",
        "auto_hover",
        "auto_runes",
        "auto_spells",
        "auto_aram_swap",
        "auto_honor",
    ]

    # Baseline: Update one by one (Old implementation behavior simulation)
    start_time = time.time()
    iterations = 100
    for _ in range(iterations):
        for k in keys:
            config.set(k, True, save=True)
    end_time = time.time()

    print(f"Baseline (100 iterations of 8 writes): {end_time - start_time:.4f} seconds")

    # Optimization: Update all then save once
    start_time = time.time()
    for _ in range(iterations):
        for k in keys:
            config.set(k, True, save=False)
        config.save()
    end_time = time.time()

    print(f"Optimized (100 iterations of 1 write): {end_time - start_time:.4f} seconds")

    # Cleanup
    if os.path.exists(TEST_CONFIG_FILE):
        os.remove(TEST_CONFIG_FILE)

if __name__ == "__main__":
    benchmark()
