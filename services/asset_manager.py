import concurrent.futures
import json
import os
import threading
import queue
from typing import Any, Dict, Optional

import customtkinter as ctk
import requests
from PIL import Image

# Constants
CONFIG_FILE = "config.json"
_DOCUMENTS = os.path.join(os.path.expanduser("~"), "Documents")
CACHE_DIR = os.path.join(_DOCUMENTS, "LoLcache")
ASSETS_DIR = os.path.join(CACHE_DIR, "assets")

# Ensure cache directories exist
os.makedirs(ASSETS_DIR, exist_ok=True)

DEFAULT_CONFIG = {
    "auto_accept": False,
    "auto_requeue": False,
    "auto_pick": "",  # Legacy/Global Fallback
    "auto_pick_backup": "",
    "auto_ban": "",
    "custom_status": "Using AutoLock",
    "auto_aram_swap": False,
    "auto_set_roles": False,
    "auto_hover": False,
    "auto_lock_in": False,
    "auto_random_skin": False,
    "auto_spells": True,
    "accept_delay": 2.0,
    "polling_rate_champ_select": 0.5,  # Default to Fast for CS
    # Role-Based Picks (3 slots per role)
    "pick_TOP_1": "",
    "pick_TOP_2": "",
    "pick_TOP_3": "",
    "pick_JUNGLE_1": "",
    "pick_JUNGLE_2": "",
    "pick_JUNGLE_3": "",
    "pick_MIDDLE_1": "",
    "pick_MIDDLE_2": "",
    "pick_MIDDLE_3": "",
    "pick_BOTTOM_1": "",
    "pick_BOTTOM_2": "",
    "pick_BOTTOM_3": "",
    "pick_UTILITY_1": "",
    "pick_UTILITY_2": "",
    "pick_UTILITY_3": "",
    # Role-Based Bans
    "ban_TOP": "",
    "ban_JUNGLE": "",
    "ban_MIDDLE": "",
    "ban_BOTTOM": "",
    "ban_UTILITY": "",
    "always_on_top": True,
}


def get_ddragon_version():
    """Return the current Data Dragon version."""
    try:
        import requests
        r = requests.get("https://ddragon.leagueoflegends.com/api/versions.json", timeout=2)
        if r.status_code == 200:
            return r.json()[0]
    except Exception:
        pass
    return "14.1.1"


DDRAGON_VER = get_ddragon_version()


class ConfigManager:
    """Manages application configuration."""

    def __init__(self):
        self.cfg = DEFAULT_CONFIG.copy()
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    self.cfg.update(json.load(f))
            except Exception:  # pylint: disable=broad-exception-caught
                pass

    def get(self, key, default=None):
        """Get a configuration value."""
        return self.cfg.get(key, default)

    def set(self, key, val, save=True):
        """Set a configuration value and optionally save to file."""
        self.cfg[key] = val
        if save:
            self.save()


    def save(self):
        """Save configuration to file."""
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.cfg, f, indent=4)

    def set_batch(self, updates: dict):
        """Update multiple keys in memory, then persist once."""
        self.cfg.update(updates)
        self.save()


from concurrent.futures import ThreadPoolExecutor

class AssetManager:
    """Manages application assets (images, data)."""

    def __init__(self, log_func=None):
        self._log_func = log_func
        # Create dir if not exists
        if not os.path.exists(ASSETS_DIR):
            try:
                os.makedirs(ASSETS_DIR)
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        self.champ_data: Dict[str, Any] = {}
        self.id_to_key: Dict[int, str] = {}  # ID (int) -> Key/DDragonID (str)
        self.id_to_tags: Dict[int, list] = {}  # ID (int) -> List[Tags]
        self.name_to_id: Dict[str, int] = {}  # Name/Key (lower) -> ID (int)
        self.champ_roles: Dict[int, list] = {}  # ID -> List[Positions]
        self.spell_data: Dict[int, str] = {}
        self.icons: Dict[str, ctk.CTkImage] = {}

        self._pending_downloads = set()
        self._lock = threading.Lock()

        # Bolt: Use a Queue + Daemon Threads to prevent thread explosion during high load
        # (e.g., skin selector) while ensuring clean app exit.
        self._download_queue = queue.Queue()
        for _ in range(5):
            threading.Thread(target=self._download_worker, daemon=True).start()

        self.session = requests.Session()

        # Initialize version from cache if available, otherwise use default
        self.ddragon_ver = DDRAGON_VER
        v_path = os.path.join(CACHE_DIR, "version.txt")
        if os.path.exists(v_path):
            try:
                with open(v_path, "r", encoding="utf-8") as f:
                    self.ddragon_ver = f.read().strip()
            except Exception:
                pass

    def _download_worker(self):
        """Worker thread for background downloads."""
        while True:
            func = self._download_queue.get()
            try:
                func()
            except Exception:  # pylint: disable=broad-exception-caught
                pass
            finally:
                self._download_queue.task_done()

    def log(self, msg):
        """Safe logging method that handles None log function."""
        if self._log_func:
            self._log_func(msg)
        else:
            print(f"[Assets] {msg}")

    def start_loading(self):
        """Start loading assets in a background thread."""
        threading.Thread(target=self._load_all, daemon=True).start()

    def _fetch_latest_version(self):
        """Fetches the latest Data Dragon version."""
        try:
            url = "https://ddragon.leagueoflegends.com/api/versions.json"
            response = self.session.get(url, timeout=5)
            if response.status_code == 200:
                versions = response.json()
                if versions and isinstance(versions, list):
                    latest = versions[0]
                    if latest != self.ddragon_ver:
                        self.log(f"Updated Data Dragon version to {latest}")
                        self.ddragon_ver = latest
                        v_path = os.path.join(CACHE_DIR, "version.txt")
                        with open(v_path, "w", encoding="utf-8") as f:
                            f.write(self.ddragon_ver)

                        # Invalidate stale data caches so they re-download
                        for filename in ["champion.json", "item.json", "summoner.json", "runesReforged.json"]:
                            path = os.path.join(CACHE_DIR, filename)
                            if os.path.exists(path):
                                try:
                                    os.remove(path)
                                except Exception:
                                    pass
        except Exception as e:
            self.log(f"Failed to fetch latest version: {e}")

    def _load_all(self):
        self._fetch_latest_version()
        self.log("Downloading Data Assets...")

        # Preload Profile Background
        try:
            cfg = ConfigManager()
            bg_id = cfg.get("profile_bg_id")
            if bg_id:
                self.log(f"Preloading background {bg_id}...")
                self.get_splash_art(int(bg_id), width=1100, opacity=0.5)
        except Exception:  # pylint: disable=broad-exception-caught
            pass

        self._load_champion_data()
        self._load_meraki_data()
        self._load_spell_data()
        self._load_rune_icons()
        self.log("Assets Loaded.")

    def _load_rune_icons(self):
        """Preloads all rune icons to cache (Download Only)."""
        runes = self.get_runes_data()
        if not runes:
            return

        count = 0
        for tree in runes:
            # Tree Icon
            self._ensure_rune_icon(tree["icon"])
            # Slots
            for slot in tree["slots"]:
                for rune in slot["runes"]:
                    self._ensure_rune_icon(rune["icon"])
                    count += 1
        self.log(f"Pre-checked {count} rune icons.")

    def _ensure_rune_icon(self, icon_path):
        """Downloads rune icon if missing, but DOES NOT create CTkImage."""
        if not icon_path:
            return
        safe_name = icon_path.replace("/", "_").replace("\\", "_")
        path = os.path.join(ASSETS_DIR, f"rune_{safe_name}")

        if not os.path.exists(path):
            url = f"https://ddragon.leagueoflegends.com/cdn/img/{icon_path}"
            self._start_download(url, path)

    def _load_champion_data(self):
        path = os.path.join(CACHE_DIR, "champion.json")
        try:
            if not os.path.exists(path):
                url = f"https://ddragon.leagueoflegends.com/cdn/{self.ddragon_ver}/data/en_US/champion.json"
                data = self.session.get(url, timeout=10).json()
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f)

            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.champ_data = data["data"]

            # Populate Lookup Maps
            self.id_to_key = {}
            self.id_to_tags = {}
            self.name_to_id = {}
            for key_str, info in self.champ_data.items():
                try:
                    cid = int(info["key"])
                    name = info["name"]

                    self.id_to_key[cid] = key_str
                    self.id_to_tags[cid] = info.get("tags", [])

                    # Map both DDragon Key (e.g. "MonkeyKing") and Name (e.g. "Wukong")
                    self.name_to_id[key_str.lower()] = cid
                    self.name_to_id[name.lower()] = cid
                except (ValueError, KeyError):
                    continue

        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"Failed to load champion data: {e}")

        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"Failed to load champion data: {e}")

    def _load_meraki_data(self):
        """Load detailed champion data (including roles) from Meraki Analytics."""
        path = os.path.join(CACHE_DIR, "meraki_champions.json")
        try:
            # Download if missing or stale (simple check: if we just updated ddragon, update this too)
            # For now, just check existence to avoid spamming
            if not os.path.exists(path):
                url = "https://cdn.merakianalytics.com/riot/lol/resources/latest/en-US/champions.json"
                # This file is large (~5MB), download with stream or just get
                r = self.session.get(url, timeout=15)
                if r.status_code == 200:
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(r.json(), f)
            
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                     data = json.load(f)
                     # Parse roles: ID -> [Positions]
                     self.champ_roles = {}
                     for _, info in data.items():
                         try:
                             cid = info.get("id", 0)
                             positions = info.get("positions", [])
                             if cid and positions:
                                 # Normalize "SUPPORT" -> "UTILITY" to match internal convention
                                 clean_pos = [
                                     "UTILITY" if p == "SUPPORT" else p 
                                     for p in positions
                                 ]
                                 self.champ_roles[int(cid)] = clean_pos
                         except Exception:
                             continue
                self.log(f"Loaded Meraki role data for {len(self.champ_roles)} champions.")

        except Exception as e:
            self.log(f"Failed to load Meraki data: {e}")

    def _load_spell_data(self):
        path = os.path.join(CACHE_DIR, "summoner.json")
        try:
            if not os.path.exists(path):
                url = f"https://ddragon.leagueoflegends.com/cdn/{self.ddragon_ver}/data/en_US/summoner.json"
                data = self.session.get(url, timeout=10).json()
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f)

            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.spell_data = {}
                for id_name, info in data["data"].items():
                    self.spell_data[int(info["key"])] = id_name
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    def get_champ_name(self, champ_id: int) -> str:
        """Get champion name by ID."""
        return self.id_to_key.get(champ_id, str(champ_id))

    def get_icon_path(self, category: str, name_or_id: str, sync_download: bool = False) -> str:
        """
        Get the file path for an icon.
        If sync_download is True, downloads synchronously if missing.
        """
        fname = f"{name_or_id}.png"
        path = os.path.join(ASSETS_DIR, f"{category}_{fname}")
        abs_path = os.path.abspath(path)

        # Special Case: Bravery (Auto-Download Random Icon)
        if name_or_id == "Bravery":
            if os.path.exists(path):
                return abs_path
            # URL for "Random Champion" icon (Fill/Dice icon)
            url = "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-clash/global/default/assets/images/position-selector/positions/icon-position-fill.png"

            if sync_download:
                self._simple_download(url, path)
                if os.path.exists(path):
                    return abs_path
                return ""
            else:
                self._start_download(url, path)
                return ""

        if os.path.exists(path):
            return abs_path

        # Download if missing
        url = f"https://ddragon.leagueoflegends.com/cdn/{self.ddragon_ver}/img/{category}/{fname}"

        if sync_download:
            self._simple_download(url, path)
            if os.path.exists(path):
                return abs_path
            return ""
        else:
            self._start_download(url, path)
            return ""

    def get_icon(
        self, category: str, name_or_id: str, size=(50, 50), grayscale=False, sync_download=False
    ) -> Optional[ctk.CTkImage]:
        """
        Retrieves a CTkImage for the specified icon using a two-tiered caching strategy.
        Now supports grayscale conversion.

        1. **Memory Cache**: Checks if the image is already loaded in memory.
        2. **Disk Cache**: If not in memory, checks if the file exists on disk.
           - If found, loads it, caches it in memory, and returns the image.
           - If not found, returns None and triggers a background download.

        Args:
            category (str): The category of the icon (e.g., 'champion', 'item').
            name_or_id (str): The name or ID of the asset.
            size (tuple[int, int], optional): The size of the image. Defaults to (50, 50).
            grayscale (bool, optional): Whether to convert to grayscale. Defaults to False.
            sync_download (bool, optional): If True, downloads synchronously if missing.

        Returns:
            Optional[ctk.CTkImage]: The loaded image object, or None if the asset is missing
            (download started in background).
        """
        path = self.get_icon_path(category, name_or_id, sync_download=sync_download)
        if path and os.path.exists(path):
            cache_key = f"{category}_{name_or_id}_{size[0]}_{grayscale}"
            if cache_key in self.icons:
                return self.icons[cache_key]

            if sync_download:
                try:
                    pil_img = Image.open(path)

                    # Resize first to save processing time on larger images
                    if pil_img.size != size:
                        pil_img = pil_img.resize(size, Image.Resampling.BICUBIC)

                    if grayscale:
                        pil_img = pil_img.convert("L")

                    img = ctk.CTkImage(pil_img, size=size)
                    self.icons[cache_key] = img
                    return img
                except Exception:  # pylint: disable=broad-exception-caught
                    try:
                        os.remove(path)
                        # Trigger download immediately for next render (async if not synced)
                        self.get_icon_path(category, name_or_id, sync_download=sync_download)
                    except Exception:
                        pass
                    self.log(f"Corrupted icon: {name_or_id}")
                    return None
            else:
                # Lazy loading: return placeholder immediately, configure in background
                placeholder = Image.new("RGBA", size, (0, 0, 0, 0))
                img = ctk.CTkImage(placeholder, size=size)
                self.icons[cache_key] = img

                def _load_task():
                    try:
                        pil_img = Image.open(path)
                        if pil_img.size != size:
                            pil_img = pil_img.resize(size, Image.Resampling.BICUBIC)
                        if grayscale:
                            pil_img = pil_img.convert("L")

                        # Safely trigger configure on the main thread so the UI actually updates
                        import tkinter
                        if tkinter._default_root:
                            tkinter._default_root.after(0, lambda: img.configure(light_image=pil_img, dark_image=pil_img))
                        else:
                            img.configure(light_image=pil_img, dark_image=pil_img)
                    except Exception:
                        try:
                            os.remove(path)
                            self.get_icon_path(category, name_or_id, sync_download=sync_download)
                        except Exception:
                            pass
                        self.log(f"Corrupted icon: {name_or_id}")

                self._download_queue.put(_load_task)
                return img
        
        # Download if missing (or deleted) - get_icon_path handles start_download
        return None

    def get_icon_async(
        self,
        category: str,
        name_or_id: str,
        callback,
        size=(50, 50),
        grayscale=False,
        widget=None,
    ):
        """
        Non-blocking icon loader. Offloads Image.open + resize to a worker
        thread, then delivers the result via callback on the main thread.

        Args:
            callback: callable(Optional[CTkImage]) — invoked with the result.
            widget:   a tkinter widget whose .after() is used to schedule
                      the callback on the UI thread. Required when calling
                      from non-main threads.
        """
        # Fast path: already in memory cache — no thread needed
        cache_key = f"{category}_{name_or_id}_{size[0]}_{grayscale}"
        if cache_key in self.icons:
            cached = self.icons[cache_key]
            if widget:
                widget.after(0, lambda: callback(cached))
            else:
                callback(cached)
            return

        def _worker():
            try:
                # Since we are in a worker thread, allow synchronous download if missing
                img = self.get_icon(category, name_or_id, size, grayscale, sync_download=True)
            except Exception:
                img = None

            if widget:
                widget.after(0, lambda: callback(img))
            else:
                callback(img)

        self._download_queue.put(_worker)

    def get_gamemode_icon(self, mode: str, size=(30, 30)) -> Optional[ctk.CTkImage]:
        """Get icon for game mode (SR, ARAM, ARENA). Uses Data Dragon map assets."""
        # Map modes to DDragon map IDs
        # SR = 11, ARAM = 12, Arena = 30 (or fallback)
        mode_map = {
            "SUMMONER'S RIFT": "map11",
            "ARAM MODE": "map12",
            "ARENA MODE": "map30", # Arena typically map 30
            "TFT": "map22" 
        }
        
        fname = f"mode_{mode_map.get(mode, 'unknown')}.png"
        path = os.path.join(ASSETS_DIR, fname)
        
        # Check Cache
        cache_key = f"gamemode_{mode}_{size[0]}"
        if cache_key in self.icons:
            return self.icons[cache_key]
            
        if os.path.exists(path):
            try:
                pil_img = Image.open(path)
                img = ctk.CTkImage(pil_img, size=size)
                self.icons[cache_key] = img
                return img
            except Exception:
                pass
        
        # Download Logic (Data Dragon)
        # Fallback to Community Dragon for Arena if DDragon fails (often DDragon only has main maps)
        dd_base = f"https://ddragon.leagueoflegends.com/cdn/{self.ddragon_ver}/img/map/"
        
        key = mode_map.get(mode)
        if key:
            url = f"{dd_base}{key}.png"
            # Arena fallback to CDragon if needed (DDragon sometimes lags on rotator modes)
            if mode == "ARENA MODE":
                # Arena specific fallback if DDragon fails (or use CDragon directly)
                # But let's verify DDragon first. If it fails, the file won't exist next time.
                pass 

            self._start_download(url, path)
            
        return None

    def get_rune_shard_icon(self, shard_name: str, size=(24, 24)) -> Optional[ctk.CTkImage]:
        """
        Get icon for a stat shard (Health, Adaptive, etc).
        shard_name should be the key segment, e.g. 'AdaptiveForce', 'AttackSpeed', 'Tenacity'.
        """
        if not shard_name:
            return None
            
        # Standardize shard name for filenames
        # Map common names (and typos) to the specific filename part expected by CommunityDragon
        # CommunityDragon uses: statmods{name}icon.png
        # Known valid names: adaptiveforce, attackspeed, cdrscaling, movementspeed, healthscaling, healthplus, armor, magicres, tenacity
        
        name_map = {
             "adaptiveforce": "adaptiveforce",
             "attackspeed": "attackspeed",
             "abilityhaste": "cdrscaling",   # Fix: CDScaling for Ability Haste
             "movementspeed": "movementspeed",
             "healthscaling": "healthscaling",
             "healthplus": "healthplus",
             "health": "healthplus",        # Fallback
             "armor": "armor",
             "magicresist": "magicres",      # Fix: magicres
             "magicres": "magicres",
             "tenacity": "tenacity"
        }
        
        clean_name = shard_name.lower().replace(" ", "")
        file_part = name_map.get(clean_name, clean_name)
        
        fname = f"statmods{file_part}icon.png"
        path = os.path.join(ASSETS_DIR, fname)
        
        # Cache Check
        cache_key = f"shard_{shard_name}_{size[0]}"
        if cache_key in self.icons:
            return self.icons[cache_key]
            
        if os.path.exists(path):
            try:
                pil_img = Image.open(path).convert("RGBA")
                img = ctk.CTkImage(pil_img, size=size)
                self.icons[cache_key] = img
                return img
            except Exception:
                pass
                
        # Download (CommunityDragon)
        url = f"https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/perk-images/statmods/{fname}"
        self._start_download(url, path)
        return None

    def get_role_icon_path(self, role: str) -> str:
        """Get the file path for a role icon."""
        role_map = {
            "TOP": "top",
            "JUNGLE": "jungle",
            "MIDDLE": "middle",
            "BOTTOM": "bottom",
            "UTILITY": "utility",
            "FILL": "fill",
        }
        r_name = role_map.get(role, "fill")
        fname = f"icon-position-{r_name}.png"
        path = os.path.join(ASSETS_DIR, fname)

        if os.path.exists(path):
            return os.path.abspath(path)

        url = f"https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/position-icons/position-{r_name}.png"
        self._start_download(url, path)
        
        return ""

    def get_role_icon(self, role: str, size=(40, 40)) -> Optional[ctk.CTkImage]:
        """Get a CTkImage for the specified role icon."""
        path = self.get_role_icon_path(role)
        if path and os.path.exists(path):
            cache_key = f"role_{role}_{size[0]}"
            if cache_key in self.icons:
                return self.icons[cache_key]
            try:
                pil_img = Image.open(path)
                img = ctk.CTkImage(pil_img, size=size)
                self.icons[cache_key] = img
                return img
            except Exception:  # pylint: disable=broad-exception-caught
                return None
        return None

    def _simple_download(self, url, path):
        try:
            # Enable SSL verification for security
            r = self.session.get(url, timeout=10)
            if r.status_code == 200:
                with open(path, "wb") as f:
                    f.write(r.content)
            else:
                print(f"[Assets] Failed {url} -> {r.status_code}")
        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"[Assets] Exception {url} -> {e}")

    def _start_download(self, url, path):
        """Helper to start a download if not already in progress."""
        with self._lock:
            if path in self._pending_downloads:
                return
            self._pending_downloads.add(path)

        def _target():
            try:
                self._simple_download(url, path)
            finally:
                with self._lock:
                    self._pending_downloads.discard(path)

        self._download_queue.put(_target)

    def get_rune_icon_path(self, icon_path: str) -> Optional[str]:
        """Get the file path for a rune icon."""
        if not icon_path:
            return None

        safe_name = icon_path.replace("/", "_").replace("\\", "_")
        path = os.path.join(ASSETS_DIR, f"rune_{safe_name}")

        if os.path.exists(path):
            return os.path.abspath(path)

        # Background download
        url = f"https://ddragon.leagueoflegends.com/cdn/img/{icon_path}"
        self._start_download(url, path)
        return None

    def get_rune_icon(self, icon_path: str, size=(20, 20)) -> Optional[ctk.CTkImage]:
        """Get a CTkImage for the specified rune icon."""
        if not icon_path:
            return None

        cache_key = f"rune_{icon_path}_{size[0]}"
        if cache_key in self.icons:
            return self.icons[cache_key]

        safe_name = icon_path.replace("/", "_").replace("\\", "_")
        path = os.path.join(ASSETS_DIR, f"rune_{safe_name}")

        if os.path.exists(path):
            try:
                # full_path = os.path.abspath(path)
                pil_img = Image.open(path).convert("RGBA")
                img = ctk.CTkImage(pil_img, size=size)
                self.icons[cache_key] = img
                return img
            except Exception:  # pylint: disable=broad-exception-caught
                # File corrupted? Delete and re-download
                try:
                    os.remove(path)
                except Exception:
                    pass
                # Update status
                self.log(f"Redownloading corrupted asset: {icon_path}")

        # Background download
        url = f"https://ddragon.leagueoflegends.com/cdn/img/{icon_path}"
        self._start_download(url, path)
        return None



    def get_spell_name(self, key: int):
        """Get spell name by key."""
        return self.spell_data.get(key, None)

    def get_champ_id(self, name: str) -> Optional[int]:
        """Get champion ID by name."""
        if not name:
            return None

        name_lower = name.lower().strip()
        # Special pseudo-champions in League client
        if name_lower == "bravery":
            return -3  # Bravery mode ID
        if name_lower == "random":
            return 0  # Random pick ID

        return self.name_to_id.get(name_lower)

    def get_champ_tags(self, champ_id: int) -> list:
        """Get champion tags by ID (Static Fallback)."""
        return self.id_to_tags.get(champ_id, [])

    def get_champ_roles(self, champ_id: int) -> list:
        """
        Get champion roles/positions.
        Returns Meraki dynamic data if available, otherwise static tags.
        """
        if champ_id in self.champ_roles:
            return self.champ_roles[champ_id]
        
        # Fallback to static mapping if Meraki data missing
        tags = self.get_champ_tags(champ_id)
        roles = []
        if "Fighter" in tags or "Tank" in tags: roles.extend(["TOP", "JUNGLE"])
        if "Mage" in tags or "Assassin" in tags: roles.extend(["MIDDLE"])
        if "Marksman" in tags: roles.append("BOTTOM")
        if "Support" in tags or "Mage" in tags or "Tank" in tags: roles.append("UTILITY")
        return list(set(roles))

    def download_all_assets(self, progress_callback=None):
        """Download all champion icons."""
        if not self.champ_data:
            self._load_champion_data()

        # Ensure Item/Rune Data is loaded effectively by just getting it (lazy loading in orig code)
        self._get_items_data()
        self.get_runes_data()

        total = len(self.champ_data)

        def _ensure_champ_icon_sync(name):
            category = "champion"
            fname = f"{name}.png"
            path = os.path.join(ASSETS_DIR, f"{category}_{fname}")
            if not os.path.exists(path):
                # Check/Register pending to coordinate with get_icon threads
                with self._lock:
                    if path in self._pending_downloads:
                        return name
                    self._pending_downloads.add(path)

                try:
                    # Use simple download directly since this is already in a thread pool
                    url = f"https://ddragon.leagueoflegends.com/cdn/{self.ddragon_ver}/img/{category}/{fname}"
                    self._simple_download(url, path)
                finally:
                    with self._lock:
                        self._pending_downloads.discard(path)
            return name

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(_ensure_champ_icon_sync, name): name
                for name in self.champ_data.keys()
            }

            for i, future in enumerate(concurrent.futures.as_completed(futures)):
                name = futures[future]
                try:
                    future.result()
                except Exception as e:
                    print(f"Error downloading asset for {name}: {e}")

                if progress_callback:
                    progress_callback(f"Downloading Champions: {name} ({i + 1}/{total})")

        if progress_callback:
            progress_callback("Done!")

    def _get_items_data(self):
        path = os.path.join(CACHE_DIR, "item.json")
        try:
            if not os.path.exists(path):
                url = f"https://ddragon.leagueoflegends.com/cdn/{self.ddragon_ver}/data/en_US/item.json"
                data = self.session.get(url, timeout=10).json()
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
            with open(path, "r", encoding="utf-8") as f:
                return list(json.load(f)["data"].keys())
        except Exception:  # pylint: disable=broad-exception-caught
            return []

    def get_runes_data(self):
        """Get runes reforged data."""
        path = os.path.join(CACHE_DIR, "runesReforged.json")
        try:
            if not os.path.exists(path):
                url = f"https://ddragon.leagueoflegends.com/cdn/{self.ddragon_ver}/data/en_US/runesReforged.json"
                data = self.session.get(url, timeout=10).json()
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:  # pylint: disable=broad-exception-caught
            return []

    def get_profile_icon(self, icon_id: int, size=(100, 100)) -> Optional[ctk.CTkImage]:
        """Get a CTkImage for the specified profile icon."""
        path = os.path.join(ASSETS_DIR, f"profileicon_{icon_id}.png")

        # Check Cache
        cache_key = f"profile_{icon_id}_{size[0]}"
        if cache_key in self.icons:
            return self.icons[cache_key]

        if os.path.exists(path):
            try:
                pil_img = Image.open(path)
                img = ctk.CTkImage(pil_img, size=size)
                self.icons[cache_key] = img
                return img
            except Exception:  # pylint: disable=broad-exception-caught
                return None

        # Download
        # Use dynamic version or fallback to CommunityDragon
        # CommunityDragon is safer for new icons
        # url = f"https://ddragon.leagueoflegends.com/cdn/{self.ddragon_ver}/img/profileicon/{icon_id}.png"
        url = f"https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/profile-icons/{icon_id}.jpg"
        
        self._start_download(url, path)
        return None

    def get_splash_art(
        self, skin_id: int, width=1280, opacity=1.0
    ) -> Optional[ctk.CTkImage]:
        """Get a CTkImage for the specified skin splash art."""
        # Logic: SkinID usually ChampID*1000 + SkinIndex (e.g. 266006 -> 266, 006)

        cache_key = f"splash_{skin_id}_{width}_{opacity}"
        if cache_key in self.icons:
            return self.icons[cache_key]

        # Parse ID
        try:
            champ_id = skin_id // 1000
            skin_num = skin_id % 1000
            ddragon_id = self.get_champ_name(champ_id)
            if not ddragon_id or ddragon_id == str(champ_id):
                return None
        except Exception:  # pylint: disable=broad-exception-caught
            return None

        fname = f"splash_{ddragon_id}_{skin_num}.jpg"
        path = os.path.join(ASSETS_DIR, fname)

        if os.path.exists(path):
            try:
                pil_img = Image.open(path).convert("RGBA")

                # Resize (Aspect Ratio)
                aspect = pil_img.height / pil_img.width
                height = int(width * aspect)
                # Bolt: Use BICUBIC instead of LANCZOS for ~25% faster resizing with acceptable quality
                pil_img = pil_img.resize((width, height), Image.Resampling.BICUBIC)

                # Opacity
                if opacity < 1.0:
                    alpha = pil_img.split()[3]
                    # Bolt: Optimized opacity scaling using a Lookup Table (LUT).
                    # This is significantly faster than lambda per pixel and preserves existing transparency.
                    lut = [int(p * opacity) for p in range(256)]
                    alpha = alpha.point(lut)
                    pil_img.putalpha(alpha)

                img = ctk.CTkImage(pil_img, size=(width, height))
                self.icons[cache_key] = img
                return img
            except Exception as e:
                print(e)
                return None

        # Download
        url = f"https://ddragon.leagueoflegends.com/cdn/img/champion/splash/{ddragon_id}_{skin_num}.jpg"
        self._start_download(url, path)
        return None

    def get_loading_art(self, skin_id: int, width=150) -> Optional[ctk.CTkImage]:
        """Get a CTkImage for the specified skin loading art."""
        # Cache Key
        cache_key = f"loading_{skin_id}_{width}"
        if cache_key in self.icons:
            return self.icons[cache_key]

        # Parse ID
        try:
            champ_id = skin_id // 1000
            skin_num = skin_id % 1000
            ddragon_id = self.get_champ_name(champ_id)
            if not ddragon_id or ddragon_id == str(champ_id):
                return None
        except Exception:  # pylint: disable=broad-exception-caught
            return None

        fname = f"loading_{ddragon_id}_{skin_num}.jpg"
        path = os.path.join(ASSETS_DIR, fname)

        if os.path.exists(path):
            try:
                pil_img = Image.open(path)
                # Resize (Maintain Aspect Ratio)
                # Loading art is usually 308x560.
                aspect = pil_img.height / pil_img.width
                height = int(width * aspect)

                # Bolt: Resize PIL image to reduce memory footprint (6.5x reduction for 308->120)
                pil_img = pil_img.resize((width, height), Image.Resampling.BICUBIC)

                img = ctk.CTkImage(pil_img, size=(width, height))
                self.icons[cache_key] = img
                return img
            except Exception:  # pylint: disable=broad-exception-caught
                return None

        # Download
        url = f"https://ddragon.leagueoflegends.com/cdn/img/champion/loading/{ddragon_id}_{skin_num}.jpg"
        self._start_download(url, path)
        return None

    def download_all_app_assets(self, progress_callback=None):
        """
        Downloads all assets used by the application:
        - Champion square icons (~170)
        - Rune tree & slot icons (~65)
        - Role position icons (6)
        
        progress_callback(current, total, status_msg)
        Runs in a background thread.
        """
        import threading

        if progress_callback:
            progress_callback(0, 1, "Scanning required assets...")

        download_queue = []

        # --- 1. Champion Icons ---
        if self.champ_data:
            for key_str, info in self.champ_data.items():
                fname = f"{key_str}.png"
                path = os.path.join(ASSETS_DIR, f"champion_{fname}")
                if not os.path.exists(path):
                    url = f"https://ddragon.leagueoflegends.com/cdn/{self.ddragon_ver}/img/champion/{fname}"
                    download_queue.append((url, path, f"Champion: {info.get('name', key_str)}"))

        # --- 2. Rune Icons ---
        runes = self.get_runes_data()
        if runes:
            for tree in runes:
                # Tree icon
                icon_path = tree.get("icon", "")
                if icon_path:
                    safe_name = icon_path.replace("/", "_").replace("\\", "_")
                    path = os.path.join(ASSETS_DIR, f"rune_{safe_name}")
                    if not os.path.exists(path):
                        url = f"https://ddragon.leagueoflegends.com/cdn/img/{icon_path}"
                        download_queue.append((url, path, f"Rune Tree: {tree.get('name', '?')}"))

                # Slot runes
                for slot in tree.get("slots", []):
                    for rune in slot.get("runes", []):
                        r_icon = rune.get("icon", "")
                        if r_icon:
                            safe_name = r_icon.replace("/", "_").replace("\\", "_")
                            path = os.path.join(ASSETS_DIR, f"rune_{safe_name}")
                            if not os.path.exists(path):
                                url = f"https://ddragon.leagueoflegends.com/cdn/img/{r_icon}"
                                download_queue.append((url, path, f"Rune: {rune.get('name', '?')}"))

        roles = ["top", "jungle", "middle", "bottom", "utility", "fill"]
        for r_name in roles:
            fname = f"icon-position-{r_name}.png"
            path = os.path.join(ASSETS_DIR, fname)
            if not os.path.exists(path):
                url = f"https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/position-icons/position-{r_name}.png"
                download_queue.append((url, path, f"Role: {r_name.title()}"))

        missing_count = len(download_queue)
        if missing_count == 0:
            if progress_callback:
                progress_callback(1, 1, "All app assets already cached!")
            return

        if progress_callback:
            progress_callback(0, missing_count, f"Downloading {missing_count} assets...")

        # Batch download
        completed = 0
        batch_size = 10

        for i in range(0, missing_count, batch_size):
            batch = download_queue[i:i + batch_size]
            threads = []

            for url, path, _label in batch:
                t = threading.Thread(target=self._download_file_sync, args=(url, path), daemon=True)
                t.start()
                threads.append(t)

            for t in threads:
                t.join(timeout=15)

            completed += len(batch)
            # Show last item label as context
            last_label = batch[-1][2] if batch else ""
            if progress_callback:
                progress_callback(completed, missing_count, f"{completed}/{missing_count} — {last_label}")

        if progress_callback:
            progress_callback(missing_count, missing_count, f"Done! {missing_count} assets downloaded.")

    def _download_file_sync(self, url, path):
        """Synchronous download for batch processing."""
        try:
           r = self.session.get(url, timeout=10)
           if r.status_code == 200:
               with open(path, "wb") as f:
                   f.write(r.content)
        except Exception:
            pass
    def get_all_summoner_icons(self):
        """Fetch all summoner icons metadata from CommunityDragon, sorted by year."""
        # We can't use LCUClient in AssetManager directly as it causes circular import usually
        # But we used LCU to find finding the URL...
        # Wait, LCUClient typically provides dynamic data.
        # However, the icon list is available via: 
        # https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/summoner-icons.json
        # This is better than relying on local LCU if we want it to work offline (cacheable).
        
        path = os.path.join(CACHE_DIR, "summoner_icons.json")
        try:
            if not os.path.exists(path):
                url = "https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/summoner-icons.json"
                # Use simple requests
                r = self.session.get(url, timeout=10)
                if r.status_code == 200:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(r.text)
                else:
                    return []
            
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Verify list
                if isinstance(data, list):
                    # Sort decending by year
                    # Default year=0 for unknown
                    return sorted(data, key=lambda x: x.get("yearReleased", 0), reverse=True)
                return []
                
        except Exception as e:
            print(f"Error fetching icon list: {e}")
            return []
