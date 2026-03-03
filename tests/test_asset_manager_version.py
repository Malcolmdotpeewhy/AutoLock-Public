
import unittest
import os
import shutil
from unittest.mock import MagicMock, patch
import customtkinter as ctk

# Mocking customtkinter before importing asset_manager because it requires display
ctk.CTkImage = MagicMock()
ctk.CTkButton = MagicMock()
ctk.CTkFrame = MagicMock()
ctk.CTkLabel = MagicMock()
ctk.CTkEntry = MagicMock()
ctk.CTkScrollableFrame = MagicMock()

import services.asset_manager as asset_manager

class TestAssetManagerVersionUpdate(unittest.TestCase):
    def setUp(self):
        # Create a temporary cache directory
        self.test_cache_dir = "test_cache"
        if os.path.exists(self.test_cache_dir):
            shutil.rmtree(self.test_cache_dir)
        os.makedirs(self.test_cache_dir)

        # Override CACHE_DIR and ASSETS_DIR in asset_manager
        self.original_cache_dir = asset_manager.CACHE_DIR
        self.original_assets_dir = asset_manager.ASSETS_DIR
        self.original_ddragon_ver = asset_manager.DDRAGON_VER
        asset_manager.CACHE_DIR = self.test_cache_dir
        asset_manager.ASSETS_DIR = os.path.join(self.test_cache_dir, "assets")
        asset_manager.DDRAGON_VER = "14.1.1"
        if not os.path.exists(asset_manager.ASSETS_DIR):
            os.makedirs(asset_manager.ASSETS_DIR)

    def tearDown(self):
        # Restore directories
        asset_manager.CACHE_DIR = self.original_cache_dir
        asset_manager.ASSETS_DIR = self.original_assets_dir
        asset_manager.DDRAGON_VER = self.original_ddragon_ver
        if os.path.exists(self.test_cache_dir):
            shutil.rmtree(self.test_cache_dir)

    @patch('services.asset_manager.requests.Session')
    def test_fetch_latest_version_success(self, mock_session_cls):
        # Setup mock session
        mock_session = mock_session_cls.return_value

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = ["14.5.1", "14.4.1"]
        mock_session.get.return_value = mock_response

        # Initialize AssetManager
        manager = asset_manager.AssetManager()
        # By default it starts with hardcoded version or cached version.
        # Since cache is empty, it starts with 14.1.1 (DDRAGON_VER)
        self.assertEqual(manager.ddragon_ver, "14.1.1")

        # Call _fetch_latest_version directly
        manager._fetch_latest_version()

        # Check if version updated
        self.assertEqual(manager.ddragon_ver, "14.5.1")

        # Check if version.txt is written
        v_path = os.path.join(self.test_cache_dir, "version.txt")
        self.assertTrue(os.path.exists(v_path))
        with open(v_path, "r") as f:
            self.assertEqual(f.read().strip(), "14.5.1")

    @patch('services.asset_manager.requests.Session')
    def test_fetch_latest_version_clears_cache(self, mock_session_cls):
        # Setup mock session
        mock_session = mock_session_cls.return_value

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = ["14.5.1"]
        mock_session.get.return_value = mock_response

        # Create dummy cache files
        cache_files = ["champion.json", "item.json", "summoner.json", "runesReforged.json"]
        for f in cache_files:
            with open(os.path.join(self.test_cache_dir, f), "w") as file:
                file.write("{}")

        # Initialize AssetManager
        manager = asset_manager.AssetManager()
        # Default is 14.1.1
        self.assertEqual(manager.ddragon_ver, "14.1.1")

        # Call update
        manager._fetch_latest_version()

        # Verify updated version
        self.assertEqual(manager.ddragon_ver, "14.5.1")

        # Verify cache files are deleted
        for f in cache_files:
            path = os.path.join(self.test_cache_dir, f)
            self.assertFalse(os.path.exists(path), f"File {f} should have been deleted")

    @patch('services.asset_manager.requests.Session')
    def test_fetch_latest_version_failure(self, mock_session_cls):
        # Setup mock to raise exception
        mock_session = mock_session_cls.return_value
        mock_session.get.side_effect = Exception("Network error")

        # Initialize AssetManager
        manager = asset_manager.AssetManager()
        self.assertEqual(manager.ddragon_ver, "14.1.1")

        # Call _fetch_latest_version
        manager._fetch_latest_version()

        # Check version remains unchanged
        self.assertEqual(manager.ddragon_ver, "14.1.1")

        # Check version.txt is NOT created (since it didn't exist)
        v_path = os.path.join(self.test_cache_dir, "version.txt")
        self.assertFalse(os.path.exists(v_path))

    def test_init_loads_cached_version(self):
        # Create a version file
        v_path = os.path.join(self.test_cache_dir, "version.txt")
        with open(v_path, "w") as f:
            f.write("13.24.1")

        # Initialize AssetManager
        manager = asset_manager.AssetManager()

        # Check if it loaded the version
        self.assertEqual(manager.ddragon_ver, "13.24.1")

if __name__ == '__main__':
    unittest.main()
