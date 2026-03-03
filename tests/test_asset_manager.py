
import unittest
import time
from unittest.mock import MagicMock
import json

# Mock external dependencies before importing
import sys




# Import AssetManager (it will use the mocked modules)
from services.asset_manager import AssetManager

class TestAssetManagerPerf(unittest.TestCase):
    def setUp(self):
        self.asset_manager = AssetManager(log_func=lambda x: None)
        # Mock champ_data with dummy data
        self.asset_manager.champ_data = {}

        # Manually init maps as we are bypassing _load_champion_data
        self.asset_manager.id_to_key = {}
        self.asset_manager.name_to_id = {}

        for i in range(200):
            key_str = str(i)
            name = f"Champ_{i}"
            # Structure matches DDragon: key is ID/Name, value has info
            self.asset_manager.champ_data[name] = {
                "id": name,
                "key": key_str,
                "name": f"Display {name}",
                "tags": ["Fighter"]
            }
            # Populate maps mimicking _load_champion_data logic
            self.asset_manager.id_to_key[i] = name
            self.asset_manager.id_to_tags[i] = ["Fighter"]
            self.asset_manager.name_to_id[name.lower()] = i
            self.asset_manager.name_to_id[f"display {name}".lower()] = i

    def test_lookup_correctness(self):
        # Test get_champ_tags
        tags = self.asset_manager.get_champ_tags(10)
        self.assertEqual(tags, ["Fighter"])
        # Test get_champ_name
        # ID 10 -> "Champ_10"
        name = self.asset_manager.get_champ_name(10)
        self.assertEqual(name, "Champ_10")

        # Test get_champ_id
        # Name "Champ_20" -> 20
        cid = self.asset_manager.get_champ_id("Champ_20")
        self.assertEqual(cid, 20)

        # Test get_champ_id case insensitive
        cid = self.asset_manager.get_champ_id("champ_30")
        self.assertEqual(cid, 30)

        # Test get_champ_id by display name
        cid = self.asset_manager.get_champ_id("Display Champ_40")
        self.assertEqual(cid, 40)

    def test_perf_get_champ_name(self):
        start = time.time()
        for _ in range(1000):
            self.asset_manager.get_champ_name(50)
        end = time.time()
        print(f"get_champ_name 1000 iter: {end - start:.6f}s")

    def test_perf_get_champ_id(self):
        start = time.time()
        for _ in range(1000):
            self.asset_manager.get_champ_id("Champ_50")
        end = time.time()
        print(f"get_champ_id 1000 iter: {end - start:.6f}s")

if __name__ == "__main__":
    unittest.main()
