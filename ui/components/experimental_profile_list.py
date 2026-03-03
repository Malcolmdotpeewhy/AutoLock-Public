"""
Experimental Profile List — Compact Analytics Grid
Renders a dense, grid-based champion preference table.
"""
import time
import customtkinter as ctk

# ── Column Spec ──────────────────────────────────────────────────────────────
# (label, width, anchor)
COLUMNS = [
    ("RANK",        48,  "center"),
    ("CHAMPION",   160,  "w"),
    ("SCORE",       64,  "center"),
    ("PICKS",       52,  "center"),
    ("BENCH",       52,  "center"),
    ("PICK %",      56,  "center"),
    ("CONF",        72,  "center"),
    ("TREND",       52,  "center"),
    ("LAST PICKED", 88,  "center"),
]

ROW_HEIGHT   = 44      # px
ICON_SIZE    = 28      # px
HEADER_H     = 36      # px
OUTER_PAD    = 8
ROW_PAD_Y    = 1
ROW_PAD_X    = 6

# ── Color palette ─────────────────────────────────────────────────────────────
C_BG         = "transparent"
C_ROW_ODD    = ("#f0f0f0", "#1e1e1e")
C_ROW_EVEN   = ("#e8e8e8", "#252525")
C_HEADER_BG  = ("#d4d4d4", "#181818")
C_POSITIVE   = "#4CAF50"
C_NEGATIVE   = "#EF5350"
C_NEUTRAL    = "#9E9E9E"
C_RANK_1     = "#FFD700"
C_RANK_23    = "#90CAF9"
C_SEP        = ("#b0b0b0", "#333333")

# ── Trend logic ───────────────────────────────────────────────────────────────
def _trend(item):
    picks = item.get("picked_count", 0)
    bench = item.get("bench_seen_count", 0)
    total = picks + bench
    if total == 0:
        return "→", C_NEUTRAL
    ratio = picks / total
    if ratio > 0.6:
        return "↑", C_POSITIVE
    if ratio < 0.35:
        return "↓", C_NEGATIVE
    return "→", C_NEUTRAL


def _format_time_ago(ts):
    if not ts:
        return "Never"
    diff = time.time() - ts
    if diff < 60:
        return "Just now"
    if diff < 3600:
        return f"{int(diff // 60)}m ago"
    if diff < 86400:
        return f"{int(diff // 3600)}h ago"
    return f"{int(diff // 86400)}d ago"


class ConfidenceBar(ctk.CTkFrame):
    """Mini horizontal bar representing low/mid/high confidence."""

    LEVELS = [
        (1,  "#555555", 18),   # low
        (3,  "#88AACC", 36),   # mid
        (99, "#4CAF50", 52),   # high
    ]

    def __init__(self, master, value, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        kwargs.setdefault("height", 6)
        kwargs.setdefault("width", 52)
        super().__init__(master, **kwargs)
        self.pack_propagate(False)
        color, width = "#555555", 18
        for threshold, col, w in self.LEVELS:
            if value <= threshold:
                color, width = col, w
                break
        else:
            color, width = self.LEVELS[-1][1], self.LEVELS[-1][2]

        bar = ctk.CTkFrame(self, fg_color=color, corner_radius=2, height=6, width=width)
        bar.place(x=0, rely=0.5, anchor="w")


class ExperimentalProfileList(ctk.CTkFrame):
    """Fixed-column analytics grid for the Experimental Profile tab."""

    def __init__(self, master, model_service, asset_manager, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self.model        = model_service
        self.asset_manager = asset_manager

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Column header bar (fixed / non-scrolling) ─────────────────────────
        self._header_bar = ctk.CTkFrame(
            self,
            fg_color=C_HEADER_BG,
            height=HEADER_H,
            corner_radius=4,
        )
        self._header_bar.grid(row=0, column=0, sticky="ew", padx=OUTER_PAD, pady=(OUTER_PAD, 0))
        self._header_bar.pack_propagate(False)
        self._build_header()

        # ── Scrollable list ───────────────────────────────────────────────────
        self._scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=C_BG,
            scrollbar_button_color=("#bbbbbb", "#444444"),
            scrollbar_button_hover_color=("#999999", "#666666"),
        )
        self._scroll.grid(row=1, column=0, sticky="nsew", padx=OUTER_PAD, pady=(2, OUTER_PAD))

        self.render()

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self):
        for col, (label, width, anchor) in enumerate(COLUMNS):
            ctk.CTkLabel(
                self._header_bar,
                text=label,
                width=width,
                font=("Arial", 11, "bold"),
                text_color=("#555555", "#aaaaaa"),
                anchor=anchor,
            ).grid(row=0, column=col, padx=(4, 0), pady=0, sticky="nsew")
        # Bottom separator
        sep = ctk.CTkFrame(self._header_bar, fg_color=C_SEP, height=1)
        sep.place(relx=0, rely=1.0, relwidth=1.0, anchor="sw")

    # ── Row Rendering ─────────────────────────────────────────────────────────

    def render(self):
        for w in self._scroll.winfo_children():
            w.destroy()

        if not self.model:
            ctk.CTkLabel(
                self._scroll,
                text="Loading behavioral profile...",
                text_color=C_NEUTRAL,
                font=("Arial", 13),
            ).pack(pady=24)
            return

        ranked = self.model.get_ranked_list()
        if not ranked:
            ctk.CTkLabel(
                self._scroll,
                text="No matches tracked yet.\nPlay ARAM matches to build your profile.",
                text_color=C_NEUTRAL,
                font=("Arial", 13),
                justify="center",
            ).pack(pady=32)
            return

        total_picks = sum(c.get("picked_count", 0) for c in ranked)

        for i, item in enumerate(ranked):
            bg = C_ROW_ODD if i % 2 == 0 else C_ROW_EVEN
            row = ctk.CTkFrame(
                self._scroll,
                fg_color=bg,
                corner_radius=3,
                height=ROW_HEIGHT,
            )
            row.pack(fill="x", pady=ROW_PAD_Y, padx=ROW_PAD_X)
            row.pack_propagate(False)

            self._fill_row(row, i, item, total_picks)

    def _fill_row(self, row, rank_idx, item, total_picks):
        # ── Rank ──────────────────────────────────────────────────────────────
        if rank_idx == 0:
            rank_color = C_RANK_1
        elif rank_idx <= 2:
            rank_color = C_RANK_23
        else:
            rank_color = C_NEUTRAL

        ctk.CTkLabel(
            row,
            text=f"#{rank_idx + 1}",
            width=COLUMNS[0][1],
            font=("Arial", 13, "bold"),
            text_color=rank_color,
            anchor="center",
        ).grid(row=0, column=0, padx=4, sticky="ns")

        # ── Champion icon + name ───────────────────────────────────────────────
        champ_key = item.get("champion", "")
        display_name = champ_key
        if self.asset_manager and self.asset_manager.champ_data:
            display_name = self.asset_manager.champ_data.get(champ_key, {}).get("name", champ_key)

        champ_cell = ctk.CTkFrame(row, fg_color="transparent", width=COLUMNS[1][1])
        champ_cell.pack_propagate(False)
        champ_cell.grid(row=0, column=1, padx=(4, 0), sticky="ns")

        if self.asset_manager:
            icon = self.asset_manager.get_icon("champion", champ_key, size=(ICON_SIZE, ICON_SIZE))
            if icon:
                ctk.CTkLabel(champ_cell, text="", image=icon).pack(side="left", padx=(4, 3))

        ctk.CTkLabel(
            champ_cell,
            text=display_name,
            font=("Arial", 13),
            anchor="w",
        ).pack(side="left", fill="x")

        # ── Score ─────────────────────────────────────────────────────────────
        score = item.get("score", 0.0)
        score_color = C_POSITIVE if score > 0 else C_NEGATIVE if score < 0 else C_NEUTRAL
        ctk.CTkLabel(
            row,
            text=f"{score:.2f}",
            width=COLUMNS[2][1],
            font=("Arial", 12, "bold"),
            text_color=score_color,
            anchor="center",
        ).grid(row=0, column=2, padx=(4, 0), sticky="ns")

        # ── Picks ─────────────────────────────────────────────────────────────
        ctk.CTkLabel(
            row,
            text=str(item.get("picked_count", 0)),
            width=COLUMNS[3][1],
            font=("Arial", 11),
            anchor="center",
        ).grid(row=0, column=3, padx=(4, 0), sticky="ns")

        # ── Bench ─────────────────────────────────────────────────────────────
        ctk.CTkLabel(
            row,
            text=str(item.get("bench_seen_count", 0)),
            width=COLUMNS[4][1],
            font=("Arial", 11),
            anchor="center",
        ).grid(row=0, column=4, padx=(4, 0), sticky="ns")

        # ── Pick % ────────────────────────────────────────────────────────────
        picks = item.get("picked_count", 0)
        pct = f"{(picks / total_picks * 100):.0f}%" if total_picks > 0 else "—"
        ctk.CTkLabel(
            row,
            text=pct,
            width=COLUMNS[5][1],
            font=("Arial", 11),
            anchor="center",
        ).grid(row=0, column=5, padx=(4, 0), sticky="ns")

        # ── Confidence bar ────────────────────────────────────────────────────
        conf_cell = ctk.CTkFrame(row, fg_color="transparent", width=COLUMNS[6][1])
        conf_cell.pack_propagate(False)
        conf_cell.grid(row=0, column=6, padx=(4, 0), sticky="ns")
        bar = ConfidenceBar(conf_cell, value=item.get("confidence", 0))
        bar.place(relx=0.5, rely=0.5, anchor="center")

        # ── Trend ─────────────────────────────────────────────────────────────
        icon_text, t_color = _trend(item)
        ctk.CTkLabel(
            row,
            text=icon_text,
            width=COLUMNS[7][1],
            font=("Arial", 16),
            text_color=t_color,
            anchor="center",
        ).grid(row=0, column=7, padx=(4, 0), sticky="ns")

        # ── Last Picked ───────────────────────────────────────────────────────
        ctk.CTkLabel(
            row,
            text=_format_time_ago(item.get("last_picked")),
            width=COLUMNS[8][1],
            font=("Arial", 11),
            text_color=("#777777", "#888888"),
            anchor="center",
        ).grid(row=0, column=8, padx=(4, 0), sticky="ns")

    def refresh(self):
        self.render()
