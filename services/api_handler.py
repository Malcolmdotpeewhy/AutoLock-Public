"""
LCU API Handler
Manages communication with the League of Legends Client Update (LCU).
"""
import base64
import os
import threading
import time
from typing import Dict, Optional

import psutil
import requests

from utils.logger import Logger


class LCUClient:
    """
    Handles communication with the Local League Client Update (LCU) API.
    Auto-detects the client's lockfile to get port and authentication.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.port = None
        self.auth_token = None
        self.protocol = "https"
        self.base_url = None
        self.is_connected = False
        self.headers = {}
        self.session = requests.Session()
        self.session.verify = False

        # Do NOT connect immediately to avoid blocking UI startup.
        # Connection is handled by the background loop in main.py.

    def connect(self, silent=False) -> bool:
        """Attempts to read the lockfile and establish connection details."""
        with self._lock:
            # Atomic check: If we connected while waiting for lock, return success
            if self.is_connected:
                return True

            try:
                # Look for League Client processes
                client_procs = [
                    "LeagueClientUx.exe",
                    "LeagueClient.exe",
                    "RiotClientUx.exe",
                ]
                process = None

                # Bolt Optimization: Iterate process list ONCE instead of up to 3 times.
                # Prioritize LeagueClientUx.exe, but scan for others in the same pass.
                found_procs = {}
                highest_priority = client_procs[0]

                scan_start = time.time()

                for p in psutil.process_iter(["name"]):
                    try:
                        name = p.info["name"]
                        if name in client_procs:
                            found_procs[name] = p
                            # Optimization: Stop early if we found the best one
                            if name == highest_priority:
                                break
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue

                scan_duration = time.time() - scan_start
                if scan_duration > 0.5:
                    Logger.debug("LCU", f"Process scan took {scan_duration:.3f}s")

                # Select best match based on priority
                for p_name in client_procs:
                    if p_name in found_procs:
                        process = found_procs[p_name]
                        break

                if not process:
                    if not silent:
                        Logger.debug("LCU", "Client not found. Ensure League of Legends is running.")
                    self.is_connected = False
                    return False

                # Try to read lockfile from process info
                try:
                    cmdline = process.cmdline()
                    for arg in cmdline:
                        if "--app-port=" in arg:
                            self.port = arg.split("=")[1]
                        if "--remoting-auth-token=" in arg:
                            self.auth_token = arg.split("=")[1]
                except (psutil.AccessDenied, Exception):  # pylint: disable=broad-exception-caught
                    # Access Denied on cmdline is common if running non-admin. Fallback to lockfile.
                    Logger.debug("LCU", "Could not read process command line. Falling back to lockfile scan.")

                # Fallback: Check for 'lockfile' in the process directory if we miss port/token
                if not self.port or not self.auth_token:
                    try:
                        exe_path = process.exe()
                        proc_dir = os.path.dirname(exe_path)
                        lockfile_path = os.path.join(proc_dir, "lockfile")

                        if os.path.exists(lockfile_path):
                            Logger.debug("LCU", f"Reading lockfile at {lockfile_path}")
                            with open(lockfile_path, "r", encoding="utf-8") as f:
                                data = f.read().split(":")
                                if len(data) >= 4:
                                    self.port = data[2]
                                    self.auth_token = data[3]
                                    Logger.debug(
                                        "LCU", f"Extracted from lockfile: Port {self.port}"
                                    )
                    except (psutil.AccessDenied, Exception) as e:  # pylint: disable=broad-exception-caught
                        Logger.debug("LCU", f"Lockfile check failed: {e}")

                if self.port and self.auth_token:
                    auth_str = f"riot:{self.auth_token}"
                    b64_auth = base64.b64encode(auth_str.encode()).decode()
                    self.headers = {
                        "Authorization": f"Basic {b64_auth}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    }
                    self.session.headers.update(self.headers)
                    self.base_url = f"https://127.0.0.1:{self.port}"
                    self.is_connected = True
                    Logger.debug("LCU", f"Connected to port {self.port}")
                    return True

                Logger.debug("LCU", "Found process but could not extract credentials.")

            except Exception as e:  # pylint: disable=broad-exception-caught
                Logger.error("LCU", f"Connection Error: {e}")
                self.is_connected = False

            return False

    def request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        silent: bool = False,
    ) -> Optional[requests.Response]:
        """Generic wrapper for LCU requests."""
        if not self.is_connected:
            if not self.connect():
                return None

        url = f"{self.base_url}{endpoint}"
        t_start = time.time()
        try:
            if not silent:
                Logger.debug("LCU", f"REQ -> {method} {endpoint}")
            response = self.session.request(
                method=method,
                url=url,
                # headers=self.headers, # Already in session
                json=data,
                verify=False,
                timeout=2,  # Prevent blocking UI
            )

            dur = time.time() - t_start
            if not silent:
                Logger.debug(
                    "LCU", f"RES <- {response.status_code} [{dur:.3f}s] {endpoint}"
                )
            return response
        except requests.RequestException as e:
            dur = time.time() - t_start
            Logger.error("LCU", f"FAIL [{dur:.3f}s] {endpoint} : {e}")
            # Connection lost?
            self.is_connected = False
            return None

    # --- Convenience Methods ---

    def get_summoner_current_summoner(self):
        """Get current summoner info."""
        return self.request("GET", "/lol-summoner/v1/current-summoner")

    def get_champ_select_session(self):
        """Get champion select session."""
        return self.request("GET", "/lol-champ-select/v1/session")

    def action_champ_select(
        self, action_id: int, champion_id: int, complete: bool = False
    ):
        """Perform a champion select action (pick/ban)."""
        data = {"championId": champion_id}
        if complete:
            data["completed"] = True
        return self.request(
            "PATCH", f"/lol-champ-select/v1/session/actions/{action_id}", data=data
        )

    def set_champ_select_intent(self, action_id: int, champion_id: int):
        """Set champion select intent (hover)."""
        # Usually for pick intent, you act on the 'pick' action but just don't complete it
        return self.action_champ_select(action_id, champion_id, complete=False)
