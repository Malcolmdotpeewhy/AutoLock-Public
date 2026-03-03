"""
Automation Engine
Handles the core logic for auto-accept, pick/ban, runes, and more.
"""
import math
import random
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

from .api_handler import LCUClient
from .asset_manager import AssetManager, ConfigManager
from utils.logger import Logger
from .rune_manager import RuneManager
from .preference_model import PreferenceModel


class AutomationEngine:
    """Core automation engine for the League Agent."""

    def __init__(
        self,
        lcu: LCUClient,
        assets: AssetManager,
        config: ConfigManager,
        log_func=None,
        stop_func=None,
    ):
        self.lcu = lcu
        self.assets = assets
        self.config = config
        self.log = log_func
        self.stop_func = stop_func  # Callback to disable system
        self.running = False
        self.paused = False
        self.thread = None
        self.executor = ThreadPoolExecutor(max_workers=5)
        self.runes = RuneManager(lcu, assets)
        self.setup_done = False
        self.last_phase = "None"  # Track previous phase
        self.current_queue_id = None  # Track queue ID for mode detection
        self.last_champ_select_session = None # Used for behavioral learning transition
        self.pref_model = PreferenceModel(config, assets)

        # Pick timing - wait before lock-in (configurable via dashboard slider)
        self.pick_hover_time = None  # When we first hovered the champion
        self.pick_hover_cid = None  # Which champion we're hovering
        self.pick_delay = self.config.get("lock_in_delay", 5)  # Seconds to wait before locking in

        # Ready Check State
        self.ready_check_start = None
        self.ready_check_delay = None
        self.ready_check_accepted = False
        self._last_countdown_log = None

        # Self-Healing Rate Limit
        self._last_disconnect_log = 0

        # Session Stats
        self.session_stats = {"wins": 0, "losses": 0, "games": 0}
        self.last_game_id = 0
        self.has_honored = False
        self._end_of_game_handled = False
        self._requeue_handled = False



    def set_mode(self, mode):
        """Set the current game mode."""
        self._log(f"Mode set to: {mode}")
        self.mode = mode

    def start(self, start_paused=False):
        """Start the automation loop."""
        if self.running:
            return
        self.running = True
        self.paused = start_paused
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop the automation loop."""
        self.running = False

    def pause(self):
        """Pause automation."""
        self.paused = True

    def resume(self):
        """Resume automation."""
        self.paused = False

    def _log(self, msg):
        if self.log:
            self.log(msg)
        Logger.debug("Auto", msg)

    def _loop(self):
        while self.running:
            if self.paused:
                time.sleep(1)
                continue

            if not self.lcu.is_connected:
                # Self-Healing: Attempt aggressive reconnect
                # Rate limit logs to avoid spamming the log file (every 30s)
                if time.time() - self._last_disconnect_log > 30:
                    Logger.debug("AutoLoop", "LCU Disconnected. Attempting Self-Heal...")
                    self._last_disconnect_log = time.time()

                if self.lcu.connect(silent=True):
                    Logger.debug(
                        "AutoLoop", "Self-Heal Successful: Reconnected to LCU."
                    )
                else:
                    time.sleep(2)
                continue

            try:
                self._tick()

            except Exception as e:  # pylint: disable=broad-exception-caught
                tb = traceback.format_exc()
                Logger.error("AutoLoop", f"Critical Error: {e}\n{tb}")
                print(f"Auto Loop Error: {e}")
                time.sleep(3)

    def _tick(self):
        # --- PARALLEL FETCHING ---
        # OPTIMIZATION: Submit speculative requests conditionally based on last_phase
        # This significantly reduces API load during high-frequency polling states (e.g. ChampSelect).

        # 1. Phase (Always)
        f_phase = self.executor.submit(
            self.lcu.request, "GET", "/lol-gameflow/v1/gameflow-phase", None, True
        )

        # 2. Lobby (covers Lobby, Matchmaking)
        # Relevant if we are already in Lobby/Matchmaking or just starting up/ending game
        f_lobby = None
        if self.last_phase in ("None", "EndOfGame", "Lobby", "Matchmaking"):
            f_lobby = self.executor.submit(
                self.lcu.request, "GET", "/lol-lobby/v2/lobby", None, True
            )

        # 3. Session (covers ChampSelect)
        # Relevant if we are matching, checking ready, or in select
        f_session = None
        if self.last_phase in ("Matchmaking", "ReadyCheck", "ChampSelect"):
            f_session = self.executor.submit(
                self.lcu.request, "GET", "/lol-champ-select/v1/session", None, True
            )

        # 4. Search State (if enabled)
        f_search = None
        if self.config.get("auto_requeue") and self.last_phase in ("Lobby", "Matchmaking"):
            f_search = self.executor.submit(
                self.lcu.request,
                "GET",
                "/lol-lobby/v2/lobby/matchmaking/search-state",
                None,
                True,
            )

        # --- RESOLVE PHASE ---
        phase_req = f_phase.result()
        phase = (
            phase_req.json()
            if phase_req and phase_req.status_code == 200
            else "None"
        )

        # --- AUTO-DISABLE CHECK ---
        # Check for manual queue cancellation (Matchmaking -> Lobby)
        if self.last_phase == "Matchmaking" and phase == "Lobby":
            self._log("Queue Cancelled Detected. Disabling System...")
            if self.stop_func:
                self.stop_func()  # Disable Power
                time.sleep(1)
                return

        # --- BEHAVIORAL MODEL TRIGGER ---
        if self.last_phase == "ChampSelect" and phase == "InProgress":
            if self.last_champ_select_session:
                try:
                    me = self._get_local_player(self.last_champ_select_session)
                    picked_id = me.get("championId") if me else None
                    bench = [c.get("championId") for c in self.last_champ_select_session.get("benchChampions", [])]
                    self.pref_model.update_after_match(picked_id, bench)
                    self._log("Behavioral Preference Model updated.")
                except Exception as e:
                    self._log(f"Error updating Preference Model: {e}")

        # Clear session cache if game aborted
        if self.last_phase == "ChampSelect" and phase not in ["ChampSelect", "InProgress"]:
            self.last_champ_select_session = None

        self.last_phase = phase

        # --- RESOLVE SPECULATIVE DATA ---
        # Use results directly. If request failed (e.g. 404), handle gracefully.

        lobby_data = None
        if phase in ("Lobby", "Matchmaking") and f_lobby:
            try:
                l_req = f_lobby.result()
                if l_req and l_req.status_code == 200:
                    lobby_data = l_req.json()
                    self.current_queue_id = (
                        lobby_data.get("gameConfig", {}).get("queueId")
                    )
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        search_data = None
        if f_search and phase in ("Lobby", "Matchmaking"):
            try:
                s_req = f_search.result()
                if s_req and s_req.status_code == 200:
                    search_data = s_req.json()
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        session_data = None
        if phase == "ChampSelect" and f_session:
            try:
                sess_req = f_session.result()
                if sess_req and sess_req.status_code == 200:
                    session_data = sess_req.json()
                    self.last_champ_select_session = session_data
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        self._handle_ready_check(phase)
        self._handle_champ_select(phase, session_data)
        self._handle_auto_queue(phase, search_data)
        self._handle_auto_role(phase, lobby_data)
        self._track_session_stats(phase)

        self._handle_auto_honor(phase)

        # Dynamic Polling Interval
        if phase == "ChampSelect":
            # User Configurable Speed for Critical Phase
            sleep_time = self.config.get("polling_rate_champ_select", 0.5)
            
            # ARAM/Bench Optimization: Force 1.0s polling
            # These modes require faster checking for bench swaps and have no "lock in" risk.
            if session_data and session_data.get("benchChampions"):
                sleep_time = 1.0

        elif phase == "ReadyCheck":
            sleep_time = 1.0  # SLOW (Response time ~1s)
        elif phase in ["Lobby", "Matchmaking", "PreEndOfGame", "EndOfGame"]:
            sleep_time = 2.0  # ECO
        elif phase == "InProgress":
            sleep_time = 30.0 # DEEP SLEEP (Game Started)
        else:
            sleep_time = 3.0  # IMPROVED RESPONSIVENESS (Was 10.0)

        time.sleep(sleep_time)

    def _handle_ready_check(self, phase):
        # Reset state when not in ReadyCheck
        if phase != "ReadyCheck":
            self.ready_check_start = None
            self.ready_check_delay = None
            self.ready_check_accepted = False
            self._last_countdown_log = None
            return

        if not self.config.get("auto_accept"):
            return

        # If already accepted, do nothing
        if self.ready_check_accepted:
            return

        # Initialize Timer
        if self.ready_check_start is None:
            self.ready_check_start = time.time()

            # UX: Randomize delay to be more human-like
            base_delay = self.config.get("accept_delay", 2.0)
            if base_delay > 0:
                # Add 0.0-1.5s random variance
                variance = random.uniform(0.0, 1.5)
                self.ready_check_delay = base_delay + variance
            else:
                self.ready_check_delay = 0.0

            self._log(f"Auto Accept: Waiting {self.ready_check_delay:.1f}s...")
            return

        # Check Timer
        # Use stored randomized delay
        target_delay = self.ready_check_delay if self.ready_check_delay is not None else self.config.get("accept_delay", 2.0)
        elapsed = time.time() - self.ready_check_start

        if elapsed >= target_delay:
            self.lcu.request("POST", "/lol-matchmaking/v1/ready-check/accept")
            self.ready_check_accepted = True
            self._log("Auto Accept: Accepted!")
        else:
            # Countdown Log
            remaining = target_delay - elapsed
            current_ceil = math.ceil(remaining)
            if current_ceil != self._last_countdown_log and current_ceil > 0:
                self._log(f"Auto Accept: {current_ceil}s...")
                self._last_countdown_log = current_ceil

    def _handle_auto_queue(self, phase, search_data=None):
        if not self.config.get("auto_requeue"):
            return

        # Reset handled flag if not in EndOfGame
        if phase != "EndOfGame":
            self._requeue_handled = False

        # Only in EndOfGame or None (if we just finished)
        # Note: We must trust the passed phase.

        if phase == "EndOfGame":
            if not self._requeue_handled:
                self.lcu.request("POST", "/lol-end-of-game/v1/state/dismiss-stats")
                self.lcu.request("POST", "/lol-lobby/v2/play-again")
                self._log("Auto Re-Queued (Play Again)")
                self._requeue_handled = True
        elif phase == "Lobby":
            # Check if we are already searching?
            state = search_data
            if not state:
                search_state = self.lcu.request(
                    "GET", "/lol-lobby/v2/lobby/matchmaking/search-state"
                )
                if search_state and search_state.status_code == 200:
                    state = search_state.json()

            if state:
                # If not searching, start search
                if state.get("searchState") != "Searching":
                    self.lcu.request("POST", "/lol-lobby/v2/lobby/matchmaking/search")
                    self._log("Auto Re-Queue: Starting Matchmaking...")
            else:
                # Blind fire fallback
                self.lcu.request("POST", "/lol-lobby/v2/lobby/matchmaking/search")

            self.setup_done = False  # Reset setup state

    def _handle_auto_role(self, phase, lobby_data=None):
        # Check Master Switch
        if not self.config.get("auto_set_roles"):
            return

        # Check if in Lobby
        if phase != "Lobby":
            return

        p1 = self.config.get("role_primary")
        p2 = self.config.get("role_secondary")

        if not p1 or not p2:
            return

        # Check current roles to avoid spamming
        if lobby_data:
            members = lobby_data.get("members", [])
        else:
            lobby = self.lcu.request("GET", "/lol-lobby/v2/lobby")
            if not lobby or lobby.status_code != 200:
                return
            members = lobby.json().get("members", [])

        local_member = next((m for m in members if m.get("isLocalMember")), None)

        if local_member:
            c1 = local_member.get("firstPositionPreference")
            c2 = local_member.get("secondPositionPreference")

            if c1 != p1 or c2 != p2:
                self.lcu.request(
                    "PUT",
                    "/lol-lobby/v2/lobby/members/localMember/position-preferences",
                    {"firstPreference": p1, "secondPreference": p2},
                )
                self._log(f"Auto Set Roles: {p1} / {p2}")

    def _handle_champ_select(self, phase, session_data=None):
        if self.paused:
            return  # Output Safety
        if phase != "ChampSelect":
            self.setup_done = False
            self.pick_hover_cid = None  # Reset pick state on exit/dodge
            self.pick_hover_time = None
            self._last_pick_ban_log = None  # Reset so next game logs fresh
            return

        # Get Session
        session = session_data
        if not session:
            r_session = self.lcu.request("GET", "/lol-champ-select/v1/session")
            if r_session and r_session.status_code == 200:
                session = r_session.json()

        if not session:
            return

        # Cache session unconditionally so `update_after_match` catches Pick & Bench data on game start
        self.last_champ_select_session = session

        # --- LOGIC SPLIT: BENCH vs STANDARD ---
        # "benchChampions" only exists in ARAM, ARURF, and some rotating modes.
        # This is the most reliable way to detect if we should use Sniper logic.
        has_bench = len(session.get("benchChampions", [])) > 0

        # Also check queue ID for Arena (1700) which has specific banning logic but might not have bench in same way?
        # Arena DOES have a bench phase but it's different.
        # Actually Arena uses standard pick/ban mostly but with unique flow.
        # Let's trust Queue ID for Arena, and "Bench" for ARAM/ARURF.

        is_arena = self.current_queue_id == 1700

        if is_arena:
            # Arena uses standard pick/ban flow
            pass

        if has_bench and not is_arena:
            # Handle ARAM / ARURF / All Random
            self._handle_bench_session(session)
        else:
            # Handle Standard Pick/Ban (SR, Arena, etc.)
            self._handle_standard_session(session)

    def _handle_bench_session(self, session):
        # Logic for modes with a Bench (ARAM, ARURF)

        # 1. Sniper (Auto-Swap)
        priority_cfg = self.config.get("priority_picker", {})
        if priority_cfg.get("enabled", False):
            self._perform_priority_sniper(session, priority_cfg.get("list", []))
        else:
            self._perform_sniper(session)

        # 2. Apply Loadouts (Runes/Skins)
        # Even in ARAM, we want to apply runes if we get a specific champ.
        me = self._get_local_player(session)
        if me:
            assigned_role = "ARAM"  # Dummy role
            self._apply_loadout(me, assigned_role)

    def _perform_priority_sniper(self, session, priority_list):
        if not priority_list:
            return

        bench = session.get("benchChampions", [])
        if not bench:
            return

        # Check what we currently have
        me = self._get_local_player(session)
        my_champ_id = me.get("championId", 0) if me else 0
        my_champ_name = self.assets.get_champ_name(my_champ_id) if my_champ_id else ""
        
        # OPTIMIZATION: Convert list to dict for O(1) lookup to prevent O(N) scanning inside loop
        # We iterate in reverse so that if there are duplicates, the first occurrence's index is kept
        priority_dict = {name: idx for idx, name in reversed(list(enumerate(priority_list)))}

        my_priority_idx = priority_dict.get(my_champ_name, 9999)

        best_bench_champ = None
        best_bench_idx = 9999
        best_bench_id = 0

        for champ in bench:
            cid = champ.get("championId")
            cname = self.assets.get_champ_name(cid)
            idx = priority_dict.get(cname)
            if idx is not None and idx < best_bench_idx:
                best_bench_idx = idx
                best_bench_champ = cname
                best_bench_id = cid

        if best_bench_idx < my_priority_idx:
            # Cooldown check to avoid rate-limiter spam
            now = time.time()
            if not hasattr(self, "_last_priority_swap"):
                self._last_priority_swap = 0
            if now - self._last_priority_swap < 1.0:
                return

            self._log(f"Priority Sniper: Found {best_bench_champ}! Swapping...")
            self.lcu.request("POST", f"/lol-champ-select/v1/session/bench/swap/{best_bench_id}")
            self._last_priority_swap = now

    def _handle_standard_session(self, session):
        me = self._get_local_player(session)
        if not me:
            return

        assigned_role = me.get("assignedPosition", "").upper()
        local_cell_id = session.get("localPlayerCellId")

        # 3. Apply Loadouts (Once per lobby)
        self._apply_loadout(me, assigned_role)

        # 3b. Auto Spells - DISABLED
        # if self.config.get("auto_spells"):
        #     self._set_spells_for_role(assigned_role)

        # 4. Pick & Ban Logic
        self._process_actions(session, local_cell_id, assigned_role)

    def _get_champ_select_session(self):
        try:
            req = self.lcu.get_champ_select_session()
            if req and req.status_code == 200:
                return req.json()
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        return None

    def _get_local_player(self, session):
        local_cell_id = session.get("localPlayerCellId")
        my_team = session.get("myTeam", [])
        return next((p for p in my_team if p["cellId"] == local_cell_id), None)

    def _apply_loadout(self, me, _assigned_role):
        if self.setup_done:
            return

        champ_id = me.get("championId")
        if champ_id and champ_id > 0:
            champ_name = self.assets.get_champ_name(champ_id)

            # 1. Find which config slot this champion belongs to (Reverse Lookup)
            # We check "pick_{ROLE}_{1-3}" and "arena_pick_{1-3}"
            found_rune_page_name = None

            # Check Roles
            roles = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
            for r in roles:
                for i in range(1, 4):
                    key = f"pick_{r}_{i}"
                    if self.config.get(key) == champ_name:
                        # Found it! Check for bound rune page
                        found_rune_page_name = self.config.get(f"rune_{key}")
                        break
                if found_rune_page_name:
                    break

            # Check Arena
            if not found_rune_page_name:
                for i in range(1, 4):
                    key = f"arena_pick_{i}"
                    if self.config.get(key) == champ_name:
                        found_rune_page_name = self.config.get(f"rune_{key}")
                        break

            # Apply Runes if found & enabled
            if found_rune_page_name and self.config.get("auto_runes"):
                self.runes.apply_saved_page(found_rune_page_name)
                self._log(
                    f"Setup: Applied bound page '{found_rune_page_name}' for {champ_name}"
                )

            # Always equip a random owned skin
            self._handle_skin_random()

            self.setup_done = True

    def _perform_sniper(self, session):
        """Unified logic to swap for targets in Any Random Mode (ARAM, ARURF)"""
        if not self.config.get("auto_aram_swap"):
            return

        bench = session.get("benchChampions", [])
        if not bench:
            return

        # Get targets from config
        targets = set()

        # 1. Dedicated ARAM Targets
        for i in range(1, 9):
            t = self.config.get(f"aram_target_{i}")
            if t:
                cid = self.assets.get_champ_id(t)
                if cid:
                    targets.add(cid)

        if not targets:
            return

        # 2. Check if we ALREADY hold a target — don't swap away from it
        me = self._get_local_player(session)
        if me:
            my_champ = me.get("championId", 0)
            if my_champ in targets:
                Logger.debug("Sniper", f"Already holding target {my_champ}. Staying.")
                return

        # 3. Scan Bench for targets
        for champ in bench:
            cid = champ.get("championId")
            if cid in targets:
                self._log(f"Sniper: Found target {cid} on bench! Swapping...")
                self.lcu.request(
                    "POST", f"/lol-champ-select/v1/session/bench/swap/{cid}"
                )
                return  # One action per tick

    def _process_actions(self, session, local_cell_id, assigned_role):
        # NOTE: No "MASTER PICK" check. If Power is ON, picks work.

        actions = session.get("actions", [])
        picks = self._get_pick_preferences(assigned_role, session)
        ban_name = self._get_ban_preference(assigned_role, session)

        # Debug: Log what we're working with (once per champ select, not every tick)
        pick_ban_key = f"{assigned_role}:{picks}:{ban_name}"
        if (picks or ban_name) and getattr(self, '_last_pick_ban_log', None) != pick_ban_key:
            self._log(
                f"[ChampSelect] Role: {assigned_role}, Picks: {picks}, Ban: {ban_name}"
            )
            self._last_pick_ban_log = pick_ban_key

        if not picks and not ban_name:
            return

        # Check if banning phase is complete (all ban actions done)
        all_bans_complete = True
        for action_group in actions:
            for action in action_group:
                if action["type"] == "ban" and not action["completed"]:
                    all_bans_complete = False
                    break
            if not all_bans_complete:
                break

        for action_group in actions:
            for action in action_group:
                if action["actorCellId"] != local_cell_id:
                    continue
                if action["completed"]:
                    continue

                if action["type"] == "pick":
                    # Allow picking logic (hovering) even during bans
                    # Lock-in protection is handled inside _perform_pick_action
                    self._perform_pick_action(action, picks, session)
                elif action["type"] == "ban":
                    self._perform_ban_action(action, ban_name, session)

    def _get_pick_preferences(self, role, session=None):
        picks = []

        # 1. Detection
        is_arena = False
        # Method A: Check stored Queue ID
        if self.current_queue_id == 1700:
            is_arena = True
        # Method B: Fallback to Team Size
        elif session:
            my_team = session.get("myTeam", [])
            if len(my_team) == 2:
                is_arena = True

        # 2. Priority: Arena
        if is_arena:
            for i in range(1, 4):
                p = self.config.get(f"arena_pick_{i}")
                if p:
                    picks.append(p)
            if picks:
                self._log(
                    f"Mode: Arena (ID: {self.current_queue_id}). Using Arena Picks: {picks}"
                )
                return picks

        # 3. Priority: Role Specific
        if role in ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]:
            for i in range(1, 4):
                p = self.config.get(f"pick_{role}_{i}")
                if p:
                    picks.append(p)
            if picks:
                self._log(f"Role Detected: {role}. Using Picks: {picks}")
                return picks

        # 4. Fallback: Generic auto_pick (for draft/blind/unknown roles)
        for key in ["auto_pick", "auto_pick_2", "auto_pick_3"]:
            p = self.config.get(key)
            if p:
                picks.append(p)
        if picks:
            self._log(f"No role match. Fallback picks: {picks}")
        return picks

    def _get_ban_preference(self, role, session=None):
        # Detect Arena
        is_arena = False
        if self.current_queue_id == 1700:
            is_arena = True
        elif session:
            my_team = session.get("myTeam", [])
            if len(my_team) == 2:
                is_arena = True

        # Arena Bans
        if is_arena:
            for i in range(1, 4):
                b = self.config.get(f"arena_ban_{i}")
                if b:
                    return b

        # Role Bans
        if role in ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]:
            b = self.config.get(f"ban_{role}")
            if b:
                return b

        # Fallback: Generic auto_ban
        return self.config.get("auto_ban")

    def _perform_pick_action(self, action, picks, session):
        # 1. Panic Mode Check (Timer < 10s)
        # adjustedTimeLeftInPhase is in milliseconds
        timer = session.get("timer", {}).get("adjustedTimeLeftInPhase", 20000)
        is_panic = timer < 10000  # 10 seconds
        
        # Check if it is actually our turn to act
        # Check if it is actually our turn to act
        is_turn = action.get("isInProgress", False)
        
        # Get local cell ID to prevent self-blocking
        local_cell_id = session.get("localPlayerCellId", -1)

        # 2. Use picks directly (no special handling)
        final_picks = picks

        # 3. Execution Loop
        for pname in final_picks:
            cid = self.assets.get_champ_id(pname)
            if not cid:
                continue

            # Check availability
            # TRUST HOVER: If we are already hovering this champion, we still need to check if it was
            # taken by someone else (e.g. enemy picked it during our delay).
            # _is_available explicitly ignores our own selection, so it is safe to call.
            if not self._is_available(cid, session, local_cell_id):
                self._log(f"Skipping {pname} - Not Available (Banned/Picked)")
                # If we were hovering it but it's now gone, reset hover state
                if self.pick_hover_cid == cid:
                    self.pick_hover_cid = None
                    self.pick_hover_time = None
                continue

            # Special handling for Bravery/Random (negative IDs)
            # These pseudo-champions need direct PATCH with completed:true
            if cid < 0 and is_turn:
                self._log(f"[Bravery Mode] Attempting to select with ID: {cid}")
                r = self.lcu.action_champ_select(action["id"], cid, complete=True)
                if r and r.status_code in (200, 204):
                    self._log(
                        f"[Bravery Mode] Selection sent. Response: {r.status_code}"
                    )
                    # Check if it actually worked by getting new session
                    return  # Exit and let next cycle verify
                else:
                    self._log(
                        f"[Bravery Mode] Failed: {r.status_code if r else 'None'}"
                    )
                continue

            # Normal champion selection flow
            # Check if we're already hovering this champion
            if self.pick_hover_cid != cid:
                # Check for INSTANT LOCK (0s delay)
                is_instant = self.config.get("auto_lock_in", True) and self.pick_delay <= 0.05

                if is_instant and is_turn:
                    # Lock immediately
                    r = self.lcu.action_champ_select(action["id"], cid, complete=True)
                    if r and r.status_code in (200, 204):
                        self._log(f"Instant Lock: {pname}")
                        self.pick_hover_cid = None
                        self.pick_hover_time = None
                        return

                # New champion - hover it and start timer
                self.lcu.action_champ_select(action["id"], cid, complete=False)
                self.pick_hover_cid = cid
                self.pick_hover_time = time.time()

                if self.config.get("auto_lock_in", True):
                    self._log(f"Hovering {pname} - will lock in {self.pick_delay}s")
                else:
                    self._log(f"Hovering {pname} (Auto-Lock Disabled)")
                return  # Wait for next cycle

            # IF NOT OUR TURN, STOP HERE (Hovered, but can't lock)
            if not is_turn:
                return

            # Check if enough time has passed (or panic mode)
            elapsed = time.time() - (self.pick_hover_time or time.time())
            if elapsed < self.pick_delay and not is_panic:
                remaining = self.pick_delay - elapsed
                # Only log every few seconds to reduce spam
                if int(remaining) % 3 == 0 and self.config.get("auto_lock_in", True):
                    self._log(f"Waiting {remaining:.0f}s before locking {pname}...")
                return  # Keep waiting

            # Lock In Check
            if self.config.get("auto_lock_in", True):
                r = self.lcu.action_champ_select(action["id"], cid, complete=True)
                if r and r.status_code in (200, 204):
                    self._log(f"Auto Picked & Locked: {pname}")
                    self.pick_hover_cid = None  # Reset for next game
                    self.pick_hover_time = None
                    return
                else:
                    self._log(
                        f"Failed to Lock {pname} (Status: {r.status_code if r else 'None'}). Retrying..."
                    )
                    if is_panic:
                        self._log("PANIC: Forced Lock-In Attempted!")
                        return  # Prevent switching to next pick in panic
            else:
                # Auto-Lock is OFF. We just sit here.
                # If timer < 5s, we break to allow Ultimate Panic logic to run as a safety net.
                if is_panic and timer < 5000:
                    self._log("PANIC: Auto-Lock disabled but time critical! Falling through to emergency lock.")
                    break
                return

        # 4. Ultimate Panic: If timer < 5s and nothing locked, lock whatever is hovered?
        if timer < 5000 and not action.get("completed"):
            hover_id = action.get("championId")
            if hover_id and hover_id != 0:
                self.lcu.action_champ_select(action["id"], hover_id, complete=True)
                self._log("EMERGENCY LOCK: Locked hovered champion!")

    def _perform_ban_action(self, action, ban_name, session=None):
        if not ban_name:
            return
        cid = self.assets.get_champ_id(ban_name)
        if cid:
            self.lcu.action_champ_select(action["id"], cid, complete=True)
            self._log(f"Auto Banned: {ban_name}")

    def _is_available(self, c_id, session, local_cell_id=-1):
        # Special pseudo-champions are always available
        if c_id in [-3, 0]:  # Bravery (-3), Random (0)
            return True

        # 1. Check Bans
        bans = session.get("bans", {})
        my_bans = bans.get("myTeamBans", [])
        their_bans = bans.get("theirTeamBans", [])

        if c_id in my_bans or c_id in their_bans:
            Logger.debug("Availability", f"Champion {c_id} is BANNED.")
            return False

        # 2. Check Picks (Already picked by someone else)
        all_players = (session.get("myTeam", []) or []) + (
            session.get("theirTeam", []) or []
        )
        for p in all_players:
            # Skip ourselves (if we are hovering, it shows as picked in session sometimes)
            p_cell = p.get("cellId")
            if p_cell == local_cell_id:
                continue
                
            if p.get("championId") == c_id:
                Logger.debug("Availability", f"Champion {c_id} is already PICKED by Cell {p_cell} (We are {local_cell_id}).")
                return False

        return True

    def _handle_skin_random(self):
        """V10: Randomly select an owned skin."""
        if not self.config.get("auto_random_skin"):
            return

        skins_req = self.lcu.request("GET", "/lol-champ-select/v1/skin-selector-info")
        if not skins_req or skins_req.status_code != 200:
            return

        data = skins_req.json()
        available = data.get("selectedChampionId", 0)  # pylint: disable=unused-variable
        skins = [s for s in data.get("skins", []) if s.get("unlocked", False)]

        if not skins:
            return

        # Pick a random skin
        chosen = random.choice(skins)
        skin_id = chosen.get("id")

        if skin_id:
            self.lcu.request(
                "PATCH",
                "/lol-champ-select/v1/session/my-selection",
                {"selectedSkinId": skin_id},
            )
            self._log(f"Skin Randomizer: Selected Skin ID {skin_id}")

    def _handle_auto_honor(self, phase):
        # 1. Check Config
        if not self.config.get("auto_honor", True):
            return

        # 2. Check Phase & State
        if phase != "PreEndOfGame":
            self.has_honored = False
            return

        if self.has_honored:
            return

        # 3. Get Ballot
        ballot = self.lcu.request("GET", "/lol-honor-v2/v1/ballot")
        if not ballot or ballot.status_code != 200:
            return

        data = ballot.json()
        players = data.get("eligiblePlayers", [])
        if not players:
            return

        # 4. Honor Random Player
        target = random.choice(players)
        summoner_id = target.get("summonerId")

        if summoner_id:
            # Honor Categories: 'COOL' (Chill), 'SHOTCALLER' (Leadership), 'HEART' (GG)
            honor_type = random.choice(["COOL", "SHOTCALLER", "HEART"])

            payload = {"summonerId": summoner_id, "honorCategory": honor_type}
            r = self.lcu.request("POST", "/lol-honor-v2/v1/honor-player", payload)
            if r and r.status_code == 200:
                self._log(
                    f"Auto Honor: Honored Summoner ID {summoner_id} ({honor_type})"
                )
                self.has_honored = True

    def _track_session_stats(self, phase):
        # Only check periodically? Loop is 3s. LCU requests are fast.
        # Check phase first
        if phase != "EndOfGame":
            self._end_of_game_handled = False
            return

        # Optimization: If we already processed this session, skip
        if getattr(self, "_end_of_game_handled", False):
            return

        # Check History
        try:
            # Get last 1 game
            # ?begIndex=0&endIndex=1
            r = self.lcu.request(
                "GET", "/lol-match-history/v1/games?begIndex=0&endIndex=1"
            )
            if not r or r.status_code != 200:
                return

            games = r.json().get("games", [])
            if not games:
                return

            last_game = games[0]
            gid = last_game.get("gameId")

            # If this is a new game we haven't tracked yet
            if gid and gid != self.last_game_id:
                self.last_game_id = gid
                self._end_of_game_handled = True

                # Determine Win/Loss
                # We need local player participant ID?
                # Actually, 'participants' list. We need to find 'participantId' from 'participantIdentities'.

                # Check outcome
                # Simplify: Look for local player in participants?
                # The response structure usually has participantIdentities.

                pid = None
                # Get current summoner to match
                summ = self.lcu.get_summoner_current_summoner()
                if summ and summ.status_code == 200:
                    my_puuid = summ.json().get("puuid")

                    # Find participant ID
                    for p in last_game.get("participantIdentities", []):
                        if p.get("player", {}).get("puuid") == my_puuid:
                            pid = p.get("participantId")
                            break

                    if pid:
                        # Find stats
                        for p in last_game.get("participants", []):
                            if p.get("participantId") == pid:
                                win = p.get("stats", {}).get("win", False)
                                key = "wins" if win else "losses"
                                self.session_stats[key] += 1
                                self.session_stats["games"] += 1
                                self._log(
                                    f"Session Stats Updated: {self.session_stats}"
                                )
                                break
        except Exception as e:  # pylint: disable=broad-exception-caught
            self._log(f"Stats Error: {e}")

    def _set_spells_for_role(self, role):
        if self.setup_done:
            return

        # Summoner Spell IDs
        spell_ids = {
            "FLASH": 4,
            "IGNITE": 14,
            "SMITE": 11,
            "HEAL": 7,
            "EXHAUST": 3,
            "TELEPORT": 12,
            "GHOST": 6,
            "BARRIER": 21,
            "CLEANSE": 1,
        }

        # Default Mapping (Flash on D=1, Spec on F=2)
        spell1, spell2 = spell_ids["FLASH"], spell_ids["IGNITE"]  # Default Mid/General

        if role == "JUNGLE":
            spell1, spell2 = spell_ids["FLASH"], spell_ids["SMITE"]
        elif role == "TOP":
            spell1, spell2 = spell_ids["FLASH"], spell_ids["TELEPORT"]
        elif role == "BOTTOM":
            spell1, spell2 = spell_ids["FLASH"], spell_ids["HEAL"]
        elif role == "UTILITY":
            spell1, spell2 = spell_ids["FLASH"], spell_ids["EXHAUST"]

        self.lcu.request(
            "PATCH",
            "/lol-champ-select/v1/session/my-selection",
            {"spell1Id": spell1, "spell2Id": spell2},
        )
        self._log(f"Auto Spells: Set Spells for {role}")
