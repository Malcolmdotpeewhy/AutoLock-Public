"""Hover animation utilities."""
from .color_utils import lighten_color

def _apply_hover(widget, normal_fg, hover_fg, normal_border, hover_border):
    """Bind hover animation to a widget for brightness transition."""
    def on_enter(e):  # pylint: disable=unused-argument
        try:
            widget.configure(fg_color=hover_fg, border_color=hover_border)
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    def on_leave(e):  # pylint: disable=unused-argument
        try:
            widget.configure(fg_color=normal_fg, border_color=normal_border)
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    widget.bind("<Enter>", on_enter)
    widget.bind("<Leave>", on_leave)


def apply_hover_brightness(widget, normal_color, boost_percent=8):
    """Simple hover brightness boost for any CTk widget with fg_color."""
    hover_color = lighten_color(normal_color, boost_percent)

    def on_enter(e):  # pylint: disable=unused-argument
        try:
            widget.configure(fg_color=hover_color)
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    def on_leave(e):  # pylint: disable=unused-argument
        try:
            widget.configure(fg_color=normal_color)
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    widget.bind("<Enter>", on_enter)
    widget.bind("<Leave>", on_leave)


def apply_press_effect(widget, normal_color, press_color=None):
    """
    Bind press animation (click down/up).
    If press_color is None, it defaults to normal_color (no change) or could be calculated.
    For now, we will perform a slight darken if no press_color is provided.
    """
    from .color_utils import darken_color
    
    active_color = press_color or darken_color(normal_color, 10)

    def on_press(e):
        try:
            widget.configure(fg_color=active_color)
        except Exception:
            pass

    def on_release(e):
        try:
            # We assume the mouse is still hovering, so we might want to return to 
            # hover state if possible, but simplest is return to normal and let hover re-trigger
            # or rely on the hover handler to fix it on next move.
            # Ideally, we restore normal, then let hover take over.
            widget.configure(fg_color=normal_color)
            # If the mouse is still inside, the hover handler <Enter> won't trigger again 
            # automatically unless we move. 
            # A robust system would track state. For now, we revert to normal.
        except Exception:
            pass

    widget.bind("<ButtonPress-1>", on_press, add="+")
    widget.bind("<ButtonRelease-1>", on_release, add="+")
