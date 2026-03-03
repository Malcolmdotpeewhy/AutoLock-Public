import sys
import unittest
from unittest.mock import MagicMock, patch
import importlib

# Provide a lightweight stub for ctk to prevent hangs and allow real method execution
class Mockwidget:
    def __init__(self, *args, **kwargs):
        self.grid_forget = MagicMock()
        
    def grid(self, *args, **kwargs): pass
    def grid_columnconfigure(self, *args, **kwargs): pass
    def grid_rowconfigure(self, *args, **kwargs): pass
    def pack(self, *args, **kwargs): pass
    def pack_forget(self, *args, **kwargs): pass
    def configure(self, *args, **kwargs): pass
    def destroy(self, *args, **kwargs): pass
    def winfo_width(self): return 1200
    def pack_propagate(self, *args, **kwargs): pass
    def winfo_children(self): return []
    def lift(self): pass
    def bind(self, *args, **kwargs): pass
    def place(self, *args, **kwargs): pass

    def __getattr__(self, name):
        mock = MagicMock()
        setattr(self, name, mock)
        return mock

mock_ctk = MagicMock()
mock_ctk.CTk = Mockwidget
mock_ctk.CTkFrame = Mockwidget
mock_ctk.CTkLabel = Mockwidget
mock_ctk.CTkEntry = Mockwidget
mock_ctk.CTkButton = Mockwidget
mock_ctk.CTkScrollableFrame = Mockwidget
mock_ctk.CTkOptionMenu = Mockwidget
mock_ctk.StringVar = MagicMock()
mock_ctk.BooleanVar = MagicMock()
mock_ctk.CTkSwitch = Mockwidget
mock_ctk.CTkComboBox = Mockwidget

sys.modules["customtkinter"] = mock_ctk
sys.modules["ctk"] = mock_ctk

class TestUICaching(unittest.TestCase):
    def setUp(self):
        self.lcu = MagicMock()
        self.mock_asset_manager = MagicMock()
        self.mock_asset_manager.champ_data = {
            "Aatrox": {"key": "266", "name": "Aatrox"},
            "Ahri": {"key": "103", "name": "Ahri"}
        }
        self.mock_asset_manager.get_champ_id.return_value = 1
        self.mock_asset_manager.get_champ_tags.return_value = []
        self.mock_asset_manager.get_icon.return_value = MagicMock()

        self.mock_config = MagicMock()
        def config_get(key, default=None):
            if key == 'accept_delay': return 2.0
            if key == 'polling_rate_champ_select': return 0.5
            if key == 'lock_in_delay': return 5
            return default
        self.mock_config.get.side_effect = config_get

        self.mock_lcu = MagicMock()
        self.mock_parent = MagicMock()

    @patch("ui.layouts.auto.make_panel", MagicMock(return_value=Mockwidget()))
    @patch("ui.layouts.auto.make_button", MagicMock())
    def test_champion_selector_reuse(self):
        import ui.layouts.auto
        from ui.layouts.auto import MainDashboard
        from ui.layouts.auto import ChampionSelector
        
        dashboard = MainDashboard(self.mock_parent, self.mock_asset_manager, self.mock_config, self.mock_lcu)

        # 1. Open first time
        btn1 = MagicMock()
        dashboard.open_selector_for_slot("pick_TOP_1", btn1, 50)

        selector_1 = dashboard.selector
        self.assertIsNotNone(selector_1, "Selector should be created")

        callback_1 = getattr(selector_1, 'on_select', None)

        # 2. Close selector
        dashboard.close_selector()

        # 3. Open second time
        btn2 = MagicMock()
        dashboard.open_selector_for_slot("pick_TOP_2", btn2, 50)

        selector_2 = dashboard.selector

        # We assert they are the same instance to enforce the fix
        self.assertIs(selector_1, selector_2, "ChampionSelector instance should be reused")

        # Verify callbacks updated
        callback_2 = getattr(selector_2, 'on_select', None)
        self.assertNotEqual(callback_1, callback_2, "Callbacks should be updated on reuse")

if __name__ == '__main__':
    unittest.main()
