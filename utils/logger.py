"""
Logger Module
Handles application logging to file and console.
"""
import threading
from datetime import datetime


class Logger:
    """Singleton Logger class."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(Logger, cls).__new__(cls)
                cls._instance.init_logger()
        return cls._instance

    def init_logger(self):
        """Initialize the logger."""
        # pylint: disable=attribute-defined-outside-init
        self.filename = "debug.log"
        # Reset log file on startup
        with open(self.filename, "w", encoding="utf-8") as f:
            f.write(f"=== ZERO-G AGENT LOG STARTED AT {datetime.now()} ===\n")

        self.logger_lock = threading.Lock()

    def log(self, tag, message):
        """Log a message with a tag."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        thread_name = threading.current_thread().name
        entry = f"[{timestamp}] [{thread_name}] [{tag}] {message}\n"

        # Print to console (optional)
        print(f"[{tag}] {message}")

        # Write to file
        with self.logger_lock:
            try:
                with open(self.filename, "a", encoding="utf-8") as f:
                    f.write(entry)
            except Exception:  # pylint: disable=broad-exception-caught
                pass

    @staticmethod
    def debug(tag, msg):
        """Log a debug message."""
        Logger().log(tag, msg)

    @staticmethod
    def error(tag, msg):
        """Log an error message."""
        Logger().log(f"ERROR:{tag}", msg)
