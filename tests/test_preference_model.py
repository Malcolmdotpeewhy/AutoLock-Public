import unittest
import time
import os
import json
import tempfile
from unittest.mock import MagicMock, patch
from services.preference_model import PreferenceModel, PICK_WEIGHT, BENCH_WEIGHT

class TestPreferenceModel(unittest.TestCase):
    def setUp(self):
        self.mock_config = MagicMock()
        self.mock_config.get.return_value = {}
        
        self.mock_assets = MagicMock()
        # Mock champ mapping: ID -> Key
        self.mock_assets.id_to_key = {
            1: "Annie",
            2: "Olaf",
            3: "Galio",
            4: "TwistedFate"
        }
        
        self.model = PreferenceModel(self.mock_config, self.mock_assets)

    def test_initialization(self):
        self.assertTrue(self.model.state["enabled"])
        self.assertEqual(self.model.state["matches_tracked"], 0)
        self.assertEqual(len(self.model.state["champions"]), 0)

    def test_single_match_update(self):
        # Pick Annie (1), Bench Olaf (2) and Galio (3)
        self.model.update_after_match(1, [2, 3])
        
        self.assertEqual(self.model.state["matches_tracked"], 1)
        
        annie = self.model.get_champion_data("Annie")
        olaf = self.model.get_champion_data("Olaf")
        galio = self.model.get_champion_data("Galio")
        tf = self.model.get_champion_data("TwistedFate") # never seen
        
        self.assertEqual(annie["picked_count"], 1)
        self.assertEqual(annie["bench_seen_count"], 0)
        self.assertGreater(annie["score"], 0) # Positive score for being picked
        
        self.assertEqual(olaf["picked_count"], 0)
        self.assertEqual(olaf["bench_seen_count"], 1)
        self.assertLess(olaf["score"], 0) # Negative score for being benched
        
        self.assertEqual(tf["score"], 0) # Never seen = neutral 0

    def test_sorting_and_ranking(self):
        # Match 1: Pick Annie, Bench Olaf
        self.model.update_after_match(1, [2])
        
        # Match 2: Pick TwistedFate, Bench Olaf
        self.model.update_after_match(4, [2])
        
        # Match 3: Pick Annie, Bench TwistedFate
        self.model.update_after_match(1, [4])
        
        ranked = self.model.get_ranked_list()
        
        # Annie = 2 Picks
        # TF = 1 Pick, 1 Bench
        # Olaf = 0 Picks, 2 Bench
        
        self.assertEqual(len(ranked), 3)
        self.assertEqual(ranked[0]["champion"], "Annie")
        self.assertEqual(ranked[1]["champion"], "TwistedFate")
        self.assertEqual(ranked[2]["champion"], "Olaf")

    def test_decay_logic(self):
        self.model.update_after_match(1, [])
        initial_score = self.model.get_champion_data("Annie")["score"]
        
        # Fast forward time by 200 hours to force decay and lose recency
        future_time = time.time() + (200 * 3600)
        self.model.recalculate_scores(time_now=future_time)
        
        decayed_score = self.model.get_champion_data("Annie")["score"]
        
        self.assertLess(decayed_score, initial_score)

    def test_import_data_success(self):
        valid_data = {
            "enabled": True,
            "matches_tracked": 10,
            "champions": {
                "LeeSin": {"score": 10.5}
            }
        }
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
            json.dump(valid_data, f)
            temp_path = f.name

        try:
            result = self.model.import_data(temp_path)
            self.assertTrue(result)
            self.assertEqual(self.model.state["matches_tracked"], 10)
            self.assertIn("LeeSin", self.model.state["champions"])
            self.mock_config.set.assert_called_with("experimental_profile", self.model.state)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_import_data_invalid_content(self):
        invalid_data = {"wrong_key": "data"}
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
            json.dump(invalid_data, f)
            temp_path = f.name

        initial_state = self.model.state.copy()
        try:
            result = self.model.import_data(temp_path)
            self.assertFalse(result)
            self.assertEqual(self.model.state, initial_state)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_import_data_file_not_found(self):
        result = self.model.import_data("non_existent_file.json")
        self.assertFalse(result)

    def test_import_data_json_decode_error(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
            f.write("invalid json content")
            temp_path = f.name

        try:
            result = self.model.import_data(temp_path)
            self.assertFalse(result)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_export_data_success(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
            temp_path = f.name

        try:
            result = self.model.export_data(temp_path)
            self.assertTrue(result)
            with open(temp_path, 'r', encoding='utf-8') as f:
                exported_data = json.load(f)
            self.assertEqual(exported_data, self.model.state)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_export_data_error(self):
        with patch("builtins.open", side_effect=OSError("Access Denied")):
            result = self.model.export_data("some_path.json")
            self.assertFalse(result)

if __name__ == '__main__':
    unittest.main()
