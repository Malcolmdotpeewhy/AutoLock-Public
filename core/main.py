"""
AutoLock (Zero-G Edition)
Main Application Module
"""
import ctypes
import math
import os
import sys
import threading
import time
import tkinter
import traceback

import customtkinter as ctk
import keyboard
import psutil
from PIL import Image

from services.api_handler import LCUClient
from services.asset_manager import AssetManager, ConfigManager
from services.automation import AutomationEngine
from utils.logger import Logger
from utils.path_utils import resource_path
from ui.tab_auto import MainDashboard

from ui.tab_runes import RunePageBuilder
from ui.tab_tools import ToolsTab
from ui.components.factory import (
    get_color, get_font, TOKENS, make_panel, parse_border
)
from ui.components.color_utils import interpolate_color
from ui.ui_shared import CTkTooltip


def is_admin():
    """Check if the script is running with administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:  # pylint: disable=broad-exception-caught
        return False


ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")


class SoundManager:  # pylint: disable=too-few-public-methods
    """Manages application sound effects."""

    @staticmethod
    def play(sound_type):
        """Play a sound effect."""
        _ = sound_type  # User requested silence
        # pass


class LeagueAgentApp(ctk.CTk):
    """Main Application Class."""

    def __init__(self):
        super().__init__()
        self.title("AutoLock")
        
        # Initialize Managers FIRST to read geometry
        self.config = ConfigManager()
        self.assets = AssetManager()
        self.lcu = LCUClient()
        # Extract saved geometry or use default
        saved_geo = self.config.get("window_geometry", "1100x800")
        self.geometry(saved_geo)
        
        self.configure(fg_color=get_color("colors.background.app"))
        
        # Set Icon
        try:
            # PRIORITIZE: Custom Branding
            icon_ico = resource_path("assets/autolock.ico")
            icon_png = resource_path("assets/autolock.png")
            
            if os.path.exists(icon_ico):
                self.iconbitmap(icon_ico)
            elif os.path.exists(icon_png):
                icon_img = tkinter.PhotoImage(file=icon_png)
                self.iconphoto(False, icon_img)
        except Exception:
            pass
        self.sounds = SoundManager()

        self.running = True
        self.current_phase = None  # Track phase for optimizations
        self._game_pid = None  # Cached PID for League of Legends.exe

        # UI Components - defined here to satisfy pylint
        self.sidebar = None
        self.content_area = None
        self.views = {}
        self.img_on = None
        self.img_off = None
        self.power_state = False
        self.anim_running = False
        self.btn_power = None
        self.nav_buttons = {}
        self.status_indicator = None
        self.lbl_status = None
        self.btn_help = None
        self.lbl_action = None
        self.automation = None
        self._anim_frames = []
        self._compact_mode = False
        self._full_geometry = None
        self._compact_hotkey = self.config.get("hotkey_compact_mode", "ctrl+shift+m")

        self.setup_ui()

        # Automation - Must happen AFTER setup_ui so status bar exists
        self.init_automation()

        # --- Global Hotkey ---
        self._hotkey_binding = self.config.get("hotkey_find_match", "ctrl+shift+f")
        try:
            keyboard.add_hotkey(self._hotkey_binding, self._hotkey_find_match, suppress=False)
            Logger.debug("SYS", f"Hotkey registered: {self._hotkey_binding} → Find Match")
        except Exception:  # pylint: disable=broad-exception-caught
            Logger.debug("SYS", "Failed to register hotkey")

        # Compact mode hotkey
        try:
            keyboard.add_hotkey(self._compact_hotkey, lambda: self.after(0, self.toggle_compact_mode), suppress=False)
            Logger.debug("SYS", f"Hotkey registered: {self._compact_hotkey} → Compact Mode")
        except Exception:  # pylint: disable=broad-exception-caught
            Logger.debug("SYS", "Failed to register compact hotkey")

        # Launch client hotkey
        self._launch_hotkey = self.config.get("hotkey_launch_client", "ctrl+shift+l")
        try:
            keyboard.add_hotkey(self._launch_hotkey, self._hotkey_launch_client, suppress=False)
            Logger.debug("SYS", f"Hotkey registered: {self._launch_hotkey} → Launch Client")
        except Exception:  # pylint: disable=broad-exception-caught
            Logger.debug("SYS", "Failed to register launch hotkey")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.sounds.play("connect")
        self.assets.start_loading()
        threading.Thread(target=self.connection_loop, daemon=True).start()
        threading.Thread(target=self._window_monitor, daemon=True).start()

    def _hotkey_find_match(self):
        """Global hotkey handler — triggers Find Match from any window."""
        def _do():
            # Switch to dashboard if not already there
            self.switch_view("dashboard")
            # Start queue + automation
            if "dashboard" in self.views:
                self.views["dashboard"].start_queue()
            # Sync power button ON
            if not self.power_state:
                self.toggle_power(force_state=True)
        self.after(0, _do)  # Thread-safe: keyboard callback runs in its own thread

    def _hotkey_launch_client(self):
        """Global hotkey handler — triggers League Client Launch from any window."""
        def _do():
            self.switch_view("tools")
            if "tools" in self.views:
                self.views["tools"].launch_client()
        self.after(0, _do)

    def toggle_compact_mode(self):
        """Toggle between full UI and compact (icon-only) mode."""
        if self._compact_mode:
            # --- RESTORE FULL MODE ---
            self._compact_mode = False
            self.attributes("-topmost", False)
            self.overrideredirect(False)

            # Restore sidebar + content
            self.sidebar.grid()
            self.content_area.grid()
            if hasattr(self, "_compact_frame"):
                self._compact_frame.destroy()

            # Restore geometry
            if self._full_geometry:
                self.geometry(self._full_geometry)
            else:
                self.geometry("1100x800")

            self.update_action_log("Restored Full Mode")
        else:
            # --- ENTER COMPACT MODE ---
            self._compact_mode = True
            self._full_geometry = self.geometry()  # Save current geometry

            # Hide sidebar + content
            self.sidebar.grid_remove()
            self.content_area.grid_remove()

            # Create compact view — just the icon
            self._compact_frame = ctk.CTkFrame(
                self, fg_color=get_color("colors.background.app"),
                corner_radius=0,
            )
            self._compact_frame.grid(row=0, column=0, columnspan=2, sticky="nsew")

            # Use power icon (active if ON, idle if OFF)
            compact_icon = self.img_on if self.power_state else self.img_off
            compact_text = "" if compact_icon else "⏻"

            btn_compact = ctk.CTkButton(
                self._compact_frame,
                text=compact_text,
                image=compact_icon,
                font=("Arial", 28, "bold"),
                width=120,
                height=120,
                corner_radius=60,
                fg_color="transparent",
                hover_color=get_color("colors.state.hover"),
                command=self.toggle_compact_mode,  # Single click → restore
            )
            btn_compact.place(relx=0.5, rely=0.5, anchor="center")
            CTkTooltip(btn_compact, f"Click to restore  |  {self._compact_hotkey}")

            # Shrink + always-on-top + borderless
            self.geometry("140x140")
            self.attributes("-topmost", True)
            self.overrideredirect(True)

            # Allow dragging the compact window
            self._compact_frame.bind("<ButtonPress-1>", self._compact_drag_start)
            self._compact_frame.bind("<B1-Motion>", self._compact_drag_move)

            self.update_action_log("Compact Mode")

    def _compact_drag_start(self, event):
        """Record drag start position."""
        self._drag_x = event.x
        self._drag_y = event.y

    def _compact_drag_move(self, event):
        """Move the compact window via drag."""
        x = self.winfo_x() + event.x - self._drag_x
        y = self.winfo_y() + event.y - self._drag_y
        self.geometry(f"140x140+{x}+{y}")


    def _on_close(self):
        """Clean shutdown."""
        try:
            keyboard.unhook_all()
        except Exception:  # pylint: disable=broad-exception-caught
            pass
            
        # Save Geometry (unless in compact mode)
        if not getattr(self, "_compact_mode", False):
            self.config.set("window_geometry", self.geometry())
            
        self.running = False
        self.destroy()

    def _window_monitor(self):
        """Monitors game state and window state to toggle Always on Top."""
        _was_in_game = False
        while self.running:
            try:
                game_running = self._is_game_running()

                if game_running:
                    # CRITICAL: Do NOT touch window attributes while game is running.
                    # Toggling -topmost during gameplay can cause League's DirectX
                    # renderer to lose focus and fail to reacquire the display surface.
                    if not _was_in_game:
                        # Game just started — auto-minimize AutoLock to avoid z-order fights
                        self.after(0, lambda: self.iconify())
                        _was_in_game = True
                else:
                    if _was_in_game:
                        # Game just ended — restore AutoLock
                        self.after(0, lambda: self.deiconify())
                        _was_in_game = False

                    # Only manage topmost when NOT in game
                    is_minimized = self.state() == "iconic"
                    if self.config.get("always_on_top", True):
                        topmost = not is_minimized and not self._compact_mode
                        self.after(0, lambda t=topmost: self.attributes("-topmost", t))
                    else:
                        self.after(0, lambda: self.attributes("-topmost", False))

            except Exception:  # pylint: disable=broad-exception-caught
                pass
            time.sleep(5.0)


    def _is_game_running(self):
        """
        Check if League of Legends game process is running.
        Optimized with phase heuristic + cached PID to avoid full iteration.
        """
        # OPTIMIZATION 1: If connected to LCU, use gameflow phase as heuristic
        if self.lcu.is_connected:
            safe_phases = [
                "Lobby", "Matchmaking", "ReadyCheck",
                "ChampSelect", "PreEndOfGame", "None", None
            ]
            if self.current_phase in safe_phases:
                return False

        # OPTIMIZATION 1.5: Ultra-fast Win32 Window Check 
        try:
            # Native OS check is O(1) and catches the game the moment it is visible
            if ctypes.windll.user32.FindWindowW(None, "League of Legends (TM) Client") != 0:
                return True
        except Exception:
            pass

        # OPTIMIZATION 2: Fast path — check cached PID (O(1) instead of O(n))
        if self._game_pid:
            try:
                proc = psutil.Process(self._game_pid)
                if proc.is_running() and proc.name() == 'League of Legends.exe':
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            self._game_pid = None  # Stale, clear cache

        # OPTIMIZATION 3: Rate Limited Fallback
        # Full process list scan is expensive. Rate limit to once every 15s.
        now = time.time()
        if not hasattr(self, "_last_full_scan"):
            self._last_full_scan = 0
            
        if now - self._last_full_scan < 15.0:
            return False
            
        self._last_full_scan = now

        # Fallback: Full process list scan (Expensive, only when no cached PID)
        try:
            for proc in psutil.process_iter(['name']):
                if proc.info['name'] == 'League of Legends.exe':
                    self._game_pid = proc.pid  # Cache for next check
                    return True
        except Exception:
            pass

        return False

    def setup_ui(self):
        """Initialize the User Interface."""
        # Cleanup (Prevent Duplication)
        if hasattr(self, "sidebar") and self.sidebar:
            try:
                self.sidebar.destroy()
            except Exception:  # pylint: disable=broad-exception-caught
                pass
        if hasattr(self, "content_area") and self.content_area:
            try:
                self.content_area.destroy()
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        # --- Layout Architecture ---

        # Grid: [ Sidebar (Fixed w=200) | Content (Expand) ]
        self.grid_columnconfigure(0, weight=0)  # Sidebar
        self.grid_columnconfigure(1, weight=1)  # Content
        self.grid_rowconfigure(0, weight=1)

        # --- Sidebar (Gradient + Depth) ---
        self.sidebar = ctk.CTkFrame(
            self, width=200, fg_color=get_color("colors.background.app"), corner_radius=0,
            border_width=0,
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        # Right-edge inner highlight (depth separator)
        self._sidebar_edge = ctk.CTkFrame(
            self.sidebar, width=1, fg_color=parse_border("subtle")[1],
        )
        self._sidebar_edge.place(relx=1.0, rely=0, relheight=1.0, anchor="ne")

        self._init_sidebar()

        # --- Content Area ---
        self.content_area = ctk.CTkFrame(
            self, fg_color=get_color("colors.background.app"), corner_radius=0,
            border_width=0,
        )
        self.content_area.grid(row=0, column=1, sticky="nsew")

        # --- Views (Stacked) ---
        self.views = {}

        # 1. Dashboard
        self.views["dashboard"] = MainDashboard(
            self.content_area, self.assets, self.config, self.lcu
        )

        # 2. Runes
        self.views["runes"] = RunePageBuilder(self.content_area, self.assets, self.lcu)

        # 3. Tools & System (Combined)
        self.views["tools"] = ToolsTab(self.content_area, self.lcu, self.assets, self.config)

        # Place all views in the same grid cell to stack them
        for view in self.views.values():
            view.grid(row=0, column=0, sticky="nsew")

        self.content_area.grid_columnconfigure(0, weight=1)
        self.content_area.grid_rowconfigure(0, weight=1)

        # Select Start View
        self.switch_view("dashboard")  # Changed to switch_view

    def init_automation(self):
        """Initialize the Automation Engine."""
        # Pass our UI logger
        self.automation = AutomationEngine(
            self.lcu,
            self.assets,
            self.config,
            log_func=self.update_action_log,
            stop_func=lambda: self.after(
                0, lambda: self.toggle_power(force_state=False)
            ),  # Verify thread safety
        )
        self.automation.start(start_paused=True)

        if "dashboard" in self.views:
            self.views["dashboard"].set_automation(self.automation)

    def _init_sidebar(self):
        # 1. Header (Logo / Power Switch)
        header = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        header.pack(fill="x", pady=(TOKENS.get("spacing.lg"), TOKENS.get("spacing.md")), padx=TOKENS.get("spacing.md"))

        # Load Status Icons
        self.img_off = None
        self.img_on = None
        try:
            idle_path = resource_path("assets/icon_idle.png")
            active_path = resource_path("assets/icon_active.png")
            
            if os.path.exists(idle_path):
                self.img_off = ctk.CTkImage(Image.open(idle_path), size=(110, 110))
            if os.path.exists(active_path):
                self.img_on = ctk.CTkImage(Image.open(active_path), size=(110, 110))
        except Exception:
            pass

        self.power_state = False

        init_img = self.img_off if self.img_off else None
        init_text = "⏻" if not init_img else ""

        self.btn_power = ctk.CTkButton(
            header,
            text=init_text,
            image=init_img,
            font=("Arial", 24, "bold"),
            width=110,
            height=110,
            corner_radius=55,
            border_width=0,
            fg_color="transparent",
            hover_color=get_color("colors.state.hover"),
            command=self.toggle_power,
        )
        self.btn_power.pack(anchor="center")
        CTkTooltip(self.btn_power, "System Status: Idle (Click to Activate)")

        # 2. Navigation (with active glow + hover)
        self.nav_buttons = {}
        self._nav_indicators = {}  # Left accent bars
        nav_container = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        nav_container.pack(fill="x", pady=(TOKENS.get("spacing.md"), TOKENS.get("spacing.lg")))

        self._create_nav_btn(nav_container, "DASHBOARD", "dashboard", True)
        self._create_nav_btn(nav_container, "RUNES & SPELLS", "runes")
        self._create_nav_btn(nav_container, "TOOLS & SYSTEM", "tools")

        # Compact mode button
        btn_compact = ctk.CTkButton(
            nav_container,
            text="▬  COMPACT MODE",
            font=get_font("caption"),
            fg_color="transparent",
            text_color=get_color("colors.text.muted"),
            hover_color=get_color("colors.state.hover"),
            anchor="w",
            height=28,
            corner_radius=TOKENS.get("radius.sm"),
            command=self.toggle_compact_mode,
        )
        btn_compact.pack(fill="x", padx=TOKENS.get("spacing.sm"), pady=(TOKENS.get("spacing.xs"), 0))
        CTkTooltip(btn_compact, f"Minimize to icon  |  {self._compact_hotkey}")

        # Section divider
        ctk.CTkFrame(
            self.sidebar, height=1, fg_color=parse_border("subtle")[1]
        ).pack(fill="x", padx=TOKENS.get("spacing.md"), pady=TOKENS.get("spacing.sm"))

        # 3. Status Footer (Elevated)
        footer = make_panel(
            self.sidebar,
            title=None,
            corner_radius=TOKENS.get("radius.sm"),
        )
        footer.pack(side="bottom", fill="x", padx=TOKENS.get("spacing.sm"), pady=TOKENS.get("spacing.sm"), ipady=TOKENS.get("spacing.xs"))
        
        # Connect/Help Row
        conn_row = ctk.CTkFrame(footer._content, fg_color="transparent")
        conn_row.pack(fill="x", padx=TOKENS.get("spacing.sm"), pady=(TOKENS.get("spacing.xs"), 0))

        self.status_indicator = ctk.CTkLabel(
            conn_row, text="●", font=("Arial", 14), text_color=get_color("colors.text.disabled"),
        )
        self.status_indicator.pack(side="left", padx=(0, TOKENS.get("spacing.xs")))

        self.lbl_status = ctk.CTkLabel(
            conn_row,
            text="DISCONNECTED",
            font=get_font("body"),
            text_color=get_color("colors.text.secondary"),
        )
        self.lbl_status.pack(side="left")

        # Help Button
        self.btn_help = ctk.CTkButton(
            conn_row,
            text="?",
            width=22,
            height=22,
            corner_radius=11,
            fg_color=get_color("colors.background.panel"),
            hover_color=get_color("colors.accent.primary"),
            font=get_font("body"),
            border_width=1,
            border_color=parse_border("subtle")[1],
            command=lambda: self.switch_view("info"),
        )
        self.btn_help.pack(side="right")
        CTkTooltip(self.btn_help, "Open Help & Info")

        # Action Row (Logs)
        self.lbl_action = ctk.CTkLabel(
            footer,
            text="Idle...",
            font=get_font("caption"),
            text_color=get_color("colors.text.muted"),
            anchor="w",
        )
        self.lbl_action.pack(fill="x", padx=TOKENS.get("spacing.md"), pady=(0, TOKENS.get("spacing.xs")))

        # Malcolm: UX-enhanced Matchmaking Progress Flair
        self.bar_action_progress = ctk.CTkProgressBar(
            footer, height=4, fg_color=get_color("colors.background.panel"), progress_color=get_color("colors.accent.gold")
        )
        self.bar_action_progress.set(0)
        self.bar_action_progress.pack_forget()
        self._ready_total_time = None

        self._precompute_animation()

    def _precompute_animation(self):
        """Pre-calculate animation frames."""
        self._anim_frames = []
        steps = 42
        for i in range(steps):
            pulse = (math.sin(i * 0.15) + 1) / 2

            # Image Scale (110 -> 118)
            scale = int(110 + (8 * pulse))

            # Border Color
            c_glow = self._interpolate_color(
                get_color("colors.accent.primary"), get_color("colors.accent.gold"), pulse
            )
            # Background Glow
            glow_color = interpolate_color("#000000", "#15803d", pulse)

            self._anim_frames.append((scale, c_glow, glow_color))

    def _interpolate_color(self, c1, c2, factor):
        """Interpolate between two hex colors."""
        try:
            r1 = int(c1[1:3], 16)
            g1 = int(c1[3:5], 16)
            b1 = int(c1[5:7], 16)

            r2 = int(c2[1:3], 16)
            g2 = int(c2[3:5], 16)
            b2 = int(c2[5:7], 16)

            r = int(r1 + (r2 - r1) * factor)
            g = int(g1 + (g2 - g1) * factor)
            b = int(b1 + (b2 - b1) * factor)

            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:  # pylint: disable=broad-exception-caught
            return c1

    def toggle_power(self, force_state=None):
        """Toggle the automation power state."""
        try:
            if not self.winfo_exists() or not getattr(self, "btn_power", None) or not self.btn_power.winfo_exists():
                return
        except Exception:
            return

        if force_state is not None:
            self.power_state = force_state
        else:
            self.power_state = not self.power_state

        if self.power_state:
            # Turned ON
            try:
                self.btn_power.configure(border_width=2)
                if self.img_on:
                    self.btn_power.configure(image=self.img_on, text="")
                else:
                    self.btn_power.configure(fg_color=get_color("colors.state.success"))

                self._start_animation()

                CTkTooltip(self.btn_power, "System: Active")
                self.update_action_log("System Enabled")
            except Exception:
                pass
            if hasattr(self, "automation") and self.automation:
                self.automation.resume()
        else:
            # Turned OFF
            # Smart Queue Cancel
            if self.lcu and self.lcu.is_connected:
                try:
                    # Check if searching
                    s_req = self.lcu.request(
                        "GET", "/lol-lobby/v2/lobby/matchmaking/search-state"
                    )
                    if s_req and s_req.status_code == 200:
                        if s_req.json().get("searchState") == "Searching":
                            self.update_action_log("Stopping Matchmaking...")
                            self.lcu.request(
                                "DELETE", "/lol-lobby/v2/lobby/matchmaking/search"
                            )
                except Exception:  # pylint: disable=broad-exception-caught
                    pass

            self.anim_running = False  # Stop Anim
            try:
                self.btn_power.configure(border_width=0)
                if self.img_on:
                    self.img_on.configure(size=(110, 110))

                self.btn_power.configure(border_color=get_color("colors.state.hover"))
                if self.img_off:
                    self.btn_power.configure(image=self.img_off, text="", fg_color="transparent")
                else:
                    self.btn_power.configure(fg_color=get_color("colors.state.danger"))

                CTkTooltip(self.btn_power, "System: Disabled")
                self.update_action_log("System Disabled")
            except Exception:
                pass
            if hasattr(self, "automation") and self.automation:
                self.automation.pause()

    def _start_animation(self):
        if self.anim_running:
            return
        self.anim_running = True
        self._animate_step(0)

    def _animate_step(self, step):
        try:
            if not self.winfo_exists() or not getattr(self, "btn_power", None) or not self.btn_power.winfo_exists():
                return
        except Exception:
            return

        if not self.power_state or not self.anim_running:
            self.btn_power.configure(border_color=get_color("colors.state.hover"))
            return

        if not self._anim_frames:
            self._precompute_animation()  # Fallback just in case

        # OPTIMIZATION: Pause animation if In-Game
        # OPTIMIZATION: Pause animation if In-Game
        if self.lcu and self.lcu.is_connected:
            # We need to access the phase. The connection loop updates self.lbl_status
            # but that text has "CONNECTED: Phase".
            # Better to check automation.last_phase if available, or just skip if we feel like it.
            # Let's use the status label text as a proxy since it is updated by the connection loop.
            status_text = self.lbl_status.cget("text")
            if "InProgress" in status_text:
                self.after(5000, lambda: self._animate_step(step)) # Optimization: Very slow poll (5s)
                return

        # Use pre-computed frame
        scale, c_glow, glow_color = self._anim_frames[step % len(self._anim_frames)]

        # Only animate border color & glow - NO size changes to prevent layout shifts
        self.btn_power.configure(border_color=c_glow, fg_color=glow_color)

        self.after(50, lambda: self._animate_step(step + 1))

    def update_status(self, connected, phase=""):
        """Update the status indicator."""
        try:
            if not self.winfo_exists() or not getattr(self, "status_indicator", None) or not self.status_indicator.winfo_exists():
                return
            if connected:
                self.status_indicator.configure(text_color=get_color("colors.state.success"))
                self.lbl_status.configure(text=f"CONNECTED: {phase}" if phase else "ONLINE")
            else:
                self.status_indicator.configure(text_color=get_color("colors.text.disabled"))
                self.lbl_status.configure(text="DISCONNECTED")
        except Exception:
            pass

    def update_action_log(self, msg):
        """Update the action log label (Thread-Safe)."""
        def _update():
            try:
                if not self.winfo_exists() or not getattr(self, "lbl_action", None) or not self.lbl_action.winfo_exists():
                    return

                # Malcolm: UX-enhanced Matchmaking Progress Flair
                if msg.startswith("Auto Accept: Waiting"):
                    import re
                    match = re.search(r"Waiting ([\d.]+)s", msg)
                    if match:
                        self._ready_total_time = float(match.group(1))
                        self.bar_action_progress.set(0)
                        self.bar_action_progress.configure(progress_color=get_color("colors.accent.gold"))
                        self.bar_action_progress.pack(fill="x", padx=TOKENS.get("spacing.md"), pady=(0, TOKENS.get("spacing.sm")))
                elif msg.startswith("Auto Accept:") and "s..." in msg and getattr(self, "_ready_total_time", None):
                    import re
                    match = re.search(r"Auto Accept: (\d+)s", msg)
                    if match:
                        remaining = float(match.group(1))
                        progress = max(0.0, min(1.0, (self._ready_total_time - remaining) / self._ready_total_time))
                        self.bar_action_progress.set(progress)
                elif msg == "Auto Accept: Accepted!":
                    self.bar_action_progress.set(1.0)
                    self.bar_action_progress.configure(progress_color=get_color("colors.state.success"))
                    self.after(2000, lambda: self.bar_action_progress.pack_forget())
                    self._ready_total_time = None
                elif not msg.startswith("Auto Accept:"):
                    self.bar_action_progress.pack_forget()
                    self._ready_total_time = None

                text = msg
                if len(text) > 30:
                    text = text[:27] + "..."
                self.lbl_action.configure(text=text)
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        try:
            if self.winfo_exists():
                self.after(0, _update)
        except Exception:
            pass

        # 3. System Monitor (Bottom)
        self._init_monitor_panel()

    def _init_monitor_panel(self):
        """Create the system monitor panel at the bottom of the sidebar."""
        if hasattr(self, "monitor_frame") and self.monitor_frame:
             try:
                 self.monitor_frame.destroy()
             except Exception:
                 pass

        self.monitor_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.monitor_frame.pack(side="bottom", fill="x", padx=TOKENS.get("spacing.md"), pady=TOKENS.get("spacing.lg"))

        # LCU Status (Dot + Text)
        lcu_row = ctk.CTkFrame(self.monitor_frame, fg_color="transparent")
        lcu_row.pack(fill="x", pady=(0, TOKENS.get("spacing.sm")))
        
        self.lcu_dot = ctk.CTkLabel(lcu_row, text="●", font=("Arial", 16), text_color=get_color("colors.state.danger"))
        self.lcu_dot.pack(side="left", padx=(0, TOKENS.get("spacing.xs")))
        
        self.lbl_lcu = ctk.CTkLabel(
            lcu_row, text="LCU: Disconnected", font=get_font("caption"), text_color=get_color("colors.text.muted")
        )
        self.lbl_lcu.pack(side="left")

        # CPU
        self.lbl_cpu = ctk.CTkLabel(
            self.monitor_frame, text="CPU: 0%", font=("Consolas", 12, "bold"), text_color=get_color("colors.text.secondary"), anchor="w"
        )
        self.lbl_cpu.pack(fill="x", pady=(0, 2))
        self.bar_cpu = ctk.CTkProgressBar(
            self.monitor_frame, height=4, fg_color=get_color("colors.background.panel"), progress_color=get_color("colors.accent.primary")
        )
        self.bar_cpu.pack(fill="x", pady=(0, TOKENS.get("spacing.sm")))
        self.bar_cpu.set(0)

        # RAM
        self.lbl_ram = ctk.CTkLabel(
            self.monitor_frame, text="RAM: 0 MB", font=("Consolas", 12, "bold"), text_color=get_color("colors.text.secondary"), anchor="w"
        )
        self.lbl_ram.pack(fill="x", pady=(0, 2))
        self.bar_ram = ctk.CTkProgressBar(
            self.monitor_frame, height=4, fg_color=get_color("colors.background.panel"), progress_color=get_color("colors.state.warning")
        )
        self.bar_ram.pack(fill="x")
        self.bar_ram.set(0)

        # Cache process for performance
        if getattr(self, "_process", None) is None:
            self._process = psutil.Process(os.getpid())

        # Start Monitor Loop
        self.after(1000, self._update_monitor)

    def _update_monitor(self):
        """Update system stats in sidebar."""
        if not self.winfo_exists():
            return
        
        try:
            # System
            cpu = psutil.cpu_percent(interval=None)
            mem = self._process.memory_info().rss / 1024 / 1024
            
            self.lbl_cpu.configure(text=f"CPU: {int(cpu)}%")
            self.bar_cpu.set(cpu / 100)
            
            self.lbl_ram.configure(text=f"RAM: {int(mem)} MB")
            self.bar_ram.set(min(mem / 500, 1.0))
            
            # LCU
            if self.lcu.is_connected:
                self.lcu_dot.configure(text_color=get_color("colors.state.success"))
                self.lbl_lcu.configure(text="LCU: Connected", text_color=get_color("colors.state.success"))
            else:
                self.lcu_dot.configure(text_color=get_color("colors.state.danger"))
                self.lbl_lcu.configure(text="LCU: Offline", text_color=get_color("colors.text.muted"))
                
        except Exception:
            pass
            
        self.after(1000, self._update_monitor)

    def _create_nav_btn(self, parent, text, view_name, selected=False):
        # Row container for accent bar + button
        row = ctk.CTkFrame(parent, fg_color="transparent", height=40)
        row.pack(fill="x", padx=TOKENS.get("spacing.sm"), pady=2)
        row.pack_propagate(False)

        # Left accent indicator (visible when active)
        indicator = ctk.CTkFrame(
            row, width=3,
            fg_color=get_color("colors.accent.primary") if selected else "transparent",
            corner_radius=2,
        )
        indicator.pack(side="left", fill="y", padx=(0, TOKENS.get("spacing.xs")))
        self._nav_indicators[view_name] = indicator

        btn = ctk.CTkButton(
            row,
            text=text,
            font=get_font("body", "bold") if selected else get_font("body", "medium"),
            fg_color=get_color("colors.background.card") if selected else "transparent",
            text_color=get_color("colors.text.primary") if selected else get_color("colors.text.secondary"),
            hover_color=get_color("colors.state.hover"),
            anchor="w",
            height=36,
            corner_radius=TOKENS.get("radius.sm"),
            border_width=1 if selected else 0,
            border_color=parse_border("subtle")[1],
            command=lambda: self.switch_view(view_name),
        )
        btn.pack(side="left", fill="both", expand=True)
        self.nav_buttons[view_name] = btn

        tips = {
            "dashboard": "Dashboard: Auto-Queue, Pick/Ban & Arena Mode",
            "runes": "Rune Manager: Create Local Pages & Push to Client",
            "tools": "Toolbar: Lobby Management, Loot & Client Fixes",
            "info": "System: Health Monitor, App Info & Help Guide",
        }
        if view_name in tips:
            CTkTooltip(btn, tips[view_name])

    def switch_view(self, view_name):
        """Switch the main content view."""
        self.update_action_log(f"Opened {view_name.title()} View")

        for name, btn in self.nav_buttons.items():
            is_active = name == view_name
            btn.configure(
                fg_color=get_color("colors.background.card") if is_active else "transparent",
                text_color=get_color("colors.text.primary") if is_active else get_color("colors.text.secondary"),
                font=get_font("body", "bold") if is_active else get_font("body", "medium"),
                border_width=1 if is_active else 0,
                border_color=parse_border("subtle")[1],
            )
            # Update left accent indicator
            if name in self._nav_indicators:
                self._nav_indicators[name].configure(
                    fg_color=get_color("colors.accent.primary") if is_active else "transparent"
                )

        if view_name in self.views:
            self.views[view_name].tkraise()

    def connection_loop(self):
        """Background thread for LCU connection monitoring."""
        Logger.debug("SYS", "Connection Loop Started")
        
        fail_count = 0

        while self.running:
            # --- LCU Connection ---
            if self.lcu.is_connected:
                # Check Phase (Background)
                phase = ""
                try:
                    r = self.lcu.request("GET", "/lol-gameflow/v1/gameflow-phase")
                    if r and r.status_code == 200:
                        phase = r.json()
                except Exception:  # pylint: disable=broad-exception-caught
                    pass

                self.current_phase = phase  # Update internal state

                # Schedule UI Update (Thread Safe)
                self.after(0, lambda p=phase: self.update_status(True, p))

            else:
                self.after(0, lambda: self.update_status(False))
                
                # Pass silent=True so api_handler doesn't spam debug logs every 5s
                if self.lcu.connect(silent=True):
                    Logger.info("SYS", "LCU Connected successfully via background loop.")
                    fail_count = 0
                else:
                    fail_count += 1
                    # Log explicitly every 6th tick (~30s) to provide health proof without spam
                    if fail_count % 6 == 0:
                        Logger.warning("SYS", f"LCU Connection polling failed for {fail_count * 5}s. (Is the Riot Client open and verified?)")

            time.sleep(5)  # Poll every 5s in background (Doesn't freeze UI)


if __name__ == "__main__":
    # Admin Elevation Loop
    if not is_admin() and sys.platform == "win32":
        print("Requesting Administrator privileges...")
        import ctypes
        import sys
        import os
        
        # We need to maintain the PYTHONPATH correctly.
        # So we run cmd.exe /c "set PYTHONPATH=... && python -m core.main"
        working_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Quote paths to be safe with spaces
        cmd_args = f'/c "cd /d "{working_dir}" && set PYTHONPATH={working_dir} && "{sys.executable}" -m core.main"'
        
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "cmd.exe", cmd_args, working_dir, 1
        )
        
        if result <= 32:
            print(f"Failed to elevate privileges. ShellExecuteW returned error code: {result}")
        
        sys.exit()

    # Aggressive Singleton (Process Killer)
    try:
        LOCK_FILE = "app.lock"
        current_pid = os.getpid()

        if os.path.exists(LOCK_FILE):
            try:
                with open(LOCK_FILE, "r", encoding="utf-8") as f_lock:
                    old_pid = int(f_lock.read().strip())

                if old_pid != current_pid and psutil.pid_exists(old_pid):
                    print(f"Terminating old instance: {old_pid}")
                    proc = psutil.Process(old_pid)
                    proc.terminate()
                    time.sleep(1)
            except Exception as ex:  # pylint: disable=broad-exception-caught
                print(f"Cleanup warning: {ex}")

        with open(LOCK_FILE, "w", encoding="utf-8") as f_lock:
            f_lock.write(str(current_pid))

    except ImportError:
        print("psutil not found, skipping singleton enforcement.")

    try:
        app_instance = LeagueAgentApp()
        app_instance.mainloop()
    except Exception as e_crash:
        # traceback is imported at top level
        with open("crash_log.txt", "w", encoding="utf-8") as f_crash:
            f_crash.write(traceback.format_exc())
            print(traceback.format_exc())
        print("CRASHED:", e_crash)
