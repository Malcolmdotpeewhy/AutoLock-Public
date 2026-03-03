import unittest
import os
import sys
from unittest.mock import MagicMock, patch

# Mock dependencies




from services.asset_manager import AssetManager

class TestRoleIcons(unittest.TestCase):
    def setUp(self):
        self.am = AssetManager(log_func=lambda x: None)

    def test_role_icon_paths(self):
        roles = {
            "TOP": "top",
            "JUNGLE": "jungle",
            "MIDDLE": "middle",
            "BOTTOM": "bottom",
            "UTILITY": "utility",
            "FILL": "fill"
        }

        for role, name in roles.items():
            expected_fname = f"icon-position-{name}.png"

            # Mock os.path.exists to False to trigger download URL generation logic (if we want to test URL)
            # Or just test the path returned (which is empty string if not exists)
            # Wait, get_role_icon_path returns "" if not exists.
            # So I need to mock exists=True to get the path back?
            # Or I can inspect the arguments passed to _start_download.

            with patch("os.path.exists", return_value=False):
                with patch.object(self.am, "_start_download") as mock_download:
                    self.am.get_role_icon_path(role)

                    # We expect _start_download to be called with (url, path)
                    args, _ = mock_download.call_args
                    url, path = args

                    # Verify filename in path
                    self.assertTrue(path.endswith(expected_fname), f"Path {path} does not end with {expected_fname}")

                    # Verify URL matches CommunityDragon
                    expected_url = f"https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/position-icons/position-{name}.png"
                    self.assertEqual(url, expected_url)

if __name__ == "__main__":
    unittest.main()
