import json
import os
import sys

def _resolve_token_path():
    """Resolve design_tokens.json for both dev and PyInstaller frozen builds."""
    try:
        base = sys._MEIPASS
    except AttributeError:
        base = os.path.abspath(os.path.dirname(__file__))
        return os.path.join(base, "design_tokens.json")
    return os.path.join(base, "ui", "theme", "design_tokens.json")

TOKEN_PATH = _resolve_token_path()

class DesignTokens:
    def __init__(self):
        with open(TOKEN_PATH, "r") as f:
            self.tokens = json.load(f)

    def get(self, *keys, default=None):
        # Flatten keys if they contain dots
        flat_keys = []
        for k in keys:
            if isinstance(k, str) and "." in k:
                flat_keys.extend(k.split("."))
            else:
                flat_keys.append(k)

        data = self.tokens
        for k in flat_keys:
            if isinstance(data, dict) and k in data:
                data = data[k]
            else:
                return default
        return data

TOKENS = DesignTokens()
