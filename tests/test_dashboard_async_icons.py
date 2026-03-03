import unittest
from unittest.mock import MagicMock, patch
import sys
import os

sys.path.append(os.getcwd())

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

class TestDashboardIconUpdate(unittest.TestCase):
    def test_repro(self):
        # Mocks
        sys.modules['customtkinter'] = mock_ctk
        sys.modules['ctk'] = mock_ctk

        # IMPORTANT: Reload to get the patched code
        if 'ui.layouts.auto' in sys.modules:
            del sys.modules['ui.layouts.auto']

        from ui.layouts.auto import MainDashboard

        am = MagicMock()
        am.get_icon.return_value = None  # Force missing icon
        # am.champ_data IS accessed in _create_simple_slot to get the name
        am.champ_data = {"Ahri": {"name": "Ahri"}}

        cfg = MagicMock()
        def config_get(key, default=None):
            if key == 'accept_delay': return 2.0
            if key == 'polling_rate_champ_select': return 0.5
            if key == 'lock_in_delay': return 5
            if key == 'pick_test': return 'Ahri'
            return default
        cfg.get.side_effect = config_get

        dash = MainDashboard(MagicMock(), am, cfg, MagicMock())

        # Invoke slot creation
        frame = MagicMock()

        # Reset mock before call
        am.get_icon.reset_mock()
        am.get_icon_async.reset_mock()

        dash._create_simple_slot(frame, "pick_test", size=50)

        # Verify async trigger
        if not am.get_icon_async.called:
            self.fail("get_icon_async should be called when get_icon returns None")

        # Verify call arguments
        # args[0] = category ('champion')
        # args[1] = name ('Ahri')
        # args[2] = callback function
        args, kwargs = am.get_icon_async.call_args
        self.assertEqual(args[0], "champion")
        self.assertEqual(args[1], "Ahri")

if __name__ == '__main__':
    unittest.main()
