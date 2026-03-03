import customtkinter as ctk

class DraggableList(ctk.CTkScrollableFrame):
    def __init__(self, master, items, on_reorder, on_remove, asset_manager=None, **kwargs):
        super().__init__(master, **kwargs)
        self.items = items
        self.on_reorder = on_reorder
        self.on_remove = on_remove
        self.asset_manager = asset_manager
        self._row_frames = []
        self._drag_data = {"y": 0, "item": None, "index": -1}
        self.render()

    def render(self):
        # Prevent destroying CTkScrollableFrame internals (Canvas/Scrollbar).
        for widget in self._row_frames:
            if widget.winfo_exists():
                widget.destroy()
        self._row_frames.clear()
        
        if not self.items:
            lbl_empty = ctk.CTkLabel(self, text="Build your ARAM priority list.\nClick '+ Add Champion' to start.", text_color="gray")
            lbl_empty.pack(pady=20)
            self._row_frames.append(lbl_empty)
            return

        for i, item in enumerate(self.items):
            frame = ctk.CTkFrame(self, fg_color=("gray85", "gray20"))
            frame.pack(fill="x", pady=2, padx=5)
            self._row_frames.append(frame)
            
            # Priority Number
            lbl_pri = ctk.CTkLabel(frame, text=f"#{i+1}", width=30, font=("Arial", 12, "bold"), text_color="gold")
            lbl_pri.pack(side="left", padx=5)
            
            # Champion Icon
            if self.asset_manager:
                icon = self.asset_manager.get_icon("champion", item, size=(32, 32))
                if icon:
                    lbl_icon = ctk.CTkLabel(frame, text="", image=icon)
                    lbl_icon.pack(side="left", padx=5)
            
            # Name
            display_name = item
            if self.asset_manager and self.asset_manager.champ_data and item in self.asset_manager.champ_data:
                display_name = self.asset_manager.champ_data[item].get("name", item)
                
            lbl_name = ctk.CTkLabel(frame, text=display_name)
            lbl_name.pack(side="left", padx=5)
            
            # Action Buttons Container
            actions = ctk.CTkFrame(frame, fg_color="transparent")
            actions.pack(side="right", padx=5)
            
            # Up Button
            btn_up = ctk.CTkButton(
                actions, text="▲", width=25, height=25,
                fg_color="transparent", hover_color="gray30",
                command=lambda idx=i: self._move_item(idx, -1)
            )
            btn_up.pack(side="left", padx=2)
            if i == 0:
                btn_up.configure(state="disabled", text_color="gray40")
                
            # Down Button
            btn_down = ctk.CTkButton(
                actions, text="▼", width=25, height=25,
                fg_color="transparent", hover_color="gray30",
                command=lambda idx=i: self._move_item(idx, 1)
            )
            btn_down.pack(side="left", padx=2)
            if i == len(self.items) - 1:
                btn_down.configure(state="disabled", text_color="gray40")

            # Remove Button
            btn_remove = ctk.CTkButton(
                actions, text="❌", width=30, height=25,
                fg_color="transparent", hover_color="red", 
                command=lambda x=item: self._do_remove(x)
            )
            btn_remove.pack(side="left", padx=(5, 0))
            
            # Optional Drag Handle (Kept for flexibility but less buggy now)
            lbl_drag = ctk.CTkLabel(frame, text=" ↕ ", cursor="hand2")
            lbl_drag.pack(side="right", padx=5)
            
            lbl_drag.bind("<Button-1>", lambda e, x=item, idx=i: self._on_drag_start(e, x, idx))
            lbl_drag.bind("<B1-Motion>", self._on_drag_motion)
            lbl_drag.bind("<ButtonRelease-1>", self._on_drag_release)

    def _flash_success(self, frame_index):
        """Briefly flash a row's background to indicate successful reordering."""
        try:
            if 0 <= frame_index < len(self._row_frames):
                frame = self._row_frames[frame_index]
                if frame.winfo_exists():
                    original_color = frame.cget("fg_color")
                    # Flash with a subtle success color/highlight
                    frame.configure(fg_color="#2A3A2C") # Subtle green hint
                    # Fade back to original after 300ms
                    self.after(300, lambda: frame.configure(fg_color=original_color) if frame.winfo_exists() else None)
        except Exception:
            pass

    def _move_item(self, index, offset):
        if 0 <= index + offset < len(self.items):
            item = self.items.pop(index)
            new_idx = index + offset
            self.items.insert(new_idx, item)
            self.on_reorder(self.items)
            self.render()
            self._flash_success(new_idx)

    def _do_remove(self, item):
        self.on_remove(item)
        
    def _on_drag_start(self, event, item, index):
        self._drag_data["item"] = item
        self._drag_data["index"] = index
        self._drag_data["y"] = event.y_root
        
        # Malcolm's UX Enhancement: Visual Drag & Drop
        import tkinter
        try:
            # Try to get the frame that contains the drag handle
            frame = self._row_frames[index]

            # Create a floating copy of the row
            window = tkinter.Toplevel(self)
            window.wm_overrideredirect(True)
            window.attributes("-topmost", True)
            window.attributes("-alpha", 0.8) # Semi-transparent

            # Match the position
            x = frame.winfo_rootx()
            y = frame.winfo_rooty()
            window.geometry(f"+{x}+{y}")

            # Give it a background matching the app theme
            from .factory import get_color
            bg_color = get_color("colors.background.card")
            window.configure(bg=bg_color)

            # Create a simplified visual representation
            content = ctk.CTkFrame(
                window,
                fg_color=bg_color,
                border_width=1,
                border_color=get_color("colors.accent.primary"),
                corner_radius=4,
                width=frame.winfo_width(),
                height=frame.winfo_height()
            )
            content.pack(fill="both", expand=True)
            content.pack_propagate(False)

            display_name = item
            if self.asset_manager and self.asset_manager.champ_data and item in self.asset_manager.champ_data:
                display_name = self.asset_manager.champ_data[item].get("name", item)

            # Icon
            if self.asset_manager:
                icon = self.asset_manager.get_icon("champion", item, size=(32, 32))
                if icon:
                    lbl_icon = ctk.CTkLabel(content, text="", image=icon)
                    lbl_icon.pack(side="left", padx=10, pady=4)

            # Name
            lbl_name = ctk.CTkLabel(content, text=display_name, font=("Arial", 12))
            lbl_name.pack(side="left", padx=5)

            self._drag_data["window"] = window
            self._drag_data["x_offset"] = event.x_root - x
            self._drag_data["y_offset"] = event.y_root - y

            # Visually dim the original row
            frame.configure(fg_color=get_color("colors.background.app"))
        except Exception as e:
            print(f"Drag UI setup error: {e}")

    def _on_drag_motion(self, event):
        if not self._drag_data.get("window"): return

        try:
            window = self._drag_data["window"]
            x = event.x_root - self._drag_data["x_offset"]
            y = event.y_root - self._drag_data["y_offset"]
            window.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _on_drag_release(self, event):
        if not self._drag_data["item"]: return
        
        # Clean up floating window
        if self._drag_data.get("window"):
            try:
                self._drag_data["window"].destroy()
            except Exception:
                pass

        delta_y = event.y_root - self._drag_data["y"]
        row_height = 40
        slots_moved = round(delta_y / row_height)
        
        needs_render = False
        if slots_moved != 0:
            old_idx = self._drag_data["index"]
            new_idx = max(0, min(len(self.items) - 1, old_idx + slots_moved))
            
            if old_idx != new_idx:
                item = self.items.pop(old_idx)
                self.items.insert(new_idx, item)
                self.on_reorder(self.items)
                needs_render = True
                
        # If no move happened, we still need to render to restore the dimmed row
        if not needs_render:
            self.render()
        else:
            self.render()
            self._flash_success(new_idx)

        self._drag_data = {"y": 0, "item": None, "index": -1, "window": None}

    def update_items(self, new_items):
        self.items = new_items
        self.render()
