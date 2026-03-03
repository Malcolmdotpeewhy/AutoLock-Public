import sys
import time
import unittest
from unittest.mock import MagicMock
import threading

# 1. Mock external dependencies






# 2. Import target
from services.automation import AutomationEngine
from services.api_handler import LCUClient
from services.asset_manager import AssetManager, ConfigManager

class BenchmarkAutomation(unittest.TestCase):
    def setUp(self):
        self.lcu = MagicMock()
        self.lcu.is_connected = True
        self.assets = MagicMock()
        self.config = MagicMock()
        # Fix: config.get should return the default value if key is missing, or a valid dict
        def mock_config_get(key, default=None):
            if key == "experimental_profile":
                return default or {}
            return None
        self.config.get.side_effect = mock_config_get

        # Disable logging to keep output clean
        self.auto = AutomationEngine(self.lcu, self.assets, self.config, log_func=lambda x: None)
        self.auto.last_phase = "None"

        # Mock time.sleep to avoid waiting
        self.sleep_mock = MagicMock()
        self.original_sleep = time.sleep
        time.sleep = self.sleep_mock

    def tearDown(self):
        time.sleep = self.original_sleep

    def test_steady_lobby(self):
        # Simulate 50ms network delay per request
        def mock_request(method, endpoint, data=None, silent=False):
            self.original_sleep(0.05)
            resp = MagicMock()
            resp.status_code = 200

            if endpoint == "/lol-gameflow/v1/gameflow-phase":
                resp.json.return_value = "Lobby"
            elif endpoint == "/lol-lobby/v2/lobby":
                resp.json.return_value = {"members": []}
            else:
                resp.json.return_value = {}
            return resp

        self.lcu.request.side_effect = mock_request
        self.auto.last_phase = "Lobby"

        start = time.time()
        self.auto._tick()
        end = time.time()

        duration = end - start
        print(f"Steady Lobby (Sequential): {duration:.4f}s")
        # Current implementation: Phase (50ms) + Lobby (50ms) = 100ms + overhead
        # If parallel: Max(50ms, 50ms) = 50ms + overhead

    def test_steady_none(self):
        def mock_request(method, endpoint, data=None, silent=False):
            self.original_sleep(0.05)
            resp = MagicMock()
            resp.status_code = 200

            if endpoint == "/lol-gameflow/v1/gameflow-phase":
                resp.json.return_value = "None"
            return resp

        self.lcu.request.side_effect = mock_request
        self.auto.last_phase = "None"

        start = time.time()
        self.auto._tick()
        end = time.time()

        duration = end - start
        print(f"Steady None: {duration:.4f}s")
        # Expect sequential: Phase (50ms) = 50ms

if __name__ == "__main__":
    unittest.main()
