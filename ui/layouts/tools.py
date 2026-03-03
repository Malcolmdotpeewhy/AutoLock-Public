"""
Tools & System Tab
Combines: Quick Actions, Client Control, Asset Management.
"""
import os
import shutil
import subprocess
import sys
import threading
import customtkinter as ctk
import ctypes
from PIL import Image

from utils.path_utils import resource_path
from ..ui_shared import (
    CTkTooltip, make_panel, make_button, make_input, 
    apply_hover_brightness, lighten_color, 
    get_color, get_font, TOKENS
)


class ToolsTab(ctk.CTkFrame):
    def __init__(self, parent, lcu, assets, config):
        super().__init__(parent, fg_color=get_color("colors.background.panel"), corner_radius=0)
        self.lcu = lcu
        self.assets = assets
        self.config = config

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.content = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=0, sticky="nsew", padx=TOKENS.get("spacing.md"), pady=TOKENS.get("spacing.md"))

        # Header
        ctk.CTkLabel(
            self.content, text="TOOLS & SYSTEM",
            font=get_font("title"), text_color=get_color("colors.accent.gold"),
        ).pack(anchor="w", pady=(0, TOKENS.get("spacing.xs")))
        ctk.CTkLabel(
            self.content,
            text="Client control, asset management, and system tasks.",
            font=get_font("body"), text_color=get_color("colors.text.secondary"),
        ).pack(anchor="w", pady=(0, TOKENS.get("spacing.sm")))
        # Glow underline
        ctk.CTkFrame(
            self.content, height=1, fg_color=get_color("colors.accent.gold"),
        ).pack(fill="x", pady=(0, TOKENS.get("spacing.xl")))

        # ========== TOOLS SECTIONS ==========
        # 1. Quick Actions (Moved to Top)
        self._build_quick_actions()
        
        # 2. Client Control (With Logo)
        self._build_client_control()
        
        # 3. Hotkey Settings
        self._build_hotkey_settings()
        
        # 4. Other Tools (Asset Management)
        self._build_asset_management()

        # Footer
        ctk.CTkLabel(
            self.content,
            text="Zero-G Architect V13 | Build 2026.1",
            font=get_font("caption"), text_color=get_color("colors.text.muted"),
        ).pack(pady=TOKENS.get("spacing.lg"))

    # ──────── QUICK ACTIONS (First) ────────
    # ──────── QUICK ACTIONS (First) ────────
    def _build_quick_actions(self):
        panel = make_panel(self.content, title="Quick Actions")
        panel.pack(fill="x", pady=(0, TOKENS.get("spacing.lg")), ipady=TOKENS.get("spacing.md")) # Pack outer
        
        row = ctk.CTkFrame(panel._content, fg_color="transparent") # Pack into _content
        row.pack(fill="x", padx=TOKENS.get("spacing.md"))

        make_button(row, "Open Logs", style="secondary", command=self._action_open_logs).pack(
            side="left", padx=TOKENS.get("spacing.sm")
        )
        make_button(row, "Clear Cache", style="secondary", command=self._action_clear_cache).pack(
            side="left", padx=TOKENS.get("spacing.sm")
        )
        # Always on Top Toggle
        self.switch_top = ctk.CTkSwitch(
            row, 
            text="Always on Top",
            command=self._toggle_always_on_top,
            font=get_font("body"),
            progress_color=get_color("colors.state.success"),
        )
        self.switch_top.pack(side="left", padx=TOKENS.get("spacing.sm"))
        # Set initial state
        if self._get_config("always_on_top", True):
            self.switch_top.select()
        else:
            self.switch_top.deselect()

        # Reboot Group
        reboot_frame = ctk.CTkFrame(row, fg_color="transparent")
        reboot_frame.pack(side="right", padx=TOKENS.get("spacing.sm"))

        # Logo next to Reboot
        try:
            logo_path = resource_path("assets/app_icon.png")
            if os.path.exists(logo_path):
                logo_img = ctk.CTkImage(Image.open(logo_path), size=(60, 60))
                ctk.CTkLabel(reboot_frame, text="", image=logo_img).pack(side="left", padx=(0, 5))
        except Exception:
            pass

        make_button(reboot_frame, "Reboot App", style="danger", command=self._action_reboot).pack(
            side="left"
        )

    # ──────── CLIENT CONTROL ────────
    # ──────── CLIENT CONTROL ────────
    def _build_client_control(self):
        panel = make_panel(self.content, title="Client Control")
        panel.pack(fill="x", pady=(0, TOKENS.get("spacing.lg")), ipady=TOKENS.get("spacing.md"))

        # Logo Display


        row = ctk.CTkFrame(panel._content, fg_color="transparent")
        row.pack(anchor="center", pady=TOKENS.get("spacing.xs"))

        try:
            logo_path = resource_path("assets/lol_logo.png") # Updated to League branding
            if os.path.exists(logo_path):
                pil_img = Image.open(logo_path)
                # Resize to fit button area nicely
                target_w = 200
                ratio = target_w / float(pil_img.width)
                target_h = int(float(pil_img.height) * float(ratio))
                
                img_btn = ctk.CTkImage(pil_img, size=(target_w, target_h))
                
                self.btn_launch = make_button(
                    row, 
                    text="", 
                    icon=img_btn, 
                    fg_color="transparent", 
                    hover_color=get_color("colors.state.hover"),
                    width=target_w,
                    height=target_h,
                    command=self.launch_client
                )
                self.btn_launch.pack(side="left", padx=TOKENS.get("spacing.xs"))
            else:
                self.btn_launch = make_button(row, "Launch Client", style="primary",
                                              width=160, command=self.launch_client)
                self.btn_launch.pack(side="left", padx=TOKENS.get("spacing.xs"))
        except Exception:
            self.btn_launch = make_button(row, "Launch Client", style="primary",
                                          width=160, command=self.launch_client)
            self.btn_launch.pack(side="left", padx=TOKENS.get("spacing.xs"))
        
        CTkTooltip(self.btn_launch, "Launch the League of Legends client.")

        self.btn_restart = make_button(row, "Restart Client UX", style="secondary",
                                       width=160, command=self.restart_ux)
        self.btn_restart.pack(side="left", padx=TOKENS.get("spacing.xs"))
        CTkTooltip(self.btn_restart, "Restart UX to fix visual glitches.")

        self.lc_path_entry = make_input(
            panel._content, placeholder="Manual Riot Client Path (Optional)", width=300
        )
        self.lc_path_entry.pack(anchor="center", pady=(TOKENS.get("spacing.sm"), 0))

        self.lbl_launch_status = ctk.CTkLabel(
            panel._content, text="", font=get_font("caption"), text_color=get_color("colors.text.muted")
        )
        self.lbl_launch_status.pack(anchor="center", pady=(0, TOKENS.get("spacing.xs")))

    # ──────── HOTKEY SETTINGS ────────
    def _build_hotkey_settings(self):
        panel = make_panel(self.content, title="Hotkey Settings (Requires Restart)")
        panel.pack(fill="x", pady=(0, TOKENS.get("spacing.lg")), ipady=TOKENS.get("spacing.md"))
        
        self.hotkeys = {
            "hotkey_find_match": {"label": "Find Match (Global)", "default": "ctrl+shift+f"},
            "hotkey_compact_mode": {"label": "Toggle Compact Mode", "default": "ctrl+shift+m"},
            "hotkey_launch_client": {"label": "Launch League Client", "default": "ctrl+shift+l"}
        }
        
        self.hotkey_vars = {}
        for key, data in self.hotkeys.items():
            row = ctk.CTkFrame(panel._content, fg_color="transparent")
            row.pack(fill="x", padx=TOKENS.get("spacing.md"), pady=(0, TOKENS.get("spacing.xs")))
            
            lbl = ctk.CTkLabel(row, text=data["label"], font=get_font("body"), width=160, anchor="w")
            lbl.pack(side="left")
            
            entry = make_input(row, placeholder=data["default"], width=150)
            entry.insert(0, self._get_config(key, data["default"]))
            entry.pack(side="left", padx=TOKENS.get("spacing.sm"))
            self.hotkey_vars[key] = entry
            
        btn_save = make_button(panel._content, "Save Hotkeys", style="primary", command=self._save_hotkeys)
        btn_save.pack(anchor="w", padx=TOKENS.get("spacing.md"), pady=(TOKENS.get("spacing.sm"), 0))

    def _save_hotkeys(self):
        for key, entry in self.hotkey_vars.items():
            val = entry.get().strip()
            if val:
                self._set_config(key, val)
        self.lbl_launch_status.configure(text="Hotkeys saved! Restart app to apply.", text_color=get_color("colors.state.success"))

    # ──────── ASSET MANAGEMENT ────────
    def _build_asset_management(self):
        panel = make_panel(self.content, title="Asset Management")
        panel.pack(fill="x", pady=(0, TOKENS.get("spacing.lg")), ipady=TOKENS.get("spacing.md"))

        self.btn_dl_icons = make_button(panel._content, "Download All Assets", style="primary",
                                         command=self.download_all_assets_ui)
        self.btn_dl_icons.pack(anchor="w", padx=TOKENS.get("spacing.md"), pady=TOKENS.get("spacing.xs"))

        self.lbl_asset_status = ctk.CTkLabel(
            panel._content, text="Cache status: Idle", font=get_font("caption"), text_color=get_color("colors.text.muted"),
        )
        self.lbl_asset_status.pack(anchor="w", padx=TOKENS.get("spacing.md"), pady=(0, TOKENS.get("spacing.xs")))

        self.progress_assets = ctk.CTkProgressBar(
            panel._content, height=6, fg_color=get_color("colors.background.panel"), progress_color=get_color("colors.accent.primary"),
        )
        # Only shown when active

    # ═══════════════════════════════════════
    #  TOOL ACTIONS (UI Wrappers)
    # ═══════════════════════════════════════
    def _run_threaded(self, func, *args):
        threading.Thread(target=func, args=args, daemon=True).start()

    def launch_client(self):
        self._run_threaded(self._launch_client_thread)

    def restart_ux(self):
        self._run_threaded(self._restart_ux_thread)

    def download_all_assets_ui(self):
        self.btn_dl_icons.configure(state="disabled", text="Scanning...")
        self.progress_assets.pack(fill="x", padx=TOKENS.get("spacing.md"), pady=TOKENS.get("spacing.xs"))
        self.progress_assets.set(0)
        threading.Thread(target=self._dl_assets_thread, daemon=True).start()

    def _dl_assets_thread(self):
        def progress(curr, total, msg):
            pct = curr / total if total > 0 else 0
            self.after(0, lambda: self._update_dl_ui(pct, msg, curr == total))
        self.assets.download_all_app_assets(progress_callback=progress)

    def _update_dl_ui(self, pct, msg, done):
        self.progress_assets.set(pct)
        self.lbl_asset_status.configure(text=msg)
        if done:
            self.btn_dl_icons.configure(state="normal", text="Download All Assets")
            self.lbl_asset_status.configure(text_color=get_color("colors.state.success"))

    # ═══════════════════════════════════════
    #  QUICK ACTION HANDLERS
    # ═══════════════════════════════════════
    def _action_open_logs(self):
        log_file = "debug.log"
        if os.path.exists(log_file):
            if sys.platform == "win32":
                os.startfile(log_file)
            else:
                opener = "open" if sys.platform == "darwin" else "xdg-open"
                subprocess.call([opener, log_file])

    def _action_clear_cache(self):
        from services.asset_manager import CACHE_DIR
        if os.path.exists(CACHE_DIR):
            try:
                shutil.rmtree(CACHE_DIR)
                os.makedirs(CACHE_DIR, exist_ok=True)
                self.lbl_asset_status.configure(text="Cache cleared!", text_color=get_color("colors.state.success"))
            except Exception:
                pass

    def _action_reboot(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Confirm Reboot")
        dialog.geometry("300x150")
        dialog.attributes("-topmost", True)
        
        # Center the dialog
        dialog.update_idletasks()
        try:
            x = self.winfo_rootx() + (self.winfo_width() // 2) - (300 // 2)
            y = self.winfo_rooty() + (self.winfo_height() // 2) - (150 // 2)
            dialog.geometry(f"+{x}+{y}")
        except Exception:
            pass

        ctk.CTkLabel(dialog, text="Restart AutoLock?", font=get_font("body")).pack(pady=TOKENS.get("spacing.md"))
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=TOKENS.get("spacing.sm"))

        def _do_reboot():
            dialog.destroy()
            try:
                print("Rebooting System...")
                if getattr(sys, "frozen", False):
                    # Running as compiled EXE — use DETACHED_PROCESS so the child
                    # outlives this process after os._exit(0).
                    DETACHED_PROCESS = 0x00000008
                    CREATE_NEW_PROCESS_GROUP = 0x00000200
                    subprocess.Popen(
                        [sys.executable] + sys.argv[1:],
                        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                        close_fds=True,
                    )
                else:
                    # Running as Python Script (Dev)
                    subprocess.Popen(
                        [sys.executable, "-m", "core.main"] + sys.argv[1:],
                        creationflags=0x00000008 | 0x00000200,
                        close_fds=True,
                    )
                # Brief pause lets the OS register the child before we exit
                import time
                time.sleep(0.4)
                os._exit(0)
            except Exception as e:
                print(f"Reboot failed: {e}")

        make_button(btn_frame, "Restart", style="danger", width=100, command=_do_reboot).pack(
            side="left", padx=TOKENS.get("spacing.sm")
        )
        make_button(btn_frame, "Cancel", style="secondary", width=100, command=dialog.destroy).pack(
            side="left", padx=TOKENS.get("spacing.sm")
        )
    
    def _toggle_always_on_top(self):
        val = bool(self.switch_top.get())
        self.config.set("always_on_top", val)

    def _get_config(self, key, default):
        return self.config.get(key, default)
    
    def _set_config(self, key, val):
        self.config.set(key, val)

    # ═══════════════════════════════════════
    #  WORKER THREADS
    # ═══════════════════════════════════════
    def _launch_client_thread(self):
        self.lbl_launch_status.configure(text="Searching for client...", text_color=get_color("colors.text.muted"))
        import winreg

        path = None
        if hasattr(self, "lc_path_entry"):
            path = self.lc_path_entry.get().strip()
            if path and not os.path.exists(path):
                path = None # Invalid manual path, fall back to auto

        try:
            if not path:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Riot Games\Riot Client")
            path, _ = winreg.QueryValueEx(key, "InstallPath")
            path = os.path.join(path, "RiotClientServices.exe")
            winreg.CloseKey(key)
        except Exception:
            pass

        if not path or not os.path.exists(path):
            potential_paths = [
                r"C:\Riot Games\Riot Client\RiotClientServices.exe",
                r"D:\Riot Games\Riot Client\RiotClientServices.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Riot Games\Riot Client\RiotClientServices.exe"),
                os.path.expanduser(r"~\Riot Games\Riot Client\RiotClientServices.exe"),
                r"C:\Program Files\Riot Games\Riot Client\RiotClientServices.exe",
                r"C:\Program Files (x86)\Riot Games\Riot Client\RiotClientServices.exe",
            ]
            path = next((p for p in potential_paths if os.path.exists(p)), None)

        if path and os.path.exists(path):
            try:
                # Use ShellExecute to handle UAC/Elevation requirements (Fixes WinError 740)
                params = "--launch-product=league_of_legends --launch-patchline=live"
                result = ctypes.windll.shell32.ShellExecuteW(None, "open", path, params, None, 1)
                
                # result > 32 indicates success
                if result > 32:
                    self.lbl_launch_status.configure(text="Launch command sent!", text_color=get_color("colors.state.success"))
                else:
                    self.lbl_launch_status.configure(text=f"Launch failed (Code: {result})", text_color=get_color("colors.state.danger"))
            except Exception as e:
                self.lbl_launch_status.configure(text=f"Error: {e}", text_color=get_color("colors.state.danger"))
        else:
            self.lbl_launch_status.configure(text="RiotClientServices.exe not found.", text_color=get_color("colors.state.danger"))

    def _restart_ux_thread(self):
        if not self.lcu.is_connected:
            return
        self.lcu.request("POST", "/riotclient/kill-and-restart-ux")
