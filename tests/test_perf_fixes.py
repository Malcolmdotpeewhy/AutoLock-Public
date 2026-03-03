"""
Tests for the three performance optimizations:
1. PID-cached process detection
2. Batched config writes (ConfigManager.set_batch)
3. Async image loading (AssetManager.get_icon_async)
"""
import json
import os
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch, call

# We avoid global sys.modules modification to prevent test pollution
# Instead we'll use patch.dict inside a decorators or tests, or 
# just let the actual modules load if possible, since customtkinter is
# often safe to import without a display in newer versions.
# For these specific tests, we don't need the UI stack at all.


# ===================================================================
# TEST 1 — PID-Cached Process Detection
# ===================================================================
class TestPIDCachedProcessDetection(unittest.TestCase):

    def setUp(self):
        self.psutil_patch = patch('core.main.psutil')
        self.mock_psutil = self.psutil_patch.start()

        self.mock_game_proc = MagicMock()
        self.mock_game_proc.info = {'name': 'League of Legends.exe'}
        self.mock_game_proc.pid = 12345
        self.mock_game_proc.is_running.return_value = True
        self.mock_game_proc.name.return_value = 'League of Legends.exe'

    def tearDown(self):
        self.psutil_patch.stop()

    def _make_app_mock(self):
        app = MagicMock()
        app.lcu = MagicMock()
        app.lcu.is_connected = False
        app.current_phase = None
        app._game_pid = None
        app._last_full_scan = 0  # Required for optimization logic
        return app

    def test_first_call_iterates_and_caches_pid(self):
        """First detection should iterate processes and cache the PID."""
        from core.main import LeagueAgentApp

        app = self._make_app_mock()
        self.mock_psutil.process_iter.return_value = [self.mock_game_proc]

        result = LeagueAgentApp._is_game_running(app)

        self.assertTrue(result)
        self.assertEqual(app._game_pid, 12345)
        self.mock_psutil.process_iter.assert_called_once()

    def test_second_call_uses_cached_pid(self):
        """Subsequent calls should use the cached PID and skip iteration."""
        from core.main import LeagueAgentApp

        app = self._make_app_mock()
        app._game_pid = 12345  # Already cached

        cached_proc = MagicMock()
        cached_proc.is_running.return_value = True
        cached_proc.name.return_value = 'League of Legends.exe'
        self.mock_psutil.Process.return_value = cached_proc

        result = LeagueAgentApp._is_game_running(app)

        self.assertTrue(result)
        # process_iter should NOT have been called
        self.mock_psutil.process_iter.assert_not_called()

    def test_stale_pid_falls_back_to_iteration(self):
        """When cached PID is stale, fall back to full iteration."""
        from core.main import LeagueAgentApp

        app = self._make_app_mock()
        app._game_pid = 99999  # Stale PID

        self.mock_psutil.Process.side_effect = self.mock_psutil.NoSuchProcess(99999)
        self.mock_psutil.process_iter.return_value = []  # Game not running

        result = LeagueAgentApp._is_game_running(app)

        self.assertFalse(result)
        self.assertIsNone(app._game_pid)
        self.mock_psutil.process_iter.assert_called_once()


# ===================================================================
# TEST 2 — Batched Config Writes
# ===================================================================
class TestBatchedConfigWrites(unittest.TestCase):

    def test_set_batch_writes_file_once(self):
        """set_batch should update all keys and write to disk exactly once."""
        from services.asset_manager import ConfigManager

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
            json.dump({}, tmp)
            tmp_path = tmp.name

        try:
            # Patch CONFIG_FILE to use our temp file
            with patch('services.asset_manager.CONFIG_FILE', tmp_path):
                cfg = ConfigManager.__new__(ConfigManager)
                cfg.cfg = {"a": 1, "b": 2}

                with patch('builtins.open', wraps=open) as mock_open:
                    cfg.set_batch({"a": 10, "b": 20, "c": 30})

                    # Should have been called once for writing
                    write_calls = [c for c in mock_open.call_args_list
                                   if 'w' in str(c)]
                    self.assertEqual(len(write_calls), 1,
                                     "set_batch should write to file exactly once")

                # Verify values were updated in memory
                self.assertEqual(cfg.cfg["a"], 10)
                self.assertEqual(cfg.cfg["b"], 20)
                self.assertEqual(cfg.cfg["c"], 30)
        finally:
            os.unlink(tmp_path)

    def test_set_calls_file_per_key(self):
        """Baseline: individual set() calls write N times."""
        from services.asset_manager import ConfigManager

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
            json.dump({}, tmp)
            tmp_path = tmp.name

        try:
            with patch('services.asset_manager.CONFIG_FILE', tmp_path):
                cfg = ConfigManager.__new__(ConfigManager)
                cfg.cfg = {}

                with patch('builtins.open', wraps=open) as mock_open:
                    cfg.set("a", 1)
                    cfg.set("b", 2)
                    cfg.set("c", 3)

                    write_calls = [c for c in mock_open.call_args_list
                                   if 'w' in str(c)]
                    self.assertEqual(len(write_calls), 3,
                                     "Individual set() should write once per call")
        finally:
            os.unlink(tmp_path)


# ===================================================================
# TEST 3 — Async Image Loading
# ===================================================================
class TestAsyncImageLoading(unittest.TestCase):

    def test_get_icon_async_cache_hit_no_worker(self):
        """When icon is already cached, callback fires immediately without worker."""
        from services.asset_manager import AssetManager

        mgr = AssetManager.__new__(AssetManager)
        mgr.icons = {"champion_Aatrox_50_False": MagicMock()}
        mgr._download_queue = MagicMock()

        results = []
        mgr.get_icon_async("champion", "Aatrox", lambda img: results.append(img),
                           size=(50, 50), grayscale=False)

        # Callback should have been called synchronously
        self.assertEqual(len(results), 1)
        self.assertIsNotNone(results[0])
        # Worker queue should NOT have been used
        mgr._download_queue.put.assert_not_called()

    def test_get_icon_async_cache_miss_queues_worker(self):
        """When icon is not cached, a worker should be queued."""
        from services.asset_manager import AssetManager

        mgr = AssetManager.__new__(AssetManager)
        mgr.icons = {}
        mgr._download_queue = MagicMock()

        mgr.get_icon_async("champion", "Aatrox", lambda img: None,
                           size=(50, 50), grayscale=False)

        # Worker should have been queued
        mgr._download_queue.put.assert_called_once()


if __name__ == '__main__':
    unittest.main()
