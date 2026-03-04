import time
import customtkinter as ctk
from .factory import get_color, get_font, parse_border, TOKENS

class ToastNotification(ctk.CTkFrame):
    """
    A sleek, actionable toast notification with a progress timeline.
    """
    def __init__(self, parent, title, message, type="info", duration=4000, action_text=None, action_cmd=None, on_dismiss=None, **kwargs):
        super().__init__(parent, fg_color=get_color("colors.background.card"),
                         corner_radius=TOKENS.get("radius.sm"),
                         border_width=1, border_color=parse_border("subtle")[1], **kwargs)

        self.duration = duration
        self.remaining = duration
        self.is_dismissed = False
        self.is_paused = False
        self.on_dismiss = on_dismiss
        self._progress_job = None

        # Determine colors and icon
        if type == "success":
            color = get_color("colors.state.success")
            icon = "✨"
        elif type == "error":
            color = get_color("colors.state.danger")
            icon = "⚠️"
        elif type == "warning":
            color = get_color("colors.state.warning")
            icon = "🔔"
        else:
            color = get_color("colors.accent.primary")
            icon = "ℹ️"

        self.configure(border_color=color)

        self.grid_columnconfigure(1, weight=1)

        lbl_icon = ctk.CTkLabel(self, text=icon, font=("Arial", 20), text_color=color)
        lbl_icon.grid(row=0, column=0, rowspan=2, padx=(12, 8), pady=(12, 8), sticky="n")

        lbl_title = ctk.CTkLabel(self, text=title, font=get_font("body", "bold"), text_color=get_color("colors.text.primary"), anchor="w")
        lbl_title.grid(row=0, column=1, sticky="ew", pady=(10, 0), padx=(0, 8))

        lbl_msg = ctk.CTkLabel(self, text=message, font=get_font("caption"), text_color=get_color("colors.text.secondary"), anchor="w", justify="left", wraplength=220)
        lbl_msg.grid(row=1, column=1, sticky="ew", pady=(0, 10), padx=(0, 8))

        if action_text and action_cmd:
            btn_action = ctk.CTkButton(self, text=action_text, width=60, height=28,
                                       font=get_font("caption", "bold"), fg_color=color, hover_color=color, text_color=get_color("colors.background.app"),
                                       command=lambda: [action_cmd(), self.dismiss()])
            btn_action.grid(row=0, column=2, rowspan=2, padx=12, pady=12)
        else:
            btn_close = ctk.CTkButton(self, text="✕", width=24, height=24, fg_color="transparent",
                                      hover_color=get_color("colors.state.hover"), text_color=get_color("colors.text.muted"),
                                      command=self.dismiss)
            btn_close.grid(row=0, column=2, rowspan=2, padx=8, pady=12, sticky="ne")

        # Progress bar
        self.progress = ctk.CTkProgressBar(self, height=4, fg_color="transparent", progress_color=color, corner_radius=0)
        self.progress.grid(row=2, column=0, columnspan=3, sticky="ew", padx=2, pady=(0, 2))
        self.progress.set(1.0)

        # Click to dismiss
        self.bind("<Button-1>", lambda e: self.dismiss())
        lbl_title.bind("<Button-1>", lambda e: self.dismiss())
        lbl_msg.bind("<Button-1>", lambda e: self.dismiss())

        # 🔮 Malcolm's UX Enhancement: Pause on Hover
        # Prevents toasts from disappearing while the user is actively reading them,
        # greatly improving accessibility and reducing cognitive load.
        def _on_enter(e):
            self.is_paused = True
        def _on_leave(e):
            self.is_paused = False

        self.bind("<Enter>", _on_enter)
        self.bind("<Leave>", _on_leave)

        # Bind to all immediate children to prevent flickering when hovering over text
        for child in self.winfo_children():
            child.bind("<Enter>", _on_enter, add="+")
            child.bind("<Leave>", _on_leave, add="+")

        self._update_progress()

    def _update_progress(self):
        if self.is_dismissed:
            return

        if not self.is_paused:
            self.remaining -= 30

        if self.remaining <= 0:
            self.dismiss()
        else:
            self.progress.set(self.remaining / self.duration)
            self._progress_job = self.after(30, self._update_progress)

    def dismiss(self):
        if self.is_dismissed:
            return
        self.is_dismissed = True
        if self._progress_job:
            self.after_cancel(self._progress_job)
            self._progress_job = None

        # Notify manager to remove from active list and reposition others
        if self.on_dismiss:
            self.on_dismiss(self)

        # 🔮 Malcolm's UX Enhancement: Smooth Exit Animation
        self._animate_out()

    def _animate_out(self):
        try:
            current_relx = float(self.place_info().get('relx', 0.98))
        except Exception:
            self.destroy()
            return

        def step():
            nonlocal current_relx
            if not self.winfo_exists(): return
            current_relx += 0.02
            if current_relx >= 1.2:
                self.destroy()
            else:
                self.place_configure(relx=current_relx)
                self.after(16, step)
        step()

class ToastManager:
    """Manages stacked toast notifications overlaid on the app."""
    _instance = None

    @classmethod
    def get_instance(cls, root=None):
        if cls._instance is None and root is not None:
            cls._instance = cls(root)
        return cls._instance

    def __init__(self, root):
        self.root = root
        self.toasts = []
        # Bind to root configure to reposition toasts when window is resized
        self.root.bind("<Configure>", self._on_root_configure, add="+")
        self._last_height = self.root.winfo_height()

    def _on_root_configure(self, event):
        # Only reposition if the height actually changed to avoid spamming
        if event.widget == self.root:
            if event.height != self._last_height:
                self._last_height = event.height
                self._reposition_toasts()

    def show_toast(self, title, message, type="info", duration=4000, action_text=None, action_cmd=None):
        toast = ToastNotification(self.root, title, message, type, duration, action_text, action_cmd, on_dismiss=self._on_toast_destroyed)

        self.toasts.append(toast)
        # Place it off-screen first to get its dimensions
        toast.place(relx=1.2, rely=1.0)
        self.root.update_idletasks()

        self._reposition_toasts()
        self._animate_in(toast)

    def _on_toast_destroyed(self, toast):
        if toast in self.toasts:
            self.toasts.remove(toast)
            self._reposition_toasts()

    def _reposition_toasts(self):
        target_y = self.root.winfo_height() - 20

        for toast in reversed(self.toasts):
            if toast.winfo_exists():
                toast.update_idletasks()
                h = toast.winfo_reqheight()
                toast.target_y = target_y
                target_y -= (h + 10)

                if getattr(toast, "is_in", False):
                    toast.place_configure(rely=None, y=toast.target_y, relx=0.98, anchor="se")

    def _animate_in(self, toast):
        current_relx = 1.1
        toast.place(relx=current_relx, rely=None, y=getattr(toast, "target_y", self.root.winfo_height() - 20), anchor="se")

        def step():
            nonlocal current_relx
            if not toast.winfo_exists() or toast.is_dismissed: return

            current_relx -= 0.015
            if current_relx <= 0.98:
                current_relx = 0.98
                toast.is_in = True
                toast.place_configure(relx=current_relx)
            else:
                toast.place_configure(relx=current_relx)
                self.root.after(16, step)

        step()
