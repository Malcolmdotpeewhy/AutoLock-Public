import unittest
import unittest.mock
import time
import sys
from services.api_handler import LCUClient

class TestLCUClientInit(unittest.TestCase):
    def test_init_does_not_connect(self):
        """Test that LCUClient.__init__ does not call connect()."""
        with unittest.mock.patch('services.api_handler.LCUClient.connect') as mock_connect:
            lcu = LCUClient()
            mock_connect.assert_not_called()
            self.assertFalse(lcu.is_connected)

    def test_init_is_fast(self):
        """Test that LCUClient instantiation is fast even if process scan is slow."""
        # Mock psutil to be slow if connect() were called
        def slow_process_iter(*args, **kwargs):
            time.sleep(1.0)
            return []

        with unittest.mock.patch('psutil.process_iter', side_effect=slow_process_iter):
            start = time.time()
            lcu = LCUClient()
            duration = time.time() - start
            self.assertLess(duration, 0.1, "LCUClient instantiation took too long")

if __name__ == '__main__':
    unittest.main()
