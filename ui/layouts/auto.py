"""
Dashboard Tab
Main control center for the agent.
"""
import json
import os
import subprocess
import threading
import time
from PIL import Image
from utils.path_utils import resource_path

import customtkinter as ctk
from ..ui_shared import (
    CTkTooltip, make_panel, make_button, make_input, 
    make_card, make_switch,
    apply_hover_brightness, lighten_color,
    get_font, get_color, parse_border, TOKENS, ToastManager
)


# pylint: disable=too-many-lines, too-many-ancestors, too-many-instance-attributes


class MainDashboard(ctk.CTkFrame):
    """Main Dashboard View."""

    def __init__(self, parent, asset_manager, config, lcu=None):
        super().__init__(parent, fg_color=get_color("colors.background.app"), corner_radius=0)
        self.asset_manager = asset_manager
        self.config = config
        self.lcu = lcu
        self.automation = None

        # UI Components
        self.header = None
        self.lbl_rank = None
        self.btn_launch = None
        self.frame_queue = None
        self.combo_queue = None
        self.btn_queue = None
        self.mode_toggle = None
        self.frame_auto = None
        self.lbl_delay = None
        self.slider_delay = None
        self.lbl_poll = None
        self.slider_poll = None
        self.view_container = None
        self.role_scroll = None
        self.btn_ban_ref = None

        # Setup Grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.content_wrapper = ctk.CTkFrame(self, fg_color="transparent")
        self.content_wrapper.grid(row=0, column=0, sticky="nsew")
        self.content_wrapper.grid_columnconfigure(0, weight=1)
        self.content_wrapper.grid_rowconfigure(0, weight=1)

        self.content = ctk.CTkFrame(self.content_wrapper, fg_color="transparent")
        self.content.grid(row=0, column=0, sticky="nsew", padx=TOKENS.get("spacing.lg"), pady=TOKENS.get("spacing.lg"))

        self.selector = None
        self._init_ui()

    def set_automation(self, automation):
        """Inject automation instance."""
        self.automation = automation
        if hasattr(self, 'exp_list') and hasattr(automation, 'pref_model'):
            self.exp_list.model = automation.pref_model
            self.exp_list.refresh()

    def _init_ui(self):
        # --- HEADER: Title + Launcher ---
        self.header = ctk.CTkFrame(
            self.content, fg_color="transparent",
        )
        self.header.pack(fill="x", pady=(0, TOKENS.get("spacing.sm")))

        ctk.CTkLabel(
            self.header,
            text="AUTOLOCK DASHBOARD",
            font=get_font("title"),
            text_color=get_color("colors.accent.gold"),
        ).pack(side="left")

        # Rank Display
        self.lbl_rank = ctk.CTkLabel(
            self.header, text="", font=get_font("body"), text_color=get_color("colors.text.secondary")
        )
        self.lbl_rank.pack(side="left", padx=TOKENS.get("spacing.md"), pady=TOKENS.get("spacing.xs"))

        # Launcher Button (Right aligned, elevated)
        self.btn_launch = make_button(
            self.header,
            text="LAUNCH CLIENT",
            style="secondary",
            width=130,
            command=self.launch_client,
        )
        self.btn_launch.pack(side="right")

        # Icon NEXT TO Launch Button
        try:
            logo_path = resource_path("assets/lol_logo.png")
            if os.path.exists(logo_path):
                # Calculate Aspect Ratio to prevent distortion
                pil_img = Image.open(logo_path)
                h_target = 48
                w_target = int((pil_img.width / pil_img.height) * h_target)
                
                icon_img = ctk.CTkImage(pil_img, size=(w_target, h_target)) 
                self.lbl_header_icon = ctk.CTkLabel(self.header, text="", image=icon_img)
                self.lbl_header_icon.pack(side="right", padx=(TOKENS.get("spacing.md"), TOKENS.get("spacing.xs")))
        except Exception:
            pass

        # Glow underline
        ctk.CTkFrame(
            self.content, height=1, fg_color=get_color("colors.accent.gold"), # Matched to header
        ).pack(fill="x", pady=(0, TOKENS.get("spacing.lg")))

        # Init Dashboard Widgets
        self._init_dashboard_ui()

        # Start Rank Poller
        self.update_rank_display()

    def update_rank_display(self):
        """Polls rank and session stats."""
        if self.lcu and self.lcu.is_connected:

            def _worker():
                # 1. Auto-Switch Mode Logic
                try:
                    # Get queue ID from Automation Engine if available, or fetch
                    qid = None
                    if self.automation:
                        qid = self.automation.current_queue_id

                    if not qid:
                        # Fallback fetch
                        l_req = self.lcu.request("GET", "/lol-lobby/v2/lobby")
                        if l_req and l_req.status_code == 200:
                            qid = l_req.json().get("gameConfig", {}).get("queueId")

                    if qid:
                        current_tab = self.current_mode
                        target_tab = None

                        if qid == 1700 and current_tab != "ARENA MODE":
                            target_tab = "ARENA MODE"
                        elif qid == 450 and current_tab != "ARAM MODE":
                            target_tab = "ARAM MODE"
                        elif (
                            qid in [400, 420, 430, 440]
                            and current_tab != "SUMMONER'S RIFT"
                        ):
                            target_tab = "SUMMONER'S RIFT"

                        if target_tab:
                            self.after(0, lambda t=target_tab: self.switch_game_mode(t))
                except Exception:  # pylint: disable=broad-exception-caught
                    pass

                # 2. Check Phase first (Fast)
                try:
                    phase_req = self.lcu.request(
                        "GET", "/lol-gameflow/v1/gameflow-phase"
                    )
                    if phase_req and phase_req.status_code == 200:
                        phase = phase_req.json()
                        # Only fetch heavy stats in Lobby/None/EndOfGame
                        if phase not in ["Lobby", "None", "EndOfGame"]:
                            self.after(
                                0, lambda: self.after(30000, self.update_rank_display)
                            )  # Optimization: Poll every 30s during game
                            return
                except Exception:  # pylint: disable=broad-exception-caught
                    pass

                # 3. Fetch Stats (Heavy)
                text = ""
                try:
                    r = self.lcu.request("GET", "/lol-ranked/v1/current-ranked-stats")
                    if r and r.status_code == 200:
                        data = r.json()
                        queues = data.get("queues", [])
                        solo = next(
                            (
                                q
                                for q in queues
                                if q.get("queueType") == "RANKED_SOLO_5x5"
                            ),
                            None,
                        )
                        if solo:
                            tier = solo.get("tier", "UNRANKED")
                            division = solo.get("division", "")
                            lp = solo.get("leaguePoints", 0)
                            text = f"{tier} {division} ({lp} LP)"

                    # 3b. Append Session Stats
                    if self.automation:
                        stats = self.automation.session_stats
                        if stats["games"] > 0:
                            text += f" | {stats['wins']}W - {stats['losses']}L"
                except Exception:  # pylint: disable=broad-exception-caught
                    pass

                # 4. Update UI (Main Thread)
                try:
                    if getattr(self, "winfo_exists", lambda: False)():
                        self.after(0, lambda: _apply(text))
                except Exception:
                    pass

            def _apply(text):
                try:
                    if not getattr(self, "winfo_exists", lambda: False)():
                        return
                    if text and hasattr(self, "lbl_rank") and getattr(self.lbl_rank, "winfo_exists", lambda: False)():
                        self.lbl_rank.configure(text=text)
                    self.after(10000, self.update_rank_display)
                except Exception:
                    pass

            threading.Thread(target=_worker, daemon=True).start()
        else:
            try:
                if getattr(self, "winfo_exists", lambda: False)():
                    self.after(10000, self.update_rank_display)
            except Exception:
                pass

    def _init_dashboard_ui(self):
        # --- SECTION 1: QUEUE CONTROL (Elevated Panel) ---
        self.frame_queue = make_panel(self.content, title=None)
        self.frame_queue.pack(fill="x", pady=(0, TOKENS.get("spacing.lg")), ipady=TOKENS.get("spacing.sm"))

        q_top = ctk.CTkFrame(self.frame_queue._content, fg_color="transparent")
        q_top.pack(fill="x", padx=TOKENS.get("spacing.md"), pady=TOKENS.get("spacing.sm"))

        ctk.CTkLabel(
            q_top,
            text="Matchmaking",
            font=get_font("header"),
            text_color=get_color("colors.text.primary"),
        ).pack(side="left", padx=(0, TOKENS.get("spacing.md")))

        self.queues = {
            "Ranked Solo/Duo": 420,
            "Ranked Flex": 440,
            "Normal Draft": 400,
            "Normal Blind": 430,
            "ARAM": 450,
            "ARAM: Mayhem": 2400,
            "Quickplay": 490,
            "Arena": 1700,
            "TFT Ranked": 1100,
            "ARURF": 900,
        }
        self.combo_queue = ctk.CTkComboBox(
            q_top, values=list(self.queues.keys()), width=200, font=get_font("body"),
            corner_radius=TOKENS.get("radius.sm"),
            border_width=1,
            border_color=get_color("colors.text.muted"),
            fg_color=get_color("colors.background.card"),
            text_color=get_color("colors.text.primary"),
            dropdown_fg_color=get_color("colors.background.panel"),
        )
        self.combo_queue.pack(side="left", padx=(0, TOKENS.get("spacing.sm")))
        
        # Load Last Played Queue
        saved_q = self.config.get("queue_type")
        if saved_q and saved_q in self.queues:
            self.combo_queue.set(saved_q)
        else:
            self.combo_queue.set("Ranked Solo/Duo")

        self.btn_queue = make_button(
            q_top,
            text="FIND MATCH",
            style="primary", 
            width=140,
            command=self.start_queue,
        )
        self.btn_queue.pack(side="left", padx=(TOKENS.get("spacing.sm"), 0))

        # Hotkey hint
        hotkey_text = self.config.get("hotkey_find_match", "Ctrl+Shift+F")
        ctk.CTkLabel(
            q_top, text=f"[{hotkey_text}]",
            font=get_font("caption"),
            text_color=get_color("colors.text.muted"),
        ).pack(side="left", padx=(4, 0))

        # --- Mode Select (Right-aligned, elevated segment) ---
        self.frame_modes = ctk.CTkFrame(q_top, fg_color="transparent")
        self.frame_modes.pack(side="right")
        
        self.mode_btns = {}
        modes = ["SUMMONER'S RIFT", "ARENA MODE", "ARAM MODE"]
        
        for m in modes:
            # 200% Larger icons
            icon = self.asset_manager.get_gamemode_icon(m, size=(56, 56))
            # Fallback text if icon missing (until downloaded)
            txt = "" if icon else m[:2] 
            
            btn = make_button(
                self.frame_modes,
                text=txt,
                icon=icon,
                width=72,
                height=72,
                style="secondary",
                command=lambda x=m: self.switch_game_mode(x)
            )
            btn.pack(side="left", padx=2)
            if icon:
                CTkTooltip(btn, m)
            self.mode_btns[m] = btn
            
        # Default State
        self.current_mode = "SUMMONER'S RIFT"
        # Defer highlighting to switch_game_mode logic
        self.after(100, lambda: self.switch_game_mode("SUMMONER'S RIFT"))

        # --- SECTION 2: AUTOMATION CONTROLS (Elevated Panel) ---
        self.frame_auto = make_panel(self.content, title="Automation & Loop", collapsible=True, start_collapsed=True)
        self.frame_auto.pack(fill="x", pady=(0, TOKENS.get("spacing.xl")), ipady=TOKENS.get("spacing.sm"))

        # 🌟 Nova: Quick Presets Row
        p_row = ctk.CTkFrame(self.frame_auto._content, fg_color="transparent")
        p_row.pack(fill="x", padx=TOKENS.get("spacing.md"), pady=(TOKENS.get("spacing.xs"), TOKENS.get("spacing.sm")))

        ctk.CTkLabel(p_row, text="Quick Presets:", font=get_font("body"), text_color=get_color("colors.text.secondary")).pack(side="left", padx=(0, TOKENS.get("spacing.sm")))

        make_button(p_row, text="⚡ Tryhard", width=90, height=24, font=get_font("caption"), command=lambda: self._apply_preset("tryhard")).pack(side="left", padx=(0, 4))
        make_button(p_row, text="☕ Coffee Break", width=110, height=24, font=get_font("caption"), command=lambda: self._apply_preset("coffee")).pack(side="left", padx=(0, 4))
        make_button(p_row, text="🛡️ Standard", width=90, height=24, font=get_font("caption"), command=lambda: self._apply_preset("standard")).pack(side="left", padx=(0, 4))

        # Toggles Grid
        a_grid = ctk.CTkFrame(self.frame_auto._content, fg_color="transparent")
        a_grid.pack(fill="x", padx=TOKENS.get("spacing.md"), pady=(TOKENS.get("spacing.xs"), TOKENS.get("spacing.md")))

        self._add_toggle_compact(
            a_grid,
            "Auto Accept",
            "auto_accept",
            side="left",
            padx=(0, 20),
            tooltip_text="Automatically accepts the matchmaking queue pop.",
        )

        self._add_toggle_compact(
            a_grid,
            "Auto Lock In",
            "auto_lock_in",
            side="left",
            padx=(0, 20),
            tooltip_text="Automatically locks in your selected champion when it is your turn to pick.",
        )
        # Auto Spells Removed

        self._add_toggle_compact(
            a_grid,
            "Auto Hover",
            "auto_hover",
            side="left",
            padx=(0, 20),
            tooltip_text="Hover your champion during the ban phase to indicate your preference to teammates.",
        )

        self._add_toggle_compact(
            a_grid,
            "Auto Random Skin",
            "auto_random_skin",
            side="left",
            padx=(0, 20),
            tooltip_text="Automatically equips a random owned skin when a champion is picked.",
        )

        # Delay Slider Row
        d_row = ctk.CTkFrame(self.frame_auto._content, fg_color="transparent")
        d_row.pack(fill="x", padx=TOKENS.get("spacing.md"), pady=(TOKENS.get("spacing.xs"), 0))

        ctk.CTkLabel(
            d_row,
            text="Accept Delay:",
            font=get_font("body"),
            text_color=get_color("colors.text.secondary"),
        ).pack(side="left", padx=(0, TOKENS.get("spacing.sm")))

        self.lbl_delay = ctk.CTkLabel(
            d_row,
            text=f"{self.config.get('accept_delay', 2.0):.1f}s",
            font=get_font("body"),
            width=40,
        )
        self.lbl_delay.pack(side="right", padx=(TOKENS.get("spacing.sm"), 0))

        self.slider_delay = ctk.CTkSlider(
            d_row,
            from_=0,
            to=10,
            number_of_steps=20,
            command=self._on_delay_change,
            fg_color=get_color("colors.background.panel"),
            progress_color=get_color("colors.accent.primary"),
            button_color=get_color("colors.accent.primary"),
            button_hover_color=get_color("colors.accent.blue"),
        )
        self.slider_delay.pack(side="left", fill="x", expand=True)
        self.slider_delay.set(self.config.get("accept_delay", 2.0))

        # Polling Speed Row
        p_row = ctk.CTkFrame(self.frame_auto._content, fg_color="transparent")
        p_row.pack(fill="x", padx=TOKENS.get("spacing.md"), pady=(TOKENS.get("spacing.xs"), 0))

        ctk.CTkLabel(
            p_row,
            text="CS Speed (Polling):",
            font=get_font("body"),
            text_color=get_color("colors.text.secondary"),
        ).pack(side="left", padx=(0, TOKENS.get("spacing.sm")))

        self.lbl_poll = ctk.CTkLabel(
            p_row,
            text=f"{self.config.get('polling_rate_champ_select', 0.5):.1f}s",
            font=get_font("body"),
            width=40,
        )
        self.lbl_poll.pack(side="right", padx=(TOKENS.get("spacing.sm"), 0))

        self.slider_poll = ctk.CTkSlider(
            p_row,
            from_=0.1,
            to=2.0,
            number_of_steps=19,
            command=self._on_poll_speed_change,
            fg_color=get_color("colors.background.panel"),
            progress_color=get_color("colors.accent.primary"),
            button_color=get_color("colors.accent.primary"),
            button_hover_color=get_color("colors.accent.blue"),
        )
        self.slider_poll.pack(side="left", fill="x", expand=True)
        self.slider_poll.set(self.config.get("polling_rate_champ_select", 0.5))

        # Lock-in Timing Row
        lock_row = ctk.CTkFrame(self.frame_auto._content, fg_color="transparent")
        lock_row.pack(fill="x", padx=TOKENS.get("spacing.md"), pady=(TOKENS.get("spacing.md"), TOKENS.get("spacing.xs")))

        ctk.CTkLabel(
            lock_row,
            text="Lock-In Timing:",
            font=get_font("body"),
            text_color=get_color("colors.text.secondary"),
        ).pack(side="left", padx=(0, TOKENS.get("spacing.sm")))

        # Labels for slider ends
        ctk.CTkLabel(
            lock_row,
            text="Instant",
            font=get_font("caption"),
            text_color=get_color("colors.text.muted"),
        ).pack(side="left", padx=(0, 5))

        self.lbl_lock_timing = ctk.CTkLabel(
            lock_row,
            text=f"{self.config.get('lock_in_delay', 5)}s",
            font=get_font("body"),
            width=35,
            text_color=get_color("colors.accent.primary"),
        )
        self.lbl_lock_timing.pack(side="right", padx=(5, 0))

        ctk.CTkLabel(
            lock_row,
            text="Last Moment",
            font=get_font("caption"),
            text_color=get_color("colors.text.muted"),
        ).pack(side="right", padx=(0, 5))

        # Slider: 0 = instant, 25 = wait ~25s (last safe moment for most modes)
        self.slider_lock_timing = ctk.CTkSlider(
            lock_row,
            from_=0,
            to=25,
            number_of_steps=25,
            command=self._on_lock_timing_change,
            fg_color=get_color("colors.background.panel"),
            progress_color=get_color("colors.accent.purple"),
            button_color=get_color("colors.accent.purple"),
            button_hover_color=get_color("colors.accent.blue"),
        )
        self.slider_lock_timing.pack(side="left", fill="x", expand=True, padx=TOKENS.get("spacing.xs"))
        self.slider_lock_timing.set(self.config.get("lock_in_delay", 5))

        # Show initial view
        self.view_container = ctk.CTkFrame(self.content, fg_color="transparent")
        self.view_container.pack(fill="both", expand=True, pady=TOKENS.get("spacing.md"))

        # Tooltips for Sliders and Buttons
        CTkTooltip(
            self.slider_delay,
            "Adds a randomized delay before accepting the queue pop to mimic human behavior.",
        )
        CTkTooltip(
            self.slider_poll,
            "Polling rate during Champion Select. Lower values are faster (Insta-lock) but use more CPU.",
        )
        CTkTooltip(
            self.btn_queue, "Starts the matchmaking search for the selected queue type."
        )
        CTkTooltip(
            self.btn_launch,
            "Attempts to launch the League of Legends client if it is not running.",
        )

        self.switch_game_mode("SUMMONER'S RIFT")

    def _animate_slider(self, slider, current_val, target_val, steps=15, current_step=0, callback=None, anim_id=None):
        """Animates a CTkSlider to a target value smoothly."""
        if not getattr(slider, "winfo_exists", lambda: False)():
            return

        if not hasattr(self, "_slider_anims"):
            self._slider_anims = {}

        if not hasattr(self, "_anim_counter"):
            self._anim_counter = 0

        if current_step == 0:
            self._anim_counter += 1
            anim_id = self._anim_counter
            self._slider_anims[slider] = anim_id

        if self._slider_anims.get(slider) != anim_id:
            return

        if current_step >= steps:
            slider.set(target_val)
            if callback:
                callback(target_val)
            return

        t = current_step / steps
        val = current_val + (target_val - current_val) * (t * (2 - t))

        slider.set(val)

        self.after(20, lambda: self._animate_slider(slider, current_val, target_val, steps, current_step + 1, callback, anim_id))

    def _apply_preset(self, preset_name):
        """Applies a quick preset with animated slider transitions."""
        tm = ToastManager.get_instance()

        if preset_name == "tryhard":
            targets = {"delay": 0.0, "poll": 0.1, "lock": 0, "msg": "Tryhard mode activated. Instant lock-in & queue pops."}
        elif preset_name == "coffee":
            targets = {"delay": 8.0, "poll": 1.0, "lock": 20, "msg": "Coffee Break mode activated. Maximum safety delays applied."}
        else: # standard
            targets = {"delay": 2.0, "poll": 0.5, "lock": 5, "msg": "Standard mode activated. Balanced delays applied."}

        if hasattr(self, "var_auto_lock_in"):
            self.var_auto_lock_in.set(True)
            self.config.set("auto_lock_in", True)

        self._animate_slider(self.slider_delay, self.slider_delay.get(), targets["delay"], callback=self._on_delay_change)
        self._animate_slider(self.slider_poll, self.slider_poll.get(), targets["poll"], callback=self._on_poll_speed_change)
        self._animate_slider(self.slider_lock_timing, self.slider_lock_timing.get(), targets["lock"], callback=self._on_lock_timing_change)

        if tm:
            tm.show_toast(
                title="✨ Preset Applied",
                message=targets["msg"],
                type="success" if preset_name == "standard" else "info",
                duration=3500
            )

    def _on_delay_change(self, value):
        self.lbl_delay.configure(text=f"{value:.1f}s")
        self.config.set("accept_delay", value)

    def _on_poll_speed_change(self, value):
        self.lbl_poll.configure(text=f"{value:.1f}s")
        self.config.set("polling_rate_champ_select", value)

    def _on_lock_timing_change(self, value):
        """Update lock-in timing delay (seconds to wait before locking in)."""
        delay = int(value)
        self.config.set("lock_in_delay", delay)
        self.lbl_lock_timing.configure(text=f"{delay}s")
        # Update automation engine if available
        if hasattr(self, "automation") and self.automation:
            self.automation.pick_delay = delay

    def switch_game_mode(self, mode: str):
        """Switch game mode (SR, Arena, ARAM) and update UI."""
        print(f"Switching mode to: {mode}")
        self.current_mode = mode
        self.config.set("last_mode", mode)
        
        # Highlight active button
        if hasattr(self, "mode_btns"):
            for m, btn in self.mode_btns.items():
                if m == mode:
                    btn.configure(fg_color=get_color("colors.accent.primary"))
                else:
                    btn.configure(fg_color=get_color("colors.background.card"))

        # Clear current view
        for widget in self.view_container.winfo_children():
            widget.destroy()

        if mode == "SUMMONER'S RIFT":
            self._init_sr_tab(self.view_container)
        elif mode == "ARENA MODE":
            self._init_arena_tab(self.view_container)
        elif mode == "ARAM MODE":
            self._init_aram_tab(self.view_container)

        # Trigger Automation update if needed
        if hasattr(self, "automation") and self.automation:
            try:
                if hasattr(self.automation, "set_mode"):
                    self.automation.set_mode(mode)
            except AttributeError:
                print(f"[Dashboard] Warning: AutomationEngine missing set_mode. Mode {mode} not propagated.")

    def _init_sr_tab(self, parent):
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill="both", expand=True)

        # Header with Auto Runes Toggle
        header_frame = ctk.CTkFrame(container, fg_color="transparent")
        header_frame.pack(fill="x", padx=TOKENS.get("spacing.md"), pady=(0, TOKENS.get("spacing.xs")))
        
        self._add_toggle_compact(
            header_frame,
            "Auto Runes (Equip Bound Page)",
            "auto_runes",
            side="right",
            tooltip_text="Automatically equips the bound rune page when your primary champion is picked.",
        )

        self.role_scroll = ctk.CTkScrollableFrame(
            container, fg_color="transparent", orientation="vertical"
        )
        self.role_scroll.pack(fill="both", expand=True)

        # Grid Configuration for 5 Columns
        self.role_scroll.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        roles = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
        for i, role in enumerate(roles):
            self._create_role_column(self.role_scroll, role, i)

    def _create_mini_rune_btn(self, parent, role, index, size=30):
        """Create a compact rune binding button."""
        rune_key = f"rune_pick_{role}_{index}"
        has_rune = self.config.get(rune_key)

        btn = make_button(
            parent,
            text="R" if not has_rune else "✓",
            width=size,
            height=size,
            fg_color=get_color("colors.background.card"),
            hover_color=get_color("colors.accent.primary") if not has_rune else get_color("colors.state.success"),
            border_color=parse_border("soft")[1],
            border_width=1,
            font=("Arial", 10, "bold") if size < 30 else ("Arial", 12),
        )
        # Late binding fix
        btn.configure(command=lambda: self.open_rune_binder(rune_key, btn))
        
        desc = f"Bound to: {self.config.get(rune_key)}" if has_rune else "Bind a Rune Page to this Pick"
        CTkTooltip(btn, desc)
        return btn

    def _poll_role_icon(self, role):
        """Periodically check if role icon is downloaded."""
        if not hasattr(self, "role_labels") or role not in self.role_labels:
            return

        lbl = self.role_labels[role]
        if not getattr(lbl, "winfo_exists", lambda: False)():
            return

        icon = self.asset_manager.get_role_icon(role, size=(40, 40))
        if icon:
            try:
                lbl.configure(image=icon, text="")
            except Exception:
                pass
        else:
            self.after(2000, lambda: self._poll_role_icon(role))
            
    def _create_role_column(self, parent, role, col_idx):
        # Column Container
        col = ctk.CTkFrame(parent, fg_color="transparent")
        col.grid(row=0, column=col_idx, sticky="nsew", padx=TOKENS.get("spacing.xs"))

        # 1. Role Icon / Header (Large & Clean)
        icon_img = self.asset_manager.get_role_icon(role, size=(40, 40))
        
        # We'll use a wrapper label that can update itself once the icon is downloaded
        self.role_labels = getattr(self, "role_labels", {})
        
        lbl_role = ctk.CTkLabel(
            col, text="" if icon_img else role[:3], 
            image=icon_img, 
            font=get_font("title"), 
            text_color=get_color("colors.accent.blue")
        )
        lbl_role.pack(pady=(TOKENS.get("spacing.sm"), TOKENS.get("spacing.lg")))
        self.role_labels[role] = lbl_role

        # Start a small poller for this column if icon is missing
        if not icon_img:
            self._poll_role_icon(role)

        # 2. Main Pick (Large Box)
        # Background slot effect
        bw, bc = parse_border("subtle")
        p1_frame = make_card(
            col, fg_color=get_color("colors.background.card"), width=70, height=70,
            corner_radius=TOKENS.get("radius.sm"),
            border_width=bw, border_color=bc,
        )
        p1_frame.pack(pady=(0, TOKENS.get("spacing.sm")))
        p1_frame.pack_propagate(False)
        self._create_pick_slot_frozen(p1_frame, role, 1, size=60)  # Main Pick Reduced

        # 2.5 Action/Rune Button (Small Row)
        action_row = ctk.CTkFrame(col, fg_color="transparent")
        action_row.pack(pady=(0, TOKENS.get("spacing.sm")))
        
        self._create_mini_rune_btn(action_row, role, 1, size=30).pack()

        # 3. Secondaries (Pair)
        # Two smaller boxes side by side
        sec_row = ctk.CTkFrame(col, fg_color="transparent")
        sec_row.pack(pady=(0, TOKENS.get("spacing.xl")))

        # Slot 2 (Left)
        s2_cont = ctk.CTkFrame(sec_row, fg_color="transparent")
        s2_cont.pack(side="left", padx=TOKENS.get("spacing.xs"))
        
        s2_frame = ctk.CTkFrame(s2_cont, fg_color="transparent")
        s2_frame.pack()
        self._create_pick_slot_frozen(s2_frame, role, 2, size=35)
        self._create_mini_rune_btn(s2_cont, role, 2, size=20).pack(pady=(2,0))

        # Slot 3 (Right)
        s3_cont = ctk.CTkFrame(sec_row, fg_color="transparent")
        s3_cont.pack(side="left", padx=TOKENS.get("spacing.xs"))

        s3_frame = ctk.CTkFrame(s3_cont, fg_color="transparent")
        s3_frame.pack()
        self._create_pick_slot_frozen(s3_frame, role, 3, size=35)
        self._create_mini_rune_btn(s3_cont, role, 3, size=20).pack(pady=(2,0))

        # 4. Ban Slot (Red Border) at Bottom
        ban_frame = ctk.CTkFrame(
            col, fg_color="transparent", width=50, height=50
        )  # Visual container
        ban_frame.pack(pady=(TOKENS.get("spacing.xs"), TOKENS.get("spacing.md")))

        self._create_ban_slot_frozen(ban_frame, role, size=40)  # Reduced from 50

    def _init_arena_tab(self, parent):
        container = make_panel(parent, title="ARENA CONFIGURATION")
        container.pack(fill="x", expand=True, ipadx=TOKENS.get("spacing.md"), ipady=TOKENS.get("spacing.md"))

        for i in range(1, 4):
            self._create_arena_slot(container._content, i)

    def _init_aram_tab(self, parent):
        # ARAM Tabs Container
        self.aram_tabs = ctk.CTkTabview(parent, fg_color="transparent")
        self.aram_tabs.pack(fill="both", expand=True, padx=TOKENS.get("spacing.md"), pady=TOKENS.get("spacing.md"))
        
        self.aram_tabs.add("Default Picker")
        self.aram_tabs.add("Priority Picker")
        self.aram_tabs.add("Experimental Profile")
        
        self._init_aram_legacy_tab(self.aram_tabs.tab("Default Picker"))
        self._init_aram_priority_tab(self.aram_tabs.tab("Priority Picker"))
        self._init_experimental_profile_tab(self.aram_tabs.tab("Experimental Profile"))

    def _init_aram_legacy_tab(self, parent):
        # ARAM Sniper UI
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=TOKENS.get("spacing.md"))

        header = ctk.CTkLabel(
            container,
            text="ARAM SNIPER TARGETS",
            font=get_font("header"),
            text_color=get_color("colors.text.secondary"),
        )
        header.pack(pady=(0, TOKENS.get("spacing.sm")))

        self.switch_aram = make_switch(
            container,
            text="Enable Auto-Swap",
            command=self._on_aram_swap_toggle
        )
        self.switch_aram.pack(pady=(0, TOKENS.get("spacing.md")))
        
        if self.config.get("auto_aram_swap"):
            self.switch_aram.select()
        else:
            self.switch_aram.deselect()


        # Grid Container 2x4 (Elevated)
        grid = make_panel(container, title=None)
        grid.pack(anchor="center", pady=TOKENS.get("spacing.md"))

        for i in range(1, 9):
            row = (i - 1) // 4
            col = (i - 1) % 4

            slot = ctk.CTkFrame(grid._content, fg_color="transparent")
            slot.grid(row=row, column=col, padx=TOKENS.get("spacing.md"), pady=TOKENS.get("spacing.md"))

            ctk.CTkLabel(
                slot,
                text=f"Priority {i}",
                font=get_font("caption"),
                text_color=get_color("colors.text.muted"),
            ).pack(pady=(0, 5))

            key = f"aram_target_{i}"
            curr = self.config.get(key)
            icon = (
                self.asset_manager.get_icon("champion", curr, size=(64, 64))
                if curr
                else None
            )

            # Simple button that opens selector
            btn = make_button(
                slot,
                text="?" if not icon else "",
                icon=icon if icon else None,
                width=72,
                height=72,
                style="secondary",
            )
            # Late binding fix: Configure command after btn exists
            btn.configure(command=lambda k=key, b=btn: self.open_selector_for_aram(k, b))
            btn.pack()

    def open_selector_for_aram(self, key, btn):
        """Open selector for ARAM slots."""
        self.open_selector_for_slot_v2(key, btn, 64)

    def _init_aram_priority_tab(self, parent):
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill="both", expand=True)

        header = ctk.CTkFrame(container, fg_color="transparent")
        header.pack(fill="x", pady=TOKENS.get("spacing.sm"))

        self.switch_priority = make_switch(
            header,
            text="Enable Priority Auto-Pick",
            command=self._on_priority_swap_toggle
        )
        self.switch_priority.pack(side="left")
        
        btn_add = make_button(header, text="+ Add Champion", style="primary", command=self._on_add_priority_champ)
        btn_add.pack(side="right")
        
        state = self.config.get("priority_picker", {})
        if state.get("enabled", False):
            self.switch_priority.select()
        else:
            self.switch_priority.deselect()
            
        self.priority_list = state.get("list", [])
        
        from ..components.draggable_list import DraggableList
        self.drag_list = DraggableList(
            container, 
            items=self.priority_list, 
            on_reorder=self._on_priority_reorder,
            on_remove=self._on_priority_remove,
            asset_manager=self.asset_manager,
            fg_color="transparent"
        )
        self.drag_list.pack(fill="both", expand=True, pady=TOKENS.get("spacing.sm"))

    def _on_priority_swap_toggle(self):
        val = self.switch_priority.get()
        state = self.config.get("priority_picker", {"enabled": False, "list": []})
        state["enabled"] = bool(val)
        self.config.set("priority_picker", state)
        
    def _save_priority_list(self, new_list):
        self.priority_list = new_list
        state = self.config.get("priority_picker", {"enabled": False, "list": []})
        state["list"] = self.priority_list
        self.config.set("priority_picker", state)
        
    def _on_priority_reorder(self, new_items):
        self._save_priority_list(new_items)
        
    def _on_priority_remove(self, item):
        if item in self.priority_list:
            self.priority_list.remove(item)
            self._save_priority_list(self.priority_list)
            self.drag_list.update_items(self.priority_list)
            
    def _on_add_priority_champ(self):
        if self.selector:
            # Defer destroy to prevent active CTk Configure callbacks from throwing TclErrors
            tw = self.selector
            self.selector = None
            tw.grid_forget()
            tw.after(50, tw.destroy)

        def on_select(name):
            if name and name not in self.priority_list:
                self.priority_list.append(name)
                self._save_priority_list(self.priority_list)
                self.drag_list.update_items(self.priority_list)
            self.close_selector()

        self.selector = ChampionSelector(
            self, self.asset_manager, on_select, self.close_selector
        )
        self.selector.grid(row=0, column=0, sticky="nsew")
        self.selector.lift()

    def _init_experimental_profile_tab(self, parent):
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=16, pady=12)
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=1)

        # ── Controls Row (fixed, non-scrolling) ───────────────────────────────
        ctrl_row = ctk.CTkFrame(container, fg_color="transparent")
        ctrl_row.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        # Toggle
        self.switch_exp = make_switch(
            ctrl_row,
            text="Enable Learning",
            command=self._on_exp_swap_toggle
        )
        self.switch_exp.pack(side="left")

        state = self.config.get("experimental_profile", {})
        if state.get("enabled", True):
            self.switch_exp.select()
        else:
            self.switch_exp.deselect()

        # Matches tracked
        matches = state.get("matches_tracked", 0)
        self.lbl_exp_matches = ctk.CTkLabel(
            ctrl_row,
            text=f"Matches Tracked: {matches}",
            font=get_font("body"),
            text_color=get_color("colors.text.secondary"),
        )
        self.lbl_exp_matches.pack(side="left", padx=12)

        # Reset Model (right-aligned)
        btn_reset = make_button(ctrl_row, text="Reset Model", style="danger", command=self._on_exp_reset, width=110)
        btn_reset.pack(side="right")

        # ── Scrollable Champion Grid ──────────────────────────────────────────
        from ..components.experimental_profile_list import ExperimentalProfileList

        model_svc = self.automation.pref_model if hasattr(self, 'automation') and self.automation and hasattr(self.automation, 'pref_model') else None
        self.exp_list = ExperimentalProfileList(
            container,
            model_service=model_svc,
            asset_manager=self.asset_manager,
        )
        self.exp_list.grid(row=1, column=0, sticky="nsew")

    def _on_exp_swap_toggle(self):
        val = self.switch_exp.get()
        if hasattr(self, 'automation') and self.automation and hasattr(self.automation, 'pref_model'):
            self.automation.pref_model.state["enabled"] = bool(val)
            self.automation.pref_model.save()
        else:
            state = self.config.get("experimental_profile", {})
            state["enabled"] = bool(val)
            self.config.set("experimental_profile", state)

    def _on_exp_reset(self):
        # Kept for programmatic use if needed later
        if hasattr(self, 'automation') and self.automation and hasattr(self.automation, 'pref_model'):
            self.automation.pref_model.reset()
            self.exp_list.refresh()

    def _on_aram_swap_toggle(self):
        """Toggle ARAM Sniper logic."""
        val = self.switch_aram.get()
        self.config.set("auto_aram_swap", bool(val))
        print(f"ARAM Swap Toggled: {bool(val)}")

    def _create_slot(
        self,
        parent,
        config_key,
        size=50,
        is_ban=False,
        show_rune=False,
        pack_side=None,
        pady=0,
    ):
        """
        Universal slot creator for Picks, Bans, and Arena.
        Handles: Icons, Bans (Red), Runes (if enabled), packing vs placing.
        """
        curr_name = self.config.get(config_key)
        
        display_name = curr_name
        if curr_name and self.asset_manager and self.asset_manager.champ_data and curr_name in self.asset_manager.champ_data:
            display_name = self.asset_manager.champ_data[curr_name].get("name", curr_name)

        # Style Defaults
        icon = None
        txt = "?"
        fg_col = get_color("colors.background.card")
        hover = get_color("colors.accent.primary")
        _, border = parse_border("subtle")
        border_w = 0

        if is_ban:
            txt = "BAN"
            hover = get_color("colors.state.danger")
            if curr_name:
                border = get_color("colors.state.danger")
                border_w = 2

        if curr_name:
            icon = self.asset_manager.get_icon("champion", curr_name, size=(size, size), grayscale=is_ban)
            if not icon:
                txt = curr_name[:2]

        # Container (Needed for Rune button side-by-side)
        container = ctk.CTkFrame(parent, fg_color="transparent")

        if isinstance(parent, ctk.CTkFrame) and pack_side:
            container.pack(side=pack_side, pady=pady)
        elif not pack_side:
            # Assume we place center if no pack side
            container.place(relx=0.5, rely=0.5, anchor="center")

        # Main Button
        btn = make_button(
            container,
            text=txt if not icon else "",
            icon=icon,
            width=size,
            height=size,
            fg_color=fg_col,
            hover_color=hover,
            border_color=border,
            border_width=border_w,
            corner_radius=4,
            command=lambda: self.open_selector_for_slot_v2(config_key, btn, size),
        )
        btn.pack(side="left")

        # Async Update if icon is missing
        if curr_name and not icon:
            def _update_btn_icon(img, _btn=btn, _cname=curr_name):
                # Check if widget still exists and config hasn't changed (simplistic check)
                try:
                    if getattr(_btn, "winfo_exists", lambda: False)():
                        if img:
                            _btn.configure(image=img, text="")
                        else:
                             # Fallback if download failed
                             _btn.configure(text=_cname[:2] if _cname else "?")
                except Exception:
                    pass

            self.asset_manager.get_icon_async(
                "champion", curr_name, _update_btn_icon, size=(size, size), grayscale=is_ban, widget=self
            )

        # Tooltip for Champion Name
        tip_text = display_name if display_name else "Click to Select"
        btn.tooltip = CTkTooltip(btn, tip_text)

        # Optional Rune Button (Tiny side bar)
        if show_rune:
            rune_key = f"rune_{config_key}"
            has_rune = self.config.get(rune_key)

            rune_btn = ctk.CTkButton(
                container,
                text="",
                width=12,
                height=size,
                fg_color=get_color("colors.background.panel") if not has_rune else get_color("colors.accent.primary"),
                hover_color=get_color("colors.accent.blue"),
                corner_radius=2,
                command=lambda: self.open_rune_binder(rune_key, rune_btn),
            )
            rune_btn.pack(side="left", padx=(2, 0))

    def _create_pick_slot_frozen(
        self, parent, role, slot_num, size, pady=0, pack_side="top"
    ):
        # Wrapper for legacy calls -> redirects to universal
        # Note: 'frozen' implys strict layout.
        # Using config key format: pick_{role}_{slot_num}
        key = f"pick_{role}_{slot_num}"
        # Frozen slots usually don't show inline runes (they use a separate button row in new layout).
        self._create_slot(
            parent,
            key,
            size,
            is_ban=False,
            show_rune=False,
            pack_side=pack_side,
            pady=pady,
        )



    def _create_ban_slot_frozen(self, parent, role, size):
        key = f"ban_{role}"
        self._create_slot(
            parent, key, size, is_ban=True, show_rune=False, pack_side=None
        )  # Centers in parent

    def _create_arena_slot(self, parent, index):
        # We'll create a row with Pick [i] and Ban [i]
        # This function is called 3 times (index 1, 2, 3)

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(pady=5, fill="x")

        # Pick Slot (Left)
        p_frame = ctk.CTkFrame(row, fg_color="transparent")
        p_frame.pack(side="left", expand=True)
        if index == 1:
            ctk.CTkLabel(
                p_frame,
                text="PICK PRIORITY",
                font=get_font("caption"),
                text_color=get_color("colors.text.secondary"),
            ).pack()

        self._create_simple_slot(
            p_frame, f"arena_pick_{index}", size=50, is_ban=False
        )

        # Ban Slot (Right)
        b_frame = ctk.CTkFrame(row, fg_color="transparent")
        b_frame.pack(side="right", expand=True)
        if index == 1:
            ctk.CTkLabel(
                b_frame,
                text="BAN PRIORITY",
                font=get_font("caption"),
                text_color=get_color("colors.state.danger"),
            ).pack()

        self._create_simple_slot(
            b_frame, f"arena_ban_{index}", size=35, is_ban=True
        )

    def _create_simple_slot(self, parent, config_key, size=50, is_ban=False):
        curr_name = self.config.get(config_key)
        
        display_name = curr_name
        if curr_name and self.asset_manager and self.asset_manager.champ_data and curr_name in self.asset_manager.champ_data:
            display_name = self.asset_manager.champ_data[curr_name].get("name", curr_name)

        icon = None
        txt = "NONE"
        color = get_color("colors.background.card")
        hover = get_color("colors.accent.primary")
        _, border = parse_border("subtle")
        border_w = 0

        if is_ban:
            hover = get_color("colors.state.danger")
            if curr_name:
                border = get_color("colors.state.danger")
                border_w = 1

        if curr_name:
            icon = self.asset_manager.get_icon("champion", curr_name, size=(size, size), grayscale=is_ban)
            if not icon:
                txt = curr_name[:2]
        else:
            txt = "?"

        btn = make_button(
            parent,
            text=txt if not icon else "",
            icon=icon,
            width=size,
            height=size,
            fg_color=color,
            hover_color=hover,
            border_color=border,
            border_width=border_w,
            command=lambda: self.open_selector_for_slot_v2(
                config_key, btn, size
            ),  # Reuse V2 compatible selector
        )
        btn.pack(pady=2)

        # Async Update
        if curr_name and not icon:
            def _update_simple(img, _btn=btn, _cname=curr_name):
                try:
                    if getattr(_btn, "winfo_exists", lambda: False)():
                        if img:
                            _btn.configure(image=img, text="")
                except Exception:
                    pass

            self.asset_manager.get_icon_async(
                "champion", curr_name, _update_simple, size=(size, size), grayscale=is_ban, widget=self
            )

        # Tooltip for Champion Name (Simple Slot)
        tip_text = display_name if display_name else "Click to Select"
        btn.tooltip = CTkTooltip(btn, tip_text)

    def open_selector_for_slot(self, config_key, btn_widget, size):
        """Open champion selector."""
        def on_select(name):
            self.config.set(config_key, name)
            img = self.asset_manager.get_icon("champion", name, size=(size, size))
            if img:
                btn_widget.configure(image=img, text="")
            else:
                btn_widget.configure(image=None, text=name[:2] if name else "?")

            display_name = name
            if name and self.asset_manager and self.asset_manager.champ_data and name in self.asset_manager.champ_data:
                display_name = self.asset_manager.champ_data[name].get("name", name)

            # Update Tooltip
            if hasattr(btn_widget, "tooltip"):
                btn_widget.tooltip.text = display_name if display_name else "Click to Select"
            else:
                btn_widget.tooltip = CTkTooltip(btn_widget, display_name if display_name else "Click to Select")

            self.close_selector()

        if self.selector:
            # Rebind the dynamic callback then re-show
            self.selector.on_select = on_select
            self.selector.grid(row=0, column=0, sticky="nsew")
            self.selector.lift()
            # Re-trigger load so scroll region refreshes after re-show
            self.selector.after(40, self.selector._load)
        else:
            self.selector = ChampionSelector(
                self, self.asset_manager, on_select, self.close_selector
            )
            self.selector.grid(row=0, column=0, sticky="nsew")
            self.selector.lift()

    def _add_toggle_compact(self, parent, text, config_key, side="top", padx=0, tooltip_text=None):
        var = ctk.BooleanVar(value=self.config.get(config_key, False))
        setattr(self, f"var_{config_key}", var)
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(side=side, padx=padx)
        lbl = ctk.CTkLabel(f, text=text, font=get_font("body"))
        lbl.pack(side="left", padx=(0, 5))
        switch = ctk.CTkSwitch(
            f,
            text="",
            width=40,
            height=20,
            variable=var,
            progress_color=get_color("colors.state.success"),
            command=self.save_config,
        )
        switch.pack(side="left")

        if tooltip_text:
            CTkTooltip(lbl, tooltip_text)
            CTkTooltip(switch, tooltip_text)

    def create_champ_card(self, parent, title, config_key, is_ban=False):
        """Create a champion selection card."""
        _ = title  # unused
        # Very compact ban selector
        curr = self.config.get(config_key)
        
        display_name = curr
        if curr and self.asset_manager and self.asset_manager.champ_data and curr in self.asset_manager.champ_data:
            display_name = self.asset_manager.champ_data[curr].get("name", curr)
            
        btn = ctk.CTkButton(
            parent,
            text=display_name if display_name else "SELECT BAN",
            width=120,
            height=25,
            fg_color=Colors.SURFACE,
            border_color=Colors.ERROR,
            border_width=1,
            command=lambda: self.open_selector_simple(config_key, is_ban),
        )
        btn.pack(side="left")
        self.btn_ban_ref = btn

    def open_selector_simple(self, key, is_ban):
        """Open a simple selector."""
        _ = is_ban  # unused

        def on_sel(name):
            self.config.set(key, name)
            if hasattr(self, "btn_ban_ref"):
                display_name = name
                if name and self.asset_manager and self.asset_manager.champ_data and name in self.asset_manager.champ_data:
                    display_name = self.asset_manager.champ_data[name].get("name", name)
                self.btn_ban_ref.configure(text=display_name)
            self.close_selector()

        if hasattr(self, "selector") and self.selector:
            self.selector.on_select = on_sel
            self.selector.grid(row=0, column=0, sticky="nsew")
            self.selector.lift()
        else:
            self.selector = ChampionSelector(
                self, self.asset_manager, on_sel, self.close_selector
            )
            self.selector.grid(row=0, column=0, sticky="nsew")
            self.selector.lift()

    def close_selector(self):
        """Close the selector."""
        if hasattr(self, "selector") and self.selector:
            self.selector.grid_remove()

    def save_config(self):
        """Save configuration (batched — single file write)."""
        keys = [
            "auto_requeue",
            "auto_accept",
            "auto_set_roles",
            "auto_hover",
            "auto_random_skin",
            "auto_runes",
            "auto_spells",
            "auto_aram_swap",
            "auto_honor",
        ]
        updates = {}
        for k in keys:
            if hasattr(self, f"var_{k}"):
                updates[k] = getattr(self, f"var_{k}").get()
        if updates:
            self.config.set_batch(updates)

            tm = ToastManager.get_instance()
            if tm:
                tm.show_toast("Settings Saved", "Your configuration updates have been saved.", type="success")

    def start_queue(self):
        """Start matchmaking queue."""
        if not self.lcu or not self.lcu.is_connected:
            return
        q_name = self.combo_queue.get()
        
        # Save Selection
        self.config.set("queue_type", q_name)
        
        target_q_id = self.queues.get(q_name, 420)

        # Auto-switch to correct game mode tab
        QUEUE_MODE_MAP = {
            "ARAM": "ARAM MODE", "ARAM: Mayhem": "ARAM MODE", "ARURF": "ARAM MODE",
            "Arena": "ARENA MODE",
        }
        target_mode = QUEUE_MODE_MAP.get(q_name, "SUMMONER'S RIFT")
        if self.current_mode != target_mode:
            self.switch_game_mode(target_mode)

        def _search():
            # Ensure Automation is ON
            if hasattr(self, "automation") and self.automation:
                if not self.automation.running:
                    self.automation.start()

            # Smart Matchmaking Logic
            # 1. Check current state
            lobby_req = self.lcu.request("GET", "/lol-lobby/v2/lobby")
            in_lobby = lobby_req and lobby_req.status_code == 200

            should_create = True

            if in_lobby:
                data = lobby_req.json()
                current_q = data.get("gameConfig", {}).get("queueId")

                # If we are in the correct lobby already
                if current_q == target_q_id:
                    should_create = False
                else:
                    # Wrong lobby - Quit it
                    self.lcu.request(
                        "DELETE", "/lol-lobby/v2/lobby/matchmaking/search"
                    )  # Stop search if active
                    time.sleep(0.5)
                    self.lcu.request("DELETE", "/lol-lobby/v2/lobby")
                    time.sleep(0.5)

            if should_create:
                self.lcu.request(
                    "POST", "/lol-lobby/v2/lobby", {"queueId": target_q_id}
                )
                time.sleep(1)

            # 2. Start Search
            self.lcu.request("POST", "/lol-lobby/v2/lobby/matchmaking/search")

        threading.Thread(target=_search, daemon=True).start()

    def open_selector_for_slot_v2(self, config_key, btn_widget, size):
        """Wrapper for champion selector - calls base selector."""
        self.open_selector_for_slot(config_key, btn_widget, size)

    def open_rune_binder(self, rune_key, btn_widget):
        """Opens the rune page selector to bind a saved rune page to a champion pick."""
        _ = btn_widget  # Unused for now
        if self.selector:
            tw = self.selector
            self.selector = None
            tw.grid_forget()
            tw.after(50, tw.destroy)

        # Load saved rune page names
        pages = self._load_saved_pages_names()

        if not pages:
            # No saved pages - show a message or just return
            print("[RUNE BINDER] No saved rune pages found.")
            return

        def on_select(page_name):
            self._bind_rune(rune_key, page_name, btn_widget)
            self.close_selector()

        self.selector = RunePageSelector(self, pages, on_select, self.close_selector)
        self.selector.grid(row=0, column=0, sticky="nsew")
        self.selector.lift()

    def _bind_rune(self, key, page_name, btn):
        self.config.set(key, page_name)
        if page_name:
            btn.configure(text="✓", fg_color="#C8AA6E")  # Gold
            if hasattr(btn, "tooltip"):
                btn.tooltip.text = f"Bound to: {page_name}"
        else:
            btn.configure(text="R", fg_color=ZLayers.Z1)
            if hasattr(btn, "tooltip"):
                btn.tooltip.text = "Bind a Rune Page to this Pick"

    def _load_saved_pages_names(self):
        if os.path.exists("rune_pages.json"):
            try:
                with open("rune_pages.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return [p["name"] for p in data]
            except Exception:  # pylint: disable=broad-exception-caught
                pass
        return []

    def launch_client(self):
        """Try to launch the League Client."""
        # Strategy 1: ProgramData JSON (Most Reliable)
        json_path = r"C:\ProgramData\Riot Games\RiotClientInstalls.json"
        rc_path = None

        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    rc_path = data.get("rc_default")
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        # Strategy 2: Common Paths
        if not rc_path or not os.path.exists(rc_path):
            candidates = [
                r"C:\Riot Games\Riot Client\RiotClientServices.exe",
                r"D:\Riot Games\Riot Client\RiotClientServices.exe",
                r"E:\Riot Games\Riot Client\RiotClientServices.exe",
            ]
            for c in candidates:
                if os.path.exists(c):
                    rc_path = c
                    break

        if rc_path and os.path.exists(rc_path):
            try:
                subprocess.Popen(
                    [
                        rc_path,
                        "--launch-product=league_of_legends",
                        "--launch-patchline=live",
                    ]
                )
                print(f"Launched League via: {rc_path}")
            except Exception as e:  # pylint: disable=broad-exception-caught
                print(f"Failed to launch: {e}")
        else:
            print("Riot Client not found.")


class RunePageSelector(ctk.CTkFrame):
    """Selector for Rune Pages."""

    def __init__(self, parent, page_names, on_select, on_close):
        super().__init__(parent, fg_color=Colors.BG_MAIN, corner_radius=0)
        self.pages = sorted(page_names)
        self.on_select = on_select
        self.on_close = on_close

        # Grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        self.header = ctk.CTkFrame(
            self, fg_color=ZLayers.Z1, height=60, corner_radius=0
        )
        self.header.grid(row=0, column=0, sticky="ew")

        self.entry = make_input(
            self.header,
            placeholder="Search Rune Page...",
            width=240,
        )
        self.entry.pack(side="left", padx=(TOKENS.get("spacing.lg"), TOKENS.get("spacing.sm")), pady=TOKENS.get("spacing.sm"))
        self.entry.bind("<KeyRelease>", self.filter_pages)

        # 🔮 Malcolm's UX Enhancement: Predictive Hint
        self.lbl_predictive_hint = ctk.CTkLabel(
            self.header,
            text="",
            font=get_font("body", "bold"),
            text_color=get_color("colors.accent.gold")
        )
        self.lbl_predictive_hint.pack(side="left", padx=(0, TOKENS.get("spacing.sm")))

        # 🔮 Malcolm's UX Enhancement: Enter-to-Lock
        self.entry.bind("<Return>", self._on_enter)

        make_button(
            self.header,
            text="CLOSE",
            width=80,
            style="danger",
            command=self.on_close,
        ).pack(side="right", padx=TOKENS.get("spacing.lg"))

        # Scroll
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.grid(row=1, column=0, sticky="nsew", padx=TOKENS.get("spacing.lg"), pady=TOKENS.get("spacing.lg"))

        self.load_pages()
        self.after(50, self.entry.focus_set)

    def _on_enter(self, event=None):
        # 🔮 Malcolm's UX Enhancement: Enter-to-Lock
        if hasattr(self, "_first_match") and self._first_match:
            self.on_select(self._first_match)

    def load_pages(self, query=""):
        """Load rune pages."""
        for w in self.scroll.winfo_children():
            w.destroy()

        # Unbind Button at top
        make_button(
            self.scroll,
            text="[UNBIND / NONE]",
            style="danger",
            command=lambda: self.on_select(None),
        ).pack(fill="x", pady=2)

        query = query.lower()

        first_match = None

        for p in self.pages:
            if query and query not in p.lower():
                continue

            btn = make_button(
                self.scroll,
                text=p,
                fg_color=get_color("colors.background.card"),
                hover_color=get_color("colors.accent.primary"),
                command=lambda n=p: self.on_select(n),
            )

            if first_match is None:
                first_match = p
                # Visually highlight the predictive hint match
                btn.configure(border_width=2, border_color=get_color("colors.accent.gold"))

            btn.pack(fill="x", pady=2)

        self._first_match = first_match

        # Update hint
        if query and first_match:
            self.lbl_predictive_hint.configure(text=f"↵  Press Enter to lock {first_match}")
        elif query and not first_match:
            self.lbl_predictive_hint.configure(text="No matches found.")
        else:
            self.lbl_predictive_hint.configure(text="")

    def filter_pages(self, event=None):
        """Filter rune pages."""
        _ = event
        self.load_pages(self.entry.get())


class ChampionSelector(ctk.CTkFrame):
    """Full-page champion browser with sticky top bar and scrollable grid."""

    # Extensible sort options: (label, sort_key_fn)
    SORT_OPTIONS = [
        ("A → Z",  lambda k, n: n),
        ("Z → A",  lambda k, n: "".join(reversed(n))),
    ]

    def __init__(self, parent, asset_manager, on_select_callback, on_close_callback):
        super().__init__(parent, fg_color=get_color("colors.background.app"), corner_radius=0)
        self.asset_manager     = asset_manager
        self.on_select         = on_select_callback
        self.on_close          = on_close_callback
        self.buttons           = []
        self.btn_pool          = []
        self.role_btns         = {}
        self._last_width       = 0
        self._active_role      = "ALL"
        self._active_sort_idx  = 0   # index into SORT_OPTIONS
        self.status_label      = None

        # ── Layout skeleton ──────────────────────────────────────────────────
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── TOP CONTROL BAR (sticky) ─────────────────────────────────────────
        self._bar = ctk.CTkFrame(
            self,
            fg_color=get_color("colors.background.panel"),
            corner_radius=0,
            height=56,
        )
        self._bar.grid(row=0, column=0, sticky="ew")
        self._bar.pack_propagate(False)

        # Search
        self.entry_search = make_input(
            self._bar,
            placeholder="🔍  Search champions…",
            width=240,
        )
        self.entry_search.pack(side="left", padx=(16, 10), pady=10)
        self.entry_search.bind("<KeyRelease>", self._on_search)

        # 🔮 Malcolm's UX Enhancement: Predictive Hint
        # Displays the top search match so users know what they are about to select.
        # This reduces friction by clearly showing the outcome before confirming.
        self.lbl_predictive_hint = ctk.CTkLabel(
            self._bar,
            text="",
            font=get_font("body", "bold"),
            text_color=get_color("colors.accent.gold")
        )
        self.lbl_predictive_hint.pack(side="left", padx=(10, 0))

        # Bind Enter key to search entry
        self.entry_search.bind("<Return>", self._on_enter)


        # Role filter buttons
        self._role_frame = ctk.CTkFrame(self._bar, fg_color="transparent")
        self._role_frame.pack(side="left", padx=(0, 10))
        self._build_role_filters()

        # Sort dropdown
        sort_labels = [s[0] for s in self.SORT_OPTIONS]
        self._sort_var = ctk.StringVar(value=sort_labels[0])
        self._sort_menu = ctk.CTkOptionMenu(
            self._bar,
            values=sort_labels,
            variable=self._sort_var,
            width=110,
            height=32,
            font=get_font("caption"),
            fg_color=get_color("colors.background.card"),
            button_color=get_color("colors.background.card"),
            button_hover_color=get_color("colors.accent.primary"),
            dropdown_fg_color=get_color("colors.background.panel"),
            command=self._on_sort_change,
        )
        self._sort_menu.pack(side="left", padx=(0, 10))

        # Close button — right side
        make_button(
            self._bar,
            text="CLOSE",
            width=80,
            style="danger",
            command=self.on_close,
        ).pack(side="right", padx=16)

        # Thin separator
        ctk.CTkFrame(self, fg_color=get_color("colors.background.card"), height=1).grid(
            row=0, column=0, sticky="sew"
        )

        # ── SCROLLABLE CONTENT AREA ──────────────────────────────────────────
        self.scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=get_color("colors.accent.primary"),
            scrollbar_button_hover_color=get_color("colors.accent.blue"),
        )
        self.scroll.grid(row=1, column=0, sticky="nsew", padx=16, pady=12)
        self.scroll.bind("<Configure>", self._on_resize)

        # Defer first load until after the window geometry is resolved
        self.after(100, self._load)
        self.after(140, lambda: self.entry_search.focus_set())


    def _on_enter(self, event=None):
        # 🔮 Malcolm's UX Enhancement: Enter-to-Lock
        # Allows power users to type a champion name and immediately lock it in
        # using the Enter key without having to reach for the mouse.
        if hasattr(self, "_first_champ_spec") and self._first_champ_spec:
            # Execute the command of the first matching champion
            self._first_champ_spec["cmd"]()

    # ── Role filter builder ──────────────────────────────────────────────────


    def _build_role_filters(self):
        roles = ["ALL", "TOP", "JUNGLE", "MIDDLE", "BOTTOM", "SUPPORT"]
        labels = {"ALL": "All", "TOP": "Top", "JUNGLE": "Jng",
                  "MIDDLE": "Mid", "BOTTOM": "Bot", "SUPPORT": "Sup"}
        tooltips = {"ALL": "Show All", "TOP": "Top Lane", "JUNGLE": "Jungle",
                    "MIDDLE": "Mid Lane", "BOTTOM": "Bot Lane", "SUPPORT": "Support"}

        for r in roles:
            asset_key = "UTILITY" if r == "SUPPORT" else r
            icon = self.asset_manager.get_role_icon(asset_key, size=(18, 18)) if r != "ALL" else None

            btn = ctk.CTkButton(
                self._role_frame,
                text=labels[r],
                image=icon,
                compound="left" if icon else "center",
                width=52,
                height=30,
                font=get_font("caption"),
                corner_radius=4,
                fg_color=get_color("colors.background.card"),
                hover_color=get_color("colors.accent.primary"),
                command=lambda x=r: self._on_role(x),
            )
            btn.pack(side="left", padx=2)
            CTkTooltip(btn, tooltips[r])
            self.role_btns[r] = btn

        self._highlight_role("ALL")

    def _highlight_role(self, active):
        for r, btn in self.role_btns.items():
            btn.configure(
                fg_color=get_color("colors.accent.primary") if r == active
                else get_color("colors.background.card")
            )

    # ── Event handlers ───────────────────────────────────────────────────────

    def _on_role(self, role):
        self._active_role = role
        self._highlight_role(role)
        self._load()

    def _on_search(self, _event=None):
        self._load()

    def _on_sort_change(self, label):
        for i, (lbl, _) in enumerate(self.SORT_OPTIONS):
            if lbl == label:
                self._active_sort_idx = i
                break
        self._load()

    def _on_resize(self, event):
        w = event.width
        if w < 10:
            return
        if abs(w - self._last_width) > 20:
            self._last_width = w
            # Using _load to refresh grid with new width
            self._load()

    # ── Core load / filter / sort ─────────────────────────────────────────────

    def _load(self):
        txt     = self.entry_search.get().strip().lower()
        role    = self._active_role
        sort_fn = self.SORT_OPTIONS[self._active_sort_idx][1]

        # Build item spec list (no widgets yet)
        items = []

        # Special: NONE
        if not txt or "none" in txt:
            items.append({
                "text": "NONE", "icon": None, "compound": "center",
                "cmd": lambda: self.on_select(None),
                "fg": get_color("colors.state.danger"), "hover": "#c62828",
                "tip": "Clear selection",
            })

        # Special: Bravery
        if not txt or "brav" in txt:
            items.append({
                "text": "Bravery",
                "icon": None,
                "champ_key": "Bravery",
                "compound": "top",
                "cmd": lambda: self.on_select("Bravery"),
                "fg": get_color("colors.accent.blue"),
                "hover": get_color("colors.accent.primary"),
                "tip": "Random champion (Ultimate Bravery)",
            })

        if self.asset_manager.champ_data:
            champ_list = []
            for k, v in self.asset_manager.champ_data.items():
                name = v.get("name", k)
                if txt and txt not in name.lower() and txt not in k.lower():
                    continue
                if role != "ALL":
                    cid = self.asset_manager.get_champ_id(k)
                    target_role = "UTILITY" if role == "SUPPORT" else role
                    roles = self.asset_manager.get_champ_roles(cid) if cid else []
                    if target_role not in roles:
                        continue
                champ_list.append((k, name))

            champ_list.sort(key=lambda x: sort_fn(x[0], x[1]))

            first_champ_spec = None
            for champ_key, display_name in champ_list:
                spec = {
                    "text": display_name,
                    "icon": None,  # Will be loaded async
                    "champ_key": champ_key,
                    "compound": "top", # Assume icon will load
                    "cmd": (lambda k=champ_key: lambda: self.on_select(k))(),
                    "fg": get_color("colors.background.card"),
                    "hover": get_color("colors.accent.primary"),
                    "tip": display_name,
                }
                items.append(spec)
                if first_champ_spec is None:
                    first_champ_spec = spec
                    # Visually highlight the predictive hint match
                    spec["border_width"] = 2
                    spec["border_color"] = get_color("colors.accent.gold")

            self._first_champ_spec = first_champ_spec

            # Update hint
            if txt and first_champ_spec:
                self.lbl_predictive_hint.configure(text=f"↵  Press Enter to lock {first_champ_spec['text']}")
            elif txt and not first_champ_spec:
                self.lbl_predictive_hint.configure(text="No matches found.")
            else:
                self.lbl_predictive_hint.configure(text="")

        self._update_grid(items)

    # ── Layout builder (Pooled) ───────────────────────────────────────────────

    def _on_icon_loaded(self, img, btn, key):
        """Callback for async icon loading."""
        try:
            # Verify button still exists and is assigned to the same champion
            if getattr(btn, "winfo_exists", lambda: False)() and getattr(btn, "champion_key", None) == key:
                if img:
                    btn.configure(image=img, text="")
                else:
                    # Fallback to text if image download fails
                    btn.configure(image=None, text=key[:2], compound="center")
        except Exception:
            pass

    def _update_grid(self, items):
        """
        Efficiently updates the grid by reusing buttons from a pool.
        This avoids destroying and recreating widgets on every filter change.
        """
        if hasattr(self, "status_label") and getattr(self, "status_label", None):
             self.status_label.grid_forget()

        if not items:
            self.status_label = ctk.CTkLabel(self.scroll, text="No champions found.",
                               font=get_font("body"), text_color="gray")
            self.status_label.grid(row=0, column=0, pady=20, sticky="ew")
            # Hide all buttons
            for btn in self.btn_pool:
                btn.grid_forget()
            return

        w = self._last_width or max(self.scroll.winfo_width(), 400)
        cols = max(2, int(w) // 92)

        # Update existing buttons / Create new ones
        for i, spec in enumerate(items):
            if i < len(self.btn_pool):
                btn = self.btn_pool[i]
            else:
                btn = ctk.CTkButton(
                    self.scroll,
                    width=80,
                    height=88,
                    font=get_font("caption"),
                    corner_radius=6,
                )
                self.btn_pool.append(btn)

            # Content
            btn.configure(
                text=spec.get("text", ""),
                image=spec.get("icon", None),
                compound=spec.get("compound", "center"),
                fg_color=spec.get("fg", "transparent"),
                hover_color=spec.get("hover", "gray"),
                command=spec.get("cmd", lambda: None),
                border_width=spec.get("border_width", 0),
                border_color=spec.get("border_color", "transparent")
            )

            # Async Icon Loading
            champ_key = spec.get("champ_key")
            btn.champion_key = champ_key # Bind key to button for callback verification

            if champ_key:
                # Start async fetch
                self.asset_manager.get_icon_async(
                    "champion",
                    champ_key,
                    lambda img, b=btn, k=champ_key: self._on_icon_loaded(img, b, k),
                    size=(50, 50),
                    widget=self
                )

            # Tooltip
            if hasattr(btn, "tooltip_ref") and btn.tooltip_ref:
                btn.tooltip_ref.text = spec["tip"]
            else:
                btn.tooltip_ref = CTkTooltip(btn, spec["tip"])

            # Layout
            row = i // cols
            col = i % cols
            btn.grid(row=row, column=col, padx=5, pady=5)

        # Hide unused buttons
        for i in range(len(items), len(self.btn_pool)):
            self.btn_pool[i].grid_forget()

        # Force canvas scrollregion update
        self.after(50, self._fix_scrollregion)

    def _fix_scrollregion(self):
        try:
            canvas = self.scroll._parent_canvas
            canvas.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))
            # Second pass: reflow if real width differs from what we used
            w = self.scroll.winfo_width()
            if w > 10 and abs(w - self._last_width) > 30:
                self._last_width = w
                self._load()
        except Exception:
            pass

    # ── Resize ────────────────────────────────────────────────────────────────

    def _deferred_repack(self):
        self._fix_scrollregion()

    def _pack_rows(self, _width=None):
        self._load()

    def _regrid(self, _width=None):
        self._load()

    # ── Legacy shims ──────────────────────────────────────────────────────────

    def load_champs(self, txt_filter="", role_filter="ALL"):
        self._active_role = role_filter
        self._highlight_role(role_filter)
        if txt_filter:
            self.entry_search.delete(0, "end")
            self.entry_search.insert(0, txt_filter)
        self._load()

    def filter_champs(self, event=None):
        self._on_search(event)


