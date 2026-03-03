import json
import os
import threading
import tkinter

import customtkinter as ctk
from PIL import Image

from ..ui_shared import (
    CTkTooltip, make_panel, make_button, make_input, 
    apply_hover_brightness, lighten_color, 
    get_color, get_font, parse_border, TOKENS
)
from utils.logger import Logger


# CONSTANTS
RUNE_PAGE_FILE = "rune_pages.json"


class RuneButton(ctk.CTkButton):
    def __init__(
        self,
        parent,
        rune_data,
        is_selected,
        on_click,
        icon=None,
        size=50,
        disabled=False,
        is_keystone=False,
        is_secondary_path=False,
    ):
        self.rune_data = rune_data
        self.is_selected = is_selected
        
        # Colors based on state and path
        accent_color = get_color("colors.state.danger") if is_secondary_path else get_color("colors.accent.gold")
        
        # Fallback visibility if no icon
        if icon is None:
            text = "?"
            fg_color = get_color("colors.background.panel") # Visible placeholder
        else:
             # Standard background for icons
            fg_color = get_color("colors.background.card")

        if disabled:
            fg_color = get_color("colors.background.app") # Darker background for disabled
            hover_color = get_color("colors.background.app")
            border_color = get_color("colors.background.app")
            border_width = 0
            # UX: Keep state normal so tooltips still work, but disable interaction via command=None
            state = "normal"
            # Greyscale/Dim effect would handle by image processing, 
            # but for now we rely on the button state.
        elif is_selected:
            fg_color = "transparent"  # Icon sits on background
            hover_color = get_color("colors.state.hover")
            border_color = accent_color
            border_width = 2
            state = "normal"
            # Add glow effect simulated by border
            if icon is None: fg_color = accent_color # distinct if no icon
        else:
            hover_color = get_color("colors.state.hover")
            _, border_color = parse_border("subtle")
            border_width = 1
            state = "normal"
            if icon is None: fg_color = get_color("colors.background.panel")

        # Keystone styling (Larger, more prominent)
        if is_keystone:
            size += 14  
            if is_selected:
                border_width = 3

        super().__init__(
            parent,
            text="",
            width=size,
            height=size,
            fg_color=fg_color,
            hover_color=hover_color,
            border_width=border_width,
            border_color=border_color,
            image=icon,
            command=on_click if not disabled else None,
            corner_radius=size // 2,
            state=state,
        )

        # Force enable if selected (even if conceptually disabled in other contexts)
        if disabled and is_selected:
             self.configure(state="normal", border_color=accent_color)
        elif disabled:
            try:
                self.configure(cursor="arrow")
            except Exception:
                pass
    
    def update_icon_from_assets(self, asset_manager):
        """Try to load icon from assets and update button."""
        icon_path = self.rune_data.get("icon")
        if not icon_path:
            return False
            
        icon = asset_manager.get_rune_icon(icon_path, size=(self.cget("width"), self.cget("height")))
        if icon:
            self.configure(image=icon)
            # Reset colors if needed (remove placeholder)
            if self.is_selected:
                self.configure(fg_color="transparent")
            else:
                self.configure(fg_color="transparent")
            return True
        return False
    
    def destroy(self):
        try:
            super().destroy()
        except Exception:
            pass


class ShardButton(RuneButton):
    def update_icon_from_assets(self, asset_manager):
        """Override to use get_rune_shard_icon."""
        name = self.rune_data.get("name")
        if not name:
            return False
            
        icon = asset_manager.get_rune_shard_icon(name, size=(self.cget("width"), self.cget("height")))
        if icon:
            self.configure(image=icon)
            if self.is_selected:
                self.configure(fg_color="transparent")
            else:
                self.configure(fg_color="transparent")
            return True
        return False


class RunePathCanvas(ctk.CTkCanvas):
    """Canvas for drawing vertical path lines between runes."""
    def __init__(self, parent, width, height, is_secondary=False):
        super().__init__(
            parent, 
            width=width, 
            height=height, 
            bg=get_color("colors.background.app"), 
            highlightthickness=0
        )
        self.is_secondary = is_secondary
        self.line_color = get_color("colors.state.danger") if is_secondary else get_color("colors.accent.gold")
        
    def clear(self):
        self.delete("all")
        
    def draw_path(self, start_coords, end_coords, active=False):
        """Draw a vertical line segment."""
        # Dimmed if inactive, but we mostly draw active paths
        fill = self.line_color if active else get_color("colors.text.muted")
        width = 2 if active else 1
        
        self.create_line(
            start_coords[0], start_coords[1],
            end_coords[0], end_coords[1],
            fill=fill,
            width=width
        )

class PageManager:
    """Handles local storage of rune pages."""

    def __init__(self):
        self.pages = []
        self._page_map = {}
        self.load()

    def load(self):
        if os.path.exists(RUNE_PAGE_FILE):
            try:
                with open(RUNE_PAGE_FILE, "r") as f:
                    self.pages = json.load(f)
            except Exception:
                self.pages = []
        else:
            self.pages = []

        self._page_map = {p["name"]: p for p in self.pages}

    def save(self):
        with open(RUNE_PAGE_FILE, "w") as f:
            json.dump(self.pages, f, indent=4)

    def save_page(self, page_data):
        name = page_data["name"]
        existing = self._page_map.get(name)

        if existing:
            if existing in self.pages:
                self.pages.remove(existing)

        self.pages.append(page_data)
        self._page_map[name] = page_data
        self.save()

    def delete_page(self, name):
        self.pages = [p for p in self.pages if p["name"] != name]
        if name in self._page_map:
            del self._page_map[name]
        self.save()

    def get_pages(self):
        return self.pages

    def get_page_by_name(self, name):
        return self._page_map.get(name)


class RunePageBuilder(ctk.CTkFrame):
    def __init__(self, parent, asset_manager, lcu):
        super().__init__(parent, fg_color=get_color("colors.background.panel"), corner_radius=0)
        self.assets = asset_manager
        self.lcu = lcu
        self.page_manager = PageManager()

        # State
        self.rune_data = []
        self.selected_primary_style = 8000  # Precision
        self.selected_sub_style = 8100  # Domination

        self.current_selections = {
            "primary": {},
            "secondary": {},
            "shards": {0: 5008, 1: 5008, 2: 5002},
        }

        self.page_name_var = ctk.StringVar(value="New Page")
        self.selected_page_var = ctk.StringVar(value="-- New Page --")

        self.tooltip_label = None
        self.delete_confirm_active = False  # State for delete button

        self._init_layout()
        self.after(100, self._load_data)
        
        self.pending_updates = []
        self._update_job = None
        self.bind("<Destroy>", self._on_destroy)

    def _on_destroy(self, event):
        if self._update_job:
            self.after_cancel(self._update_job)
            self._update_job = None
        self._force_hide_tooltip()

    def _init_layout(self):
        # Configure Main Grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)  # Editor expands

        # --- ROW 0: NEW HEADER BAR (Compact) ---
        self.toolbar_frame = ctk.CTkFrame(
            self, fg_color="transparent", height=46, corner_radius=0
        )
        self.toolbar_frame.grid(row=0, column=0, sticky="ew", padx=TOKENS.get("spacing.md"), pady=(TOKENS.get("spacing.xs"), TOKENS.get("spacing.xs")))
        
        # Left: Title + Edit Controls
        title_box = ctk.CTkFrame(self.toolbar_frame, fg_color="transparent")
        title_box.pack(side="left")
        
        # Page Name Entry
        self.name_entry = make_input(
            title_box,
            textvariable=self.page_name_var,
            width=200,
            font=get_font("title"),
        )
        self.name_entry.pack(side="left", padx=(0, TOKENS.get("spacing.sm")))
        
        # Dropdown (Styled as Title)
        self.page_dropdown = ctk.CTkComboBox(
            title_box,
            values=["New Page"],
            variable=self.selected_page_var,
            width=200,
            font=get_font("title"),
            text_color=get_color("colors.text.primary"),
            fg_color=get_color("colors.background.card"),
            border_width=1,
            border_color=parse_border("subtle")[1],
            corner_radius=TOKENS.get("radius.sm"),
            button_color=get_color("colors.background.panel"),
            command=self._on_page_selected,
            state="readonly",
        )
        self.page_dropdown.pack(side="left")

        # Right: Actions (SAVE is Dominant)
        action_box = ctk.CTkFrame(self.toolbar_frame, fg_color="transparent")
        action_box.pack(side="right")
        
        # SAVE (Gold Border, Dominant)
        self.btn_save = make_button(
            action_box,
            text="SAVE",
            style="primary", # Use primary (green usually) or manual gold?
            width=100,
            command=self.save_local,
            border_color=get_color("colors.accent.gold"),
            border_width=2,
            text_color=get_color("colors.accent.gold"),
            fg_color="transparent", # Outline style
            hover_color=TOKENS.get("colors.state.hover"),
            font=("Roboto", 14, "bold"),
        )
        self.btn_save.pack(side="left", padx=TOKENS.get("spacing.sm"))

        # Equip (Upload to Client)
        self.btn_equip = make_button(
            action_box,
            text="EQUIP",
            style="secondary", 
            width=80,
            command=self.equip_to_client,
            state="disabled"
        )
        self.btn_equip.pack(side="left", padx=TOKENS.get("spacing.xs"))
        self.equip_tooltip = CTkTooltip(self.btn_equip, "Select all runes to enable")
        
        # Add (+)
        make_button(
            action_box, text="+", 
            width=32, 
            height=32,
            corner_radius=16, 
            font=("Arial", 20),
            style="secondary",
            command=self.create_page
        ).pack(side="left", padx=TOKENS.get("spacing.xs"))
        
        # Delete (Trash)
        self.btn_delete = make_button(
            action_box, text="🗑", 
            width=32,
            height=32,
            style="ghost",
            hover_color=get_color("colors.state.danger"),
            corner_radius=16, 
            font=("Segoe UI Emoji", 18),
            command=self._on_click_delete
        )
        self.btn_delete.pack(side="left", padx=TOKENS.get("spacing.xs"))

        # --- ROW 1: MAIN EDITOR (Two Columns) ---
        self.editor_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.editor_frame.grid(row=1, column=0, sticky="nsew", padx=TOKENS.get("spacing.lg"), pady=TOKENS.get("spacing.md"))

        # Split: Primary (Left) | Secondary & Shards (Right)
        self.editor_frame.grid_columnconfigure(0, weight=1)  # Primary
        self.editor_frame.grid_columnconfigure(1, weight=1)  # Secondary
        self.editor_frame.grid_rowconfigure(0, weight=1)
        
        # Separator Line
        sep = ctk.CTkFrame(self.editor_frame, width=1, fg_color=parse_border("subtle")[1])
        sep.grid(row=0, column=0, sticky="e", padx=(0, TOKENS.get("spacing.md")), pady=TOKENS.get("spacing.lg"))

        # PRIMARY PANEL CONTAINER (Left Column)
        self.left_panel = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, TOKENS.get("spacing.lg")))

        # Primary Tree (Top of Left)
        self.p_panel = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.p_panel.pack(side="top", fill="both", expand=True)

        # SHARDS (Bottom of Left)
        self.shards_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.shards_frame.pack(side="bottom", fill="x", pady=(TOKENS.get("spacing.lg"), 0))

        # SECONDARY PANEL CONTAINER (Right Column)
        self.right_panel = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(TOKENS.get("spacing.lg"), 0))
        
        # Secondary Tree (Fills Right)
        self.s_panel = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        self.s_panel.pack(side="top", fill="both", expand=True)

        # Status Bar
        self.status_bar = ctk.CTkLabel(
            self, text="", font=get_font("caption"), text_color=get_color("colors.text.muted")
        )
        self.status_bar.grid(row=2, column=0, pady=(0, 10))

    def _reset_current_page(self):
        # Reset to defaults for current style
        self.current_selections = {
            "primary": {},
            "secondary": {},
            "shards": {0: 5008, 1: 5008, 2: 5002},
        }
        self._render_editor()
        self._set_status("Selections cleared")

    def _on_click_delete(self):
        if not self.delete_confirm_active:
            self.delete_confirm_active = True
            self.btn_delete.configure(text="CONFIRM?")
            self.after(3000, self._reset_delete_btn)
        else:
            self._delete_page()
            self._reset_delete_btn()

    def _reset_delete_btn(self):
        self.delete_confirm_active = False
        if self.winfo_exists():
            self.btn_delete.configure(text="DELETE")

    def _check_completeness(self):
        # Logic to enable/disable Equip button
        p_count = len(self.current_selections["primary"])
        s_count = len(self.current_selections["secondary"])
        sh_count = len(self.current_selections["shards"])

        is_complete = (p_count == 4) and (s_count == 2) and (sh_count == 3)

        if is_complete:
            self.btn_equip.configure(state="normal", fg_color=get_color("colors.state.success"))
            if hasattr(self, "equip_tooltip"):
                self.equip_tooltip.text = "Upload this page to the League Client"
        else:
            self.btn_equip.configure(state="disabled", fg_color=get_color("colors.text.disabled"))
            if hasattr(self, "equip_tooltip"):
                self.equip_tooltip.text = "Select all runes and shards to enable"

    def _set_status(self, msg, is_error=False):
        self.status_bar.configure(
            text=msg, text_color=get_color("colors.state.danger") if is_error else get_color("colors.accent.primary")
        )
        self.after(4000, lambda: self.status_bar.configure(text=""))

    def _load_data(self):
        self.rune_data = self.assets.get_runes_data()
        self._refresh_page_dropdown()
        self._render_editor()

    def _refresh_page_dropdown(self):
        pages = self.page_manager.get_pages()
        names = ["-- New Page --"] + [p["name"] for p in pages]
        self.page_dropdown.configure(values=names)

    def _on_page_selected(self, choice):
        if choice == "-- New Page --":
            self.page_name_var.set("New Page")
            self._reset_current_page()
            return

        page = self.page_manager.get_page_by_name(choice)
        if not page:
            return

        self.page_name_var.set(page["name"])
        self.selected_primary_style = page.get("primaryStyleId", 8000)
        self.selected_sub_style = page.get("subStyleId", 8100)

        # Load Perks
        self.current_selections = {"primary": {}, "secondary": {}, "shards": {}}
        perks = page.get("selectedPerkIds", [])

        if self.rune_data:
            # Map Primary
            p_tree = next(
                (t for t in self.rune_data if t["id"] == self.selected_primary_style),
                None,
            )
            if p_tree:
                for slot_idx, slot in enumerate(p_tree["slots"]):
                    slot_ids = [r["id"] for r in slot["runes"]]
                    for perk in perks:
                        if perk in slot_ids:
                            self.current_selections["primary"][slot_idx] = perk
                            break

            # Map Secondary
            s_tree = next(
                (t for t in self.rune_data if t["id"] == self.selected_sub_style), None
            )
            if s_tree:
                for slot_idx, slot in enumerate(s_tree["slots"]):
                    if slot_idx == 0:
                        continue  # Skip Keystone
                    slot_ids = [r["id"] for r in slot["runes"]]
                    for perk in perks:
                        if perk in slot_ids:
                            self.current_selections["secondary"][slot_idx] = perk
                            break

            # Shards
            shard_ids = [5001, 5002, 5003, 5005, 5007, 5008, 5010, 5011, 5013]
            shard_perks = [p for p in perks if p in shard_ids]

            rows_defs = [[5008, 5005, 5007], [5008, 5010, 5001], [5011, 5002, 5003]]

            temp_perks = list(shard_perks)
            for r_idx, r_opts in enumerate(rows_defs):
                for p in temp_perks:
                    if p in r_opts:
                        self.current_selections["shards"][r_idx] = p
                        temp_perks.remove(p)
                        break

        self._render_editor()
        self._set_status(f"Loaded {page['name']}")

    def _render_editor(self):
        # Clean panels
        for w in self.tree_selector_frame.winfo_children():
            w.destroy()
        for w in self.p_panel.winfo_children():
            w.destroy()
        for w in self.s_panel.winfo_children():
            w.destroy()
        for w in self.shards_frame.winfo_children():
            w.destroy()

        self._force_hide_tooltip()
        self._check_completeness()

        # --- ROW 1: SHARED TREE SELECTOR ---
        self._render_tree_selector()

        # --- PRIMARY PANEL ---
        self._render_tree_title(self.p_panel, self.selected_primary_style, is_primary=True)
        self._render_primary_slots()

        # --- SECONDARY PANEL ---
        self._render_tree_title(self.s_panel, self.selected_sub_style, is_primary=False)
        self._render_secondary_slots()

        # --- SHARDS ---
        self._render_shards()

    def _render_tree_selector(self):
        """Render shared tree selector row with all 5 tree icons."""
        center_box = ctk.CTkFrame(self.tree_selector_frame, fg_color="transparent")
        center_box.pack(anchor="center")

        for tree in self.rune_data:
            tid = tree["id"]
            is_primary_selected = tid == self.selected_primary_style
            is_secondary_selected = tid == self.selected_sub_style

            icon = self.assets.get_rune_icon(tree["icon"], size=(36, 36))

            # Style: primary = solid fill, secondary = ring border
            if is_primary_selected:
                fg = get_color("colors.accent.primary")
                border_w = 0
            elif is_secondary_selected:
                fg = "transparent"
                border_w = 3
            else:
                fg = "transparent"
                border_w = 0

            btn = make_button(
                center_box,
                text="",
                icon=icon,
                width=44,
                height=44,
                fg_color=fg,
                hover_color=get_color("colors.state.hover"),
                border_width=border_w,
                border_color=get_color("colors.accent.gold") if is_secondary_selected else parse_border("subtle")[1],
                corner_radius=22,
                command=lambda t=tid: self._on_tree_click(t),
            )
            btn.pack(side="left", padx=TOKENS.get("spacing.sm"))

    def _on_tree_click(self, tid):
        """Handle tree icon click - primary if not already primary, else secondary."""
        if tid == self.selected_primary_style:
            return  # Can't deselect primary
        elif tid == self.selected_sub_style:
            return  # Already secondary, no change
        else:
            # Set as secondary (user can click another to make it primary)
            self.selected_sub_style = tid
            self.current_selections["secondary"] = {}
        self._render_editor()

    def _safe_destroy(self, parent):
        for w in parent.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass

    def _render_editor(self):
        # Clean
        self._safe_destroy(self.p_panel)
        self._safe_destroy(self.s_panel)
        self._safe_destroy(self.shards_frame)

        self._force_hide_tooltip()
        self._check_completeness()
        
        self.pending_updates.clear() # Reset tracking

        # --- LEFT (PRIMARY) ---
        self._render_primary_tree_header(self.p_panel)
        self._render_divider(self.p_panel)
        self._render_primary_slots()

        # --- RIGHT (SECONDARY) ---
        try:
            self._render_secondary_tree_header(self.s_panel)
            self._render_divider(self.s_panel)
            self._render_secondary_slots()
        except Exception as e:
            Logger.error("Runes", f"Error rendering secondary: {e}")
            self._set_status(f"Error sec: {e}", True)

        # --- BOTTOM RIGHT (SHARDS) ---
        try:
            self._render_divider(self.shards_frame)
            self._render_shards()
        except Exception as e:
            Logger.error("Runes", f"Error rendering shards: {e}")
            self._set_status(f"Error shards: {e}", True)

        # Start update loop if needed
        if self.pending_updates:
            if self._update_job:
                self.after_cancel(self._update_job)
            self._update_job = self.after(1000, self._update_missing_assets)

    def _update_missing_assets(self):
        """Poll for missing assets and update widgets without re-rendering."""
        if not self.pending_updates:
            return

        still_pending = []
        for item in self.pending_updates:
            # check type
            if isinstance(item, RuneButton):
                if not item.update_icon_from_assets(self.assets):
                    still_pending.append(item)
            else:
                # Header tuple: (btn, icon_path, size)
                btn, path, size = item
                img = self.assets.get_rune_icon(path, size=size)
                if img:
                    try:
                        btn.configure(image=img)
                    except Exception:
                        pass # widget destroyed
                else:
                    still_pending.append(item)
        
        self.pending_updates = still_pending
        if self.pending_updates:
             self._update_job = self.after(1000, self._update_missing_assets)

    def _render_divider(self, parent):
        ctk.CTkFrame(parent, height=1, fg_color=parse_border("subtle")[1]).pack(fill="x", padx=TOKENS.get("spacing.md"), pady=TOKENS.get("spacing.xs"))

    def _render_primary_tree_header(self, parent):
        # ... existing ...
        """Render the 5 tree icons for Primary selection."""
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", pady=(0, TOKENS.get("spacing.lg")), padx=TOKENS.get("spacing.sm"))

        # Center Container
        center_box = ctk.CTkFrame(header, fg_color="transparent")
        center_box.pack(anchor="center")

        for tree in self.rune_data:
            tid = tree["id"]
            active = tid == self.selected_primary_style
            
            # Gold Ring for active
            border_width = 2 if active else 0
            
            # Icon (Compact)
            icon = self.assets.get_rune_icon(tree["icon"], size=(28, 28))
            
            # Wrapper for layout
            
            # Wrapper for layout
            wrapper = ctk.CTkFrame(center_box, fg_color="transparent")
            wrapper.pack(side="left", padx=TOKENS.get("spacing.xs"))

            btn = make_button(
                wrapper,
                text="",
                icon=icon,
                width=36, 
                height=36,
                fg_color="transparent",
                hover_color=TOKENS.get("colors.state.hover"),
                border_width=border_width,
                corner_radius=18,
                command=lambda t=tid: self.set_style(t, True)
            )
            if active:
                btn.configure(border_color=get_color("colors.accent.gold"))
            
            btn.pack()
            
            if icon is None:
                self.pending_updates.append((btn, tree["icon"], (28, 28)))
            
            # Title Label under icon
            ctk.CTkLabel(
                wrapper,
                text=tree["name"].upper(),
                font=get_font("caption"),
                text_color=get_color("colors.accent.gold") if active else get_color("colors.text.muted")
            ).pack(pady=(TOKENS.get("spacing.xs"), 0))

    def _render_secondary_tree_header(self, parent):
        """Render the tree icons for Secondary selection."""
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", pady=(0, TOKENS.get("spacing.lg")), padx=TOKENS.get("spacing.sm"))

        center_box = ctk.CTkFrame(header, fg_color="transparent")
        center_box.pack(anchor="center")

        for tree in self.rune_data:
            tid = tree["id"]
            if tid == self.selected_primary_style:
                continue # Don't show primary tree in secondary list

            active = tid == self.selected_sub_style
            
            # Red Ring for active secondary  
            border_width = 2 if active else 0
            
            icon = self.assets.get_rune_icon(tree["icon"], size=(20, 20)) 
            
            btn_args = {
                "text": "",
                "icon": icon,
                "width": 25,
                "height": 25,
                "fg_color": "transparent",
                "hover_color": TOKENS.get("colors.state.hover"),
                "border_width": border_width,
                "corner_radius": 13,
                "command": lambda t=tid: self._on_tree_click(t)
            }
            if active:
                btn_args["border_color"] = get_color("colors.state.danger")
            
            btn = make_button(center_box, **btn_args)
            
            if icon is None:
                self.pending_updates.append((btn, tree["icon"], (20, 20)))
            btn.pack(side="left", padx=TOKENS.get("spacing.xs"))

    def _render_tree_title(self, parent, style_id, is_primary):
        """Render just the tree name header (no selector buttons)."""
        tree_obj = next((t for t in self.rune_data if t["id"] == style_id), None)
        if tree_obj:
            # Tree name with color coding
            color = get_color("colors.accent.primary") if is_primary else get_color("colors.state.danger")
            t_lbl = ctk.CTkLabel(
                parent,
                text=tree_obj["name"].upper(),
                font=get_font("title"),
                text_color=color,
            )
            t_lbl.pack(pady=(15, 5))

            # Horizontal divider
            ctk.CTkFrame(
                parent,
                height=2,
                fg_color=color,
                width=150,
            ).pack(pady=(0, 10))

    def _render_tree_header(self, parent, selected_id, is_primary):
        # Tree Selection Icons
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", pady=15, padx=20)

        center_box = ctk.CTkFrame(header, fg_color="transparent")
        center_box.pack(anchor="center")

        for tree in self.rune_data:
            tid = tree["id"]
            # If primary, exclude nothing. If secondary, exclude primary choice.
            if not is_primary and tid == self.selected_primary_style:
                continue

            active = tid == selected_id
            icon = self.assets.get_rune_icon(tree["icon"], size=(40, 40))

            btn = make_button(
                center_box,
                text="",
                icon=icon,
                width=48,
                height=48,
                fg_color=get_color("colors.accent.primary") if active else "transparent",
                hover_color=get_color("colors.state.hover"),
                border_width=2 if active else 0,
                border_color=get_color("colors.accent.gold"),
                command=lambda t=tid: self.set_style(t, is_primary),
            )
            btn.pack(side="left", padx=TOKENS.get("spacing.xs"))

        # Title
        tree_obj = next((t for t in self.rune_data if t["id"] == selected_id), None)
        if tree_obj:
            t_lbl = ctk.CTkLabel(
                parent,
                text=tree_obj["name"].upper(),
                font=get_font("title"),
                text_color=get_color("colors.text.primary") if is_primary else get_color("colors.text.secondary"),
            )
            t_lbl.pack(pady=(5, 10))

            # Divider
            ctk.CTkFrame(
                parent,
                height=2,
                fg_color=get_color("colors.accent.primary") if is_primary else get_color("colors.text.secondary"),
                width=100,
            ).pack(pady=(0, 15))

    def set_style(self, tid, is_primary):
        if is_primary:
            self.selected_primary_style = tid
            # Reset secondary if conflict
            if self.selected_sub_style == tid:
                for t in self.rune_data:
                    if t["id"] != tid:
                        self.selected_sub_style = t["id"]
                        break
            self.current_selections["primary"] = {}
        else:
            self.selected_sub_style = tid
            self.current_selections["secondary"] = {}

        self._render_editor()

    def _render_primary_slots(self):
        """Render primary tree rune slots using simple frame layout."""
        tree = next(
            (t for t in self.rune_data if t["id"] == self.selected_primary_style), None
        )
        if not tree:
            return

        # Container for all rows
        container = ctk.CTkFrame(self.p_panel, fg_color="transparent")
        container.pack(expand=True, fill="both", padx=10, pady=10)

        slots = tree.get("slots", [])


        for i, slot in enumerate(slots):
            runes = slot.get("runes", [])
            is_keystone = (i == 0)
            
            # Connector Line (except first)
            if i > 0:
                ctk.CTkFrame(
                    container, 
                    width=2, 
                    height=12, 
                    fg_color=parse_border("subtle")[1]
                ).pack(pady=0)

            # Create row frame (Compact)
            row = ctk.CTkFrame(container, fg_color="transparent")
            row.pack(pady=4, anchor="center") # Reduced padding significantly
            
            active_id = self.current_selections["primary"].get(i)
            
            for rune in runes:
                rid = rune["id"]
                selected = (rid == active_id)
                
                # Get icon (Compact: Keystone same, others smaller)
                icon = self.assets.get_rune_icon(rune.get("icon", ""), size=(34, 34) if is_keystone else (22, 22))
                
                # Button size
                size = 42 if is_keystone else 28
                
                # Create button
                btn = RuneButton(
                    row,
                    rune_data=rune,
                    is_selected=selected,
                    on_click=lambda r=rid, s=i: self.select_rune(r, "primary", s),
                    icon=icon,
                    size=size,
                    is_keystone=is_keystone
                )
                btn.pack(side="left", padx=4 if is_keystone else 2)
                
                if icon is None:
                    self.pending_updates.append(btn)
                
                # Tooltip
                btn.bind("<Enter>", lambda e, r=rune: self.show_tooltip(e, r["name"], r["shortDesc"]))
                btn.bind("<Leave>", self.hide_tooltip)


    def _render_secondary_slots(self):
        """Render secondary tree rune slots (no keystones)."""
        tree = next(
            (t for t in self.rune_data if t["id"] == self.selected_sub_style), None
        )
        if not tree:
            return

        container = ctk.CTkFrame(self.s_panel, fg_color="transparent")
        container.pack(expand=True, fill="both", padx=10, pady=10)

        selected_rows = list(self.current_selections["secondary"].keys())
        slots = tree.get("slots", [])

        for i, slot in enumerate(slots):
            if i == 0:
                continue  # Skip Keystone for secondary

            runes = slot.get("runes", [])
            
            # Connector Line
            ctk.CTkFrame(
                container, 
                width=2, 
                height=10, 
                fg_color=parse_border("subtle")[1]
            ).pack(pady=0)

            row = ctk.CTkFrame(container, fg_color="transparent")
            row.pack(pady=2, anchor="center") # Compact

            # Logic: Can select if row already selected OR we haven't picked 2 yet
            row_has_pick = i in selected_rows
            can_pick = row_has_pick or (len(selected_rows) < 2)
            
            active_id = self.current_selections["secondary"].get(i)

            for rune in runes:
                rid = rune["id"]
                selected = (rid == active_id)
                
                icon = self.assets.get_rune_icon(rune.get("icon", ""), size=(22, 22))
                
                btn = RuneButton(
                    row,
                    rune_data=rune,
                    is_selected=selected,
                    on_click=lambda r=rid, s=i: self.select_rune(r, "secondary", s),
                    icon=icon,
                    size=27,
                    is_secondary_path=True,
                    disabled=not can_pick
                )
                btn.pack(side="left", padx=2)

                if icon is None:
                    self.pending_updates.append(btn)

                # Tooltip
                btn.bind("<Enter>", lambda e, r=rune: self.show_tooltip(e, r["name"], r["shortDesc"]))
                btn.bind("<Leave>", self.hide_tooltip)


    def _render_shards(self):
        """Render Shards (3x3 Grid) - Bottom Right"""
        container = ctk.CTkFrame(self.shards_frame, fg_color="transparent")
        container.pack(expand=True, anchor="center")

        # 3 Rows: Offense, Flex, Defense
        shard_rows = [
            [5008, 5005, 5007],  # Adaptive, AS, Haste
            [5008, 5010, 5001],  # Adaptive, Move, HP
            [5011, 5002, 5003],  # HP, Armor, MR
        ]
        
        # Colors map
        shard_colors = {
            5008: "#9333ea", # Purple (Adaptive)
            5005: "#eab308", # Yellow (AS)
            5007: "#eab308", # Yellow (Haste)
            5010: "#3b82f6", # Blue (Move speed)
            5001: "#22c55e", # Green (HP)
            5011: "#22c55e", # Green (HP)
            5002: "#22c55e", # Green (Armor)
            5003: "#3b82f6", # Blue (MR)
        }

        grid_f = ctk.CTkFrame(container, fg_color="transparent")
        grid_f.pack()

        for i, row_ids in enumerate(shard_rows):
            # Row Label
            lbls = ["OFF", "FLX", "DEF"]
            ctk.CTkLabel(
                grid_f, 
                text=lbls[i], 
                font=get_font("caption"), 
                text_color=get_color("colors.text.muted"),
                width=40,
                anchor="e"
            ).grid(row=i, column=0, padx=5)

            for j, sid in enumerate(row_ids):
                # Is selected?
                selected = self.current_selections["shards"].get(i) == sid
                
                # Visuals
                color = shard_colors.get(sid, "#9ca3af")
                
                # Create Button
                btn = ctk.CTkButton(
                    grid_f,
                    text="",
                    width=17,
                    height=17,
                    corner_radius=9,
                    fg_color=color if selected else get_color("colors.background.panel"),
                    hover_color=color,
                    border_width=2 if selected else 1,
                    border_color=get_color("colors.text.primary") if selected else parse_border("subtle")[1],
                    command=lambda s=sid, r=i: self.select_shard(s, r) # FIX: sid first, then row index
                )
                btn.grid(row=i, column=j+1, padx=2, pady=2)
                
                # Tooltip
                name = self._get_shard_name(sid)
                btn.bind("<Enter>", lambda e, n=name: self.show_tooltip(e, n, "Stat Shard"))
                btn.bind("<Leave>", self.hide_tooltip)
                
    def _get_shard_name(self, shard_id):
        # Helper to map shard ID to name for icon (if we used icons)
        map_names = {
            5008: "AdaptiveForce",
            5005: "AttackSpeed",
            5007: "AbilityHaste", # CoolDownReduction
            5010: "MovementSpeed",
            5001: "HealthScaling",
            5002: "Armor",
            5003: "MagicResist",
            5011: "Health",
        }
        return map_names.get(shard_id, "AdaptiveForce")
        
    def _render_stats_preview(self):
        """Stats preview removed in new layout - no-op."""
        pass

    def _add_stat_section(self, parent, title, selections, style_id):
        pass
        # Get Style Name
        style_name = ""
        for t in self.rune_data:
            if t["id"] == style_id:
                style_name = t["name"]

        ctk.CTkLabel(
            parent,
            text=f"{title} ({style_name})",
            font=("Roboto", 10, "bold"),
            text_color=get_color("colors.text.muted"),
            anchor="w",
        ).pack(fill="x", pady=(10, 2))

        # Get rune names
        # Selections is dict {slot: id}
        # We need to look up ID -> Name

        # Flatten rune_data to ID map?
        # Or inefficient search

        # Pre-calculate rune name map for efficiency (O(1) lookup vs O(N^3))
        rune_map = {
            r["id"]: r["name"]
            for t in self.rune_data
            for s in t["slots"]
            for r in s["runes"]
        }

        for slot_idx in sorted(selections.keys()):
            rid = selections[slot_idx]
            name = rune_map.get(rid, "?")
            ctk.CTkLabel(
                parent,
                text=f"• {name}",
                font=get_font("body"),
                text_color="#ffffff",
                anchor="w",
            ).pack(fill="x", pady=1)

    def _create_rune_btn(self, parent, rune, mode, slot_idx, size=50, disabled=False):
        rid = rune["id"]
        is_sel = False
        if mode == "primary":
            is_sel = self.current_selections["primary"].get(slot_idx) == rid
        else:
            is_sel = self.current_selections["secondary"].get(slot_idx) == rid

        icon = self.assets.get_rune_icon(rune["icon"], size=(size - 8, size - 8))

        btn = RuneButton(
            parent,
            rune,
            is_sel,
            lambda: self.select_rune(rid, mode, slot_idx),
            icon=icon,
            size=size,
            disabled=disabled and not is_sel,
        )

        btn.pack(side="left", padx=6)

        def _get_tooltip_title():
            title = rune["name"]
            if disabled and not is_sel:
                title += " (Disabled)"
            return title

        btn.bind(
            "<Enter>", lambda e: self.show_tooltip(e, _get_tooltip_title(), rune["shortDesc"])
        )
        btn.bind("<Leave>", self.hide_tooltip)

    def _create_shard_btn(self, parent, shard_id, row_idx):
        is_sel = self.current_selections["shards"].get(row_idx) == shard_id

        labels = {
            5008: "Adaptive",
            5005: "Atk Spd",
            5007: "Haste",
            5010: "Move Spd",
            5001: "Scaling HP",
            5011: "65 HP",
            5013: "Tenacity",
        }

        txt = labels.get(shard_id, "?")

        btn = ctk.CTkButton(
            parent,
            text=f"✓ {txt}" if is_sel else txt,
            width=90,
            height=32,
            font=get_font("body"),
            fg_color=get_color("colors.accent.primary") if is_sel else get_color("colors.background.panel"),
            hover_color=get_color("colors.state.hover"),
            corner_radius=16,
            border_width=1 if not is_sel else 0,
            border_color=parse_border("subtle")[1],
            command=lambda: self.select_shard(shard_id, row_idx),
        )
        btn.pack(side="left", padx=5)

    def _render_shards(self):
        """Render the 3 rows of stat shards."""
        container = ctk.CTkFrame(self.shards_frame, fg_color="transparent")
        container.pack(pady=5)

        # Offense, Flex, Defense
        rows_defs = [
            [5008, 5005, 5007], # Adaptive, AS, Haste
            [5008, 5010, 5001], # Adaptive, MoveSpeed, Health Scaling
            [5011, 5013, 5001]  # Health Flat, Tenacity, Health Scaling
        ]
        
        # Name mapping for AssetManager
        # AssetManager uses these names to find files like "statmods{name}icon.png"
        id_to_name = {
            5008: "AdaptiveForce",
            5005: "AttackSpeed", 
            5007: "AbilityHaste", # CooldownReduction
            5010: "MovementSpeed",
            5001: "HealthScaling",
            5011: "HealthPlus", # Flat Health
            5013: "Tenacity",
        }
        
        # Tooltip Descriptions
        id_to_desc = {
            5008: "Grants Adaptive Force",
            5005: "Grants Attack Speed",
            5007: "Grants Ability Haste",
            5010: "Grants 2% Move Speed",
            5001: "Grants Health (Scaling)",
            5011: "Grants 65 Health",
            5013: "Grants 10% Tenacity & Slow Resist",
        }

        for r_idx, options in enumerate(rows_defs):
            row_frame = ctk.CTkFrame(container, fg_color="transparent")
            row_frame.pack(pady=2)

            for sid in options:
                active = self.current_selections["shards"].get(r_idx) == sid
                
                name = id_to_name.get(sid, "Adaptive Force")
                icon = self.assets.get_rune_shard_icon(name, size=(24, 24))
                
                # Construct data for ShardButton
                rune_data = {
                    "id": sid,
                    "name": name,
                    "icon": name, # ShardButton uses this name to look up
                    "shortDesc": id_to_desc.get(sid, name)
                }
                
                btn = ShardButton(
                    row_frame,
                    rune_data=rune_data,
                    is_selected=active,
                    on_click=lambda s=sid, r=r_idx: self.select_shard(s, r),
                    icon=icon,
                    size=30,
                    is_keystone=False
                )
                btn.pack(side="left", padx=4)
                
                if icon is None:
                     # Fix: Use object-based update so it calls ShardButton.update_icon_from_assets
                     self.pending_updates.append(btn)
                     
                # Tooltip
                btn.bind("<Enter>", lambda e, r=rune_data: self.show_tooltip(e, r["name"], r["shortDesc"]))
                btn.bind("<Leave>", self.hide_tooltip)

    def select_rune(self, rid, mode, slot_idx):
        if mode == "primary":
            self.current_selections["primary"][slot_idx] = rid
        else:
            current = self.current_selections["secondary"].get(slot_idx)
            if current == rid:
                del self.current_selections["secondary"][slot_idx]
            else:
                if len(self.current_selections["secondary"]) < 2 or current:
                    self.current_selections["secondary"][slot_idx] = rid
                else:
                    return

        self._render_editor()

    def select_shard(self, sid, row_idx):
        self.current_selections["shards"][row_idx] = sid
        self._render_editor()

    def create_page(self):
        self.page_name_var.set("New Page")
        self.selected_page_var.set("-- New Page --")
        self._reset_current_page()

    def save_local(self):
        perks = self._build_perk_list()
        page = {
            "name": self.page_name_var.get(),
            "primaryStyleId": self.selected_primary_style,
            "subStyleId": self.selected_sub_style,
            "selectedPerkIds": perks,
            "current": True,
        }
        self.page_manager.save_page(page)
        self._refresh_page_dropdown()
        self.selected_page_var.set(page["name"])
        self._set_status(f"Saved: {page['name']}")

    def equip_to_client(self):
        if not self.lcu or not self.lcu.is_connected:
            self._set_status("Client Disconnected", True)
            return

        perks = self._build_perk_list()
        page_data = {
            "name": self.page_name_var.get(),
            "primaryStyleId": self.selected_primary_style,
            "subStyleId": self.selected_sub_style,
            "selectedPerkIds": perks,
            "current": True,
        }

        try:
            c_req = self.lcu.request("GET", "/lol-perks/v1/currentpage")
            if c_req and c_req.status_code == 200:
                curr = c_req.json()
                if curr.get("isEditable", False):
                    self.lcu.request("DELETE", f"/lol-perks/v1/pages/{curr['id']}")

            res = self.lcu.request("POST", "/lol-perks/v1/pages", page_data)
            if res and res.status_code in [200, 204]:
                self._set_status("Equipped Successfully!")
        except Exception as e:
            self._set_status(f"Error: {e}", True)

    def _build_perk_list(self):
        perks = []
        for d in [
            self.current_selections["primary"],
            self.current_selections["secondary"],
            self.current_selections["shards"],
        ]:
            for k in sorted(d.keys()):
                perks.append(d[k])
        return perks

    def delete_page(self, name):
        self.page_manager.delete_page(name)

    def _delete_page(self):
        name = self.selected_page_var.get()
        if name == "-- New Page --":
            return
        self.page_manager.delete_page(name)
        self._refresh_page_dropdown()
        self.selected_page_var.set("-- New Page --")
        self._on_page_selected("-- New Page --")
        self._set_status(f"Deleted {name}")

    def show_tooltip(self, event, title, desc):
        if hasattr(self, "_tooltip_job") and self._tooltip_job:
            self.after_cancel(self._tooltip_job)
        self._tooltip_job = self.after(
            150, lambda: self._do_show_tooltip(event, title, desc)
        )

    def _do_show_tooltip(self, event, title, desc):
        self._force_hide_tooltip()
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return

        import re

        desc = re.sub("<[^<]+?>", "", desc)

        self.tooltip_label = tkinter.Toplevel(self)
        self.tooltip_label.wm_overrideredirect(True)
        self.tooltip_label.geometry(f"+{event.x_root+20}+{event.y_root+20}")
        self.tooltip_label.attributes("-topmost", True)
        self.tooltip_label.configure(bg="#1A1A1A")

        f = ctk.CTkFrame(
            self.tooltip_label,
            fg_color="#1A1A1A",
            border_width=1,
            border_color=get_color("colors.accent.primary"),
        )
        f.pack()

        ctk.CTkLabel(
            f,
            text=title.upper(),
            font=get_font("header"),
            text_color=get_color("colors.accent.primary"),
        ).pack(pady=(5, 0), padx=10, anchor="w")
        ctk.CTkLabel(
            f,
            text=desc,
            font=get_font("body"),
            text_color="#DDDDDD",
            wraplength=300,
            justify="left",
        ).pack(pady=(5, 10), padx=10)

    def hide_tooltip(self, event):
        if hasattr(self, "_tooltip_job") and self._tooltip_job:
            self.after_cancel(self._tooltip_job)
            self._tooltip_job = None
        self._force_hide_tooltip()

    def _force_hide_tooltip(self):
        if self.tooltip_label:
            try:
                self.tooltip_label.destroy()
            except Exception:
                pass
            self.tooltip_label = None
