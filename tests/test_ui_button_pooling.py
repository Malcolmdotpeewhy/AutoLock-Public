import sys
import unittest
from unittest.mock import MagicMock, patch

# Provide a lightweight stub for ctk to prevent hangs
class Mockwidget:
    def __init__(self, *args, **kwargs):
        self.grid = MagicMock()
        self.grid_forget = MagicMock()
        self.winfo_width = MagicMock(return_value=1200)
        self.grid_columnconfigure = MagicMock()
        self.grid_rowconfigure = MagicMock()
        self.pack_propagate = MagicMock()
        self.after = MagicMock()
        self.bind = MagicMock()
        self.pack = MagicMock()
        self.configure = MagicMock()
        self.destroy = MagicMock()
        self.lift = MagicMock()
        self.winfo_children = MagicMock(return_value=[])
        self.place = MagicMock()

mock_ctk = MagicMock()
mock_ctk.CTk = Mockwidget
mock_ctk.CTkFrame = Mockwidget
mock_ctk.CTkLabel = Mockwidget
mock_ctk.CTkEntry = Mockwidget
mock_ctk.CTkButton = Mockwidget
mock_ctk.CTkScrollableFrame = Mockwidget
mock_ctk.CTkOptionMenu = Mockwidget
mock_ctk.StringVar = MagicMock()

sys.modules["customtkinter"] = mock_ctk
sys.modules["ctk"] = mock_ctk

class TestUIButtonPooling(unittest.TestCase):
    def setUp(self):
        self.mock_asset_manager = MagicMock()

        self.mock_asset_manager = MagicMock()
        self.mock_asset_manager.champ_data = {
            f"Champ{i}": {"key": str(i), "name": f"Champion {i}"}
            for i in range(20)
        }
        self.mock_asset_manager.get_champ_id.return_value = 1
        self.mock_asset_manager.get_champ_tags.return_value = []
        self.mock_asset_manager.get_champ_roles.return_value = ["TOP", "MIDDLE"]
        self.mock_asset_manager.get_icon.return_value = "fake_icon"
        self.mock_asset_manager.get_role_icon.return_value = "fake_role_icon"

        self.mock_parent = MagicMock()
        self.on_select = MagicMock()
        self.on_close = MagicMock()

    @patch("ui.layouts.auto.get_color", return_value="#000")
    @patch("ui.layouts.auto.get_font", return_value=("Arial", 12))
    @patch("ui.layouts.auto.parse_border", return_value=(1, "#000"))
    @patch("ui.layouts.auto.make_input")
    @patch("ui.layouts.auto.make_button")
    @patch("ui.layouts.auto.CTkTooltip")
    def test_button_reuse(self, mock_tooltip, mock_mb, mock_mi, mock_pb, mock_gf, mock_gc):
        import ui.layouts.auto
        
        # We must return a string from the search input so the list filter logic succeeds
        mock_mi.return_value.get.return_value = ""
        
        selector = ui.layouts.auto.ChampionSelector(self.mock_parent, self.mock_asset_manager, self.on_select, self.on_close)

        selector._load()
        initial_count = len(selector.btn_pool)
        # Should be exactly 22: 20 champs + None + Bravery
        self.assertGreater(initial_count, 20, "Should create initial buttons")

        selector._load()
        second_count = len(selector.btn_pool)
        diff = second_count - initial_count
        
        self.assertLess(diff, 5, f"Expected button reuse, but created {diff} new buttons!")

    @patch("ui.layouts.auto.get_color", return_value="#000")
    @patch("ui.layouts.auto.get_font", return_value=("Arial", 12))
    @patch("ui.layouts.auto.parse_border", return_value=(1, "#000"))
    @patch("ui.layouts.auto.make_input")
    @patch("ui.layouts.auto.make_button")
    @patch("ui.layouts.auto.CTkTooltip")
    def test_grid_forget(self, mock_tooltip, mock_mb, mock_mi, mock_pb, mock_gf, mock_gc):
        import ui.layouts.auto
        mock_mi.return_value.get.return_value = ""
        
        selector = ui.layouts.auto.ChampionSelector(self.mock_parent, self.mock_asset_manager, self.on_select, self.on_close)
        selector._load() 

        self.mock_asset_manager.champ_data = {"Champ1": {"key": "1", "name": "Champion 1"}}
        selector._load()

        forgotten = sum(1 for btn in selector.btn_pool if btn.grid_forget.called)
        self.assertGreater(forgotten, 0, "Expected grid_forget on unused buttons")

if __name__ == '__main__':
    unittest.main()
