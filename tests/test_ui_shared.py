
import sys
from unittest.mock import MagicMock

# Mock dependencies




import unittest
# Now import ui_shared
from ui.components.color_utils import interpolate_color

class TestUIShared(unittest.TestCase):
    def test_interpolate_color(self):
        # Black to White 50%
        c = interpolate_color("#000000", "#ffffff", 0.5)
        # 0 + (255-0)*0.5 = 127 -> 7f
        self.assertEqual(c, "#7f7f7f")

        # Red to Green 0%
        c = interpolate_color("#ff0000", "#00ff00", 0.0)
        self.assertEqual(c, "#ff0000")

        # Red to Green 100%
        c = interpolate_color("#ff0000", "#00ff00", 1.0)
        self.assertEqual(c, "#00ff00")

        # Invalid input (should return first color)
        c = interpolate_color("invalid", "#ffffff", 0.5)
        self.assertEqual(c, "invalid")

if __name__ == "__main__":
    unittest.main()
