"""
New UI Component Factory using Design Tokens.
Centralizes the creation of styled widgets (Panels, Cards, Buttons) ensuring visual consistency.
"""
import customtkinter as ctk
from PIL import Image
from ..theme.token_loader import TOKENS
from .hover import apply_hover_brightness, apply_press_effect

# ... (omitted)

# --- Token Parsing Helpers ---

def get_color(path, default="#000000"):
    """Retrieve color from tokens."""
    return TOKENS.get(*path.split("."), default=default)

def get_radius(size="md"):
    """Retrieve corner radius."""
    return TOKENS.get("radius", size, default=10)

def get_font(type="body", weight=None):
    """Retrieve font tuple. Weight can be 'bold', 'medium', or 'normal'."""
    family = TOKENS.get("typography", "font_primary", default="Segoe UI")
    if type == "header" or type == "title":
        size = 18 if type == "title" else 14
        weight_val = "bold"
    elif type == "caption":
        size = 11
        weight_val = "normal"
    else:
        size = 13
        weight_val = "normal"
    
    # Caller override
    if weight == "bold":
        weight_val = "bold"
    
    return (family, size, weight_val)

def parse_border(token_key):
    """
    Parse a border token like '1px solid #RRGGBB'.
    Returns (width, color).
    """
    val = TOKENS.get("borders", token_key)
    if not val:
        return 0, None
    
    parts = val.split()
    try:
        width = int(parts[0].replace("px", ""))
        color = parts[2]
        if "rgba" in color:
             return width, "#3A4654" 
        return width, color
    except Exception:
        return 0, None

# --- Components ---

def make_panel(parent, title=None, fg_color=None, pad=None, corner_radius=None, **kw):
    """
    Create an elevated panel frame with optional title and divider.
    Supports collapsible behavior.
    """
    # Defaults
    def_bg = get_color("colors.background.panel")
    def_radius = get_radius("lg")
    def_border_w, def_border_c = parse_border("subtle")
    
    # Resolve values (kw > arg > default)
    bg_color = kw.pop("fg_color", fg_color or def_bg)
    radius = kw.pop("corner_radius", corner_radius or def_radius)
    border_w = kw.pop("border_width", def_border_w)
    border_c = kw.pop("border_color", def_border_c)
    
    p = pad if pad is not None else TOKENS.get("spacing", "md")
    
    # Pop special args
    collapsible = kw.pop("collapsible", False)
    start_collapsed = kw.pop("start_collapsed", False)

    # Outer frame (Structural)
    outer = ctk.CTkFrame(
        parent,
        fg_color=bg_color,
        corner_radius=radius,
        border_width=border_w,
        border_color=border_c,
        **kw
    )

    # Inner frame for padding/structure
    inner = ctk.CTkFrame(
        outer,
        fg_color=bg_color,
        corner_radius=radius - 1,
    )
    inner.pack(fill="both", expand=True, padx=1, pady=1)

    # Title bar
    if title:
        title_frame = ctk.CTkFrame(inner, fg_color="transparent")
        title_frame.pack(fill="x", padx=p, pady=(p, 0))

        ctk.CTkLabel(
            title_frame,
            text=title,
            font=get_font("title"),
            text_color=get_color("colors.text.primary")
        ).pack(side="left")

        # Gold underline
        underline = ctk.CTkFrame(
            inner, 
            height=1, 
            fg_color=get_color("colors.accent.gold", default="#C8A45D") 
        )
        underline.pack(fill="x", padx=p, pady=(8, 8))

    # Content Area
    content = ctk.CTkFrame(inner, fg_color="transparent")
    content.pack(fill="both", expand=True, padx=p, pady=(0 if title else p, p))

    # References for consumer access
    outer._content = content
    outer._inner = inner

    # Collapsible Logic
    if title and collapsible:
        btn_toggle = make_button(
            title_frame,
            text="▼" if not start_collapsed else "▶",
            style="ghost",
            width=30,
            height=24,
            font=get_font("body")
        )
        btn_toggle.pack(side="right")
        
        is_expanded = not start_collapsed 

        def toggle():
            nonlocal is_expanded
            if is_expanded:
                content.pack_forget()
                if "underline" in locals():
                    underline.pack_forget()
                btn_toggle.configure(text="▶")
                outer.configure(height=40) 
                is_expanded = False
            else:
                if "underline" in locals():
                    underline.pack(fill="x", padx=p, pady=(8, 8))
                content.pack(fill="both", expand=True, padx=p, pady=(0, p))
                btn_toggle.configure(text="▼")
                is_expanded = True
        
        btn_toggle.configure(command=toggle)

        if start_collapsed:
            content.pack_forget()
            if "underline" in locals():
                underline.pack_forget()
            outer.configure(height=40)

    return outer


def make_card(parent, fg_color=None, corner_radius=None, hover=True, **kw):
    """
    Create a card-level frame with raised surface.
    """
    def_bg = get_color("colors.background.card")
    def_radius = get_radius("md")
    def_border_w, def_border_c = parse_border("soft")
    
    bg_color = kw.pop("fg_color", fg_color or def_bg)
    radius = kw.pop("corner_radius", corner_radius or def_radius)
    border_w = kw.pop("border_width", def_border_w)
    border_c = kw.pop("border_color", def_border_c)
    
    card = ctk.CTkFrame(
        parent,
        fg_color=bg_color,
        corner_radius=radius,
        border_width=border_w,
        border_color=border_c,
        **kw
    )
    
    if hover:
        apply_hover_brightness(card, bg_color)

    return card




def make_button(parent, text, style="primary", width=None, command=None, icon=None, **kw):
    """
    Create a standardized button.
    Styles matches tokens: primary, secondary, danger, ghost.
    """
    # Map 'default' to 'secondary' if not found
    if style == "default": style = "secondary"
    if style == "success": style = "primary"

    style_def = TOKENS.get("buttons", style) or TOKENS.get("buttons", "secondary")
    
    # Base defaults
    def_fg = style_def.get("bg")
    def_text = style_def.get("text")
    def_hover = style_def.get("hover")
    
    # Border defaults
    def_bw, def_bc = parse_border("subtle")
    if style == "ghost":
        def_bw = 0
        def_bc = None
    if style == "danger":
        def_bc = get_color("colors.state.danger")

    # Double check for transparent color (crash prevention)
    if def_bc == "transparent":
        def_bc = None

    # KW overrides
    fg_color = kw.pop("fg_color", def_fg)
    text_color = kw.pop("text_color", def_text)
    hover_color = kw.pop("hover_color", def_hover)
    
    border_width = kw.pop("border_width", def_bw)
    border_color = kw.pop("border_color", def_bc)
    
    radius = kw.pop("corner_radius", get_radius("sm"))
    h = kw.pop("height", 32)
    w = kw.pop("width", width or 120)
    font = kw.pop("font", get_font("body", "medium"))

    btn = ctk.CTkButton(
        parent,
        text=text,
        font=font,
        width=w,
        height=h,
        corner_radius=radius,
        fg_color=fg_color,
        text_color=text_color,
        hover_color=hover_color,
        border_width=border_width,
        border_color=border_color,
        command=command,
        image=icon,
        **kw
    )
    
    apply_hover_brightness(btn, fg_color)
    apply_press_effect(btn, fg_color)

    return btn


def make_input(parent, placeholder="", width=None, **kw):
    """
    Create a standardized input field.
    """
    w = kw.pop("width", width or 200)
    font = kw.pop("font", get_font("body"))
    radius = kw.pop("corner_radius", get_radius("sm"))
    height = kw.pop("height", 32)
    
    bg_color = kw.pop("fg_color", get_color("colors.background.app"))
    def_border_w, def_border_c = parse_border("subtle")
    border_w = kw.pop("border_width", def_border_w)
    border_c = kw.pop("border_color", def_border_c)
    
    entry = ctk.CTkEntry(
        parent,
        width=w,
        height=height,
        corner_radius=radius,
        font=font,
        fg_color=bg_color, 
        border_color=border_c,
        border_width=border_w,
        placeholder_text=placeholder,
        placeholder_text_color=get_color("colors.text.muted"),
        text_color=get_color("colors.text.primary"),
        **kw
    )

    # Focus bindings
    def _on_focus(e):
        entry.configure(
            border_color=get_color("colors.accent.blue"), 
            fg_color=get_color("colors.background.card")
        )

    def _on_unfocus(e):
        entry.configure(
            border_color=border_c, 
            fg_color=bg_color
        )

    entry.bind("<FocusIn>", _on_focus, add="+")
    entry.bind("<FocusOut>", _on_unfocus, add="+")

    return entry





def make_switch(parent, text, command=None, variable=None, **kw):
    """
    Create a standardized switch.
    """
    switch = ctk.CTkSwitch(
        parent,
        text=text,
        font=get_font("body"),
        fg_color=get_color("colors.text.disabled"),
        progress_color=get_color("colors.accent.primary"),
        button_color=get_color("colors.text.primary"),
        button_hover_color=get_color("colors.text.secondary"),
        command=command,
        variable=variable,
        **kw
    )
    return switch



