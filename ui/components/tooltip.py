"""Tooltip component."""
import tkinter
import customtkinter as ctk
from ..components.factory import get_color, get_font, parse_border, TOKENS

class CTkTooltip:
    """
    Custom Tooltip for CTk Widgets.
    Uses standard tkinter.Toplevel to avoid icon glitches with CTk Toplevels.
    """
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip = None
        self.widget.bind("<Enter>", self.show, add="+")
        self.widget.bind("<Leave>", self.hide, add="+")

    def show(self, event=None):
        """Show the tooltip."""
        try:
            x = self.widget.winfo_rootx() + 25
            y = self.widget.winfo_rooty() + 25

            self.tooltip = tkinter.Toplevel(self.widget)
            self.tooltip.wm_overrideredirect(True)
            self.tooltip.wm_geometry(f"+{x}+{y}")
            self.tooltip.configure(bg=get_color("colors.background.card"))

            frame = ctk.CTkFrame(
                self.tooltip,
                corner_radius=TOKENS.get("radius.sm"),
                fg_color=get_color("colors.background.card"),
                border_color=parse_border("subtle")[1],
                border_width=1,
            )
            frame.pack()

            label = ctk.CTkLabel(
                frame,
                text=self.text,
                bg_color="transparent",
                text_color=get_color("colors.text.primary"),
                padx=10,
                pady=5,
                font=get_font("body"),
            )
            label.pack()
        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"Tooltip Error: {e}")

    def hide(self, event=None):
        """Hide the tooltip."""
        if self.tooltip:
            try:
                # CTk widgets inside Toplevels will crash if destroyed during an event loop.
                # Withdraw first to hide immediately, then safely request teardown.
                tw = self.tooltip
                self.tooltip = None
                tw.withdraw()
                tw.after(50, tw.destroy)
            except Exception:  # pylint: disable=broad-exception-caught
                pass
            self.tooltip = None
