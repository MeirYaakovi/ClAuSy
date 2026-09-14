"""ClAuSy — Claude Paths Manager UI."""
import copy
import os
import threading
import time
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

import customtkinter as ctk

import claude_meta
import config_manager
import storage

ctk.set_appearance_mode("dark")

# ─── palette ─────────────────────────────────────────────────────────────────
BG      = "#12121e"
SURF    = "#1c1c2e"
SURF2   = "#26263e"
SURF3   = "#30304a"
TEXT    = "#eaeaf8"   # bright readable white-blue
DIM     = "#a0a0c8"   # lighter grey-blue for secondary text
ACCENT  = "#7c6af7"
ACC2    = "#5a4ec0"

CC_R    = "#e74c3c"   # red   — permissions.allow
CC_G    = "#27ae60"   # green — additionalDirectories
CD_B    = "#2980b9"   # blue  — Desktop MCP
OFF     = "#3a3a5c"
OFF_TXT = "#6060a0"

ICON_S  = 24
THUMB_W = 160
THUMB_H = 148
CPAD    = 14

DOCS_SCHEDULED_TASKS_URL = "https://code.claude.com/docs/en/desktop-scheduled-tasks"

# plain-language names/descriptions for each toggle, grouped by product —
# used in the legend, column tooltips, confirmation dialogs, and Explained tab.
COLUMN_NAMES = {
    "cc_allow":      "Claude Code — Allow List",
    "cc_additional": "Claude Code — Additional Directories",
    "cd":            "Claude Desktop — MCP Filesystem",
}
COLUMN_HELP = {
    "cc_allow":      "Claude Code (CLI) can freely read/write here without asking permission each time.",
    "cc_additional": "Claude Code (CLI) can access this folder, in addition to the current project folder.",
    "cd":            "Claude Desktop app can access this folder through its filesystem tool (MCP).",
}

SORT_LABELS = {"name_asc": "Name A→Z", "name_desc": "Name Z→A",
               "date_asc": "Date ↑", "date_desc": "Date ↓"}
VIEW_LABELS = {"list": "≡ List", "thumb": "⊞ Thumb"}


class Tooltip:
    """Small delayed tooltip shown on hover over any widget."""

    def __init__(self, widget, text: str, delay_ms: int = 400):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after_id = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<Button-1>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def _schedule(self, _=None):
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _show(self):
        self._after_id = None
        if self._tip is not None:
            return
        try:
            if not self.widget.winfo_exists():
                return
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except tk.TclError:
            return
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self._tip, text=self.text, bg="#2a2a44", fg=TEXT,
                 font=("Segoe UI", 9), padx=8, pady=4,
                 wraplength=260, justify="left",
                 relief="solid", bd=1).pack()

    def _hide(self, _=None):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None


# ─── helpers ─────────────────────────────────────────────────────────────────

def _norm(p: str) -> str:
    return os.path.normpath(p)


def _ctime(p: str) -> float:
    try:
        return os.path.getctime(p)
    except OSError:
        return 0.0


def _snap(entries: list) -> list:
    return [copy.copy(e) for e in entries]


def _open_path(p: str):
    if p and os.path.exists(p):
        os.startfile(p)


# ─── widgets ─────────────────────────────────────────────────────────────────

class ToggleCircle(tk.Canvas):
    """24×24 clickable circle toggle. Calls pre_toggle() before changing state."""

    def __init__(self, parent, letter: str, on_color: str,
                 state: bool = False, pre_toggle=None, on_toggle=None,
                 bg: str = SURF, tooltip: str = "", **kw):
        super().__init__(parent, width=ICON_S, height=ICON_S,
                         bd=0, highlightthickness=0, bg=bg, **kw)
        self.letter     = letter
        self.on_color   = on_color
        self._state     = state
        self.pre_toggle = pre_toggle
        self.on_toggle  = on_toggle
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>",    lambda e: self.config(cursor="hand2"))
        self.bind("<Leave>",    lambda e: self.config(cursor="arrow"))
        if tooltip:
            Tooltip(self, tooltip)
        self._draw()

    def _draw(self):
        self.delete("all")
        fill    = self.on_color if self._state else ""
        outline = self.on_color if self._state else "#5858a8"
        self.create_oval(2, 2, ICON_S - 2, ICON_S - 2,
                         fill=fill, outline=outline, width=2)
        self.create_text(ICON_S // 2, ICON_S // 2 + 1,
                         text=self.letter,
                         fill="white" if self._state else "#6868b8",
                         font=("Segoe UI", 8, "bold"))

    def _click(self, _=None):
        if self.pre_toggle:
            self.pre_toggle()
        self._state = not self._state
        self._draw()
        if self.on_toggle:
            self.on_toggle(self._state)

    def set(self, v: bool):
        if self._state != v:
            self._state = v
            self._draw()

    def get(self) -> bool:
        return self._state


class DirectoryRow:
    """One row in the list view — placed directly on a CTkScrollableFrame's grid."""

    def __init__(self, parent, entry: dict, idx: int,
                 on_change=None, on_pre_change=None):
        self.entry         = entry
        self.on_change     = on_change
        self.on_pre_change = on_pre_change
        self._sel          = tk.BooleanVar(value=False)

        self.cb = ctk.CTkCheckBox(parent, text="", variable=self._sel,
                                   onvalue=True, offvalue=False,
                                   width=ICON_S, checkbox_width=18, checkbox_height=18,
                                   fg_color=ACCENT, hover_color=ACC2,
                                   border_color=OFF, checkmark_color=TEXT)

        self._lv = tk.StringVar(value=entry.get("label", ""))
        self.le  = ctk.CTkEntry(parent, textvariable=self._lv,
                                fg_color=SURF2, text_color=TEXT,
                                border_color=OFF, border_width=1,
                                font=("Segoe UI", 9), width=150)
        self.le.bind("<FocusOut>", lambda e: self._sync_label())
        self.le.bind("<Return>",   lambda e: self._sync_label())

        self.pl = ctk.CTkLabel(parent, text=entry.get("path", ""),
                               fg_color="transparent", text_color=DIM,
                               font=("Consolas", 10), anchor="w", cursor="hand2")
        self.pl.bind("<Double-Button-1>", self._open_dir)

        self.t_r = ToggleCircle(parent, "C", CC_R,
                                 state=entry.get("cc_allow", False),
                                 pre_toggle=on_pre_change,
                                 on_toggle=lambda v: self._set("cc_allow", v), bg=SURF,
                                 tooltip=f"{COLUMN_NAMES['cc_allow']}\n{COLUMN_HELP['cc_allow']}")
        self.t_g = ToggleCircle(parent, "C", CC_G,
                                 state=entry.get("cc_additional", False),
                                 pre_toggle=on_pre_change,
                                 on_toggle=lambda v: self._set("cc_additional", v), bg=SURF,
                                 tooltip=f"{COLUMN_NAMES['cc_additional']}\n{COLUMN_HELP['cc_additional']}")
        self.t_d = ToggleCircle(parent, "D", CD_B,
                                 state=entry.get("cd", False),
                                 pre_toggle=on_pre_change,
                                 on_toggle=lambda v: self._set("cd", v), bg=SURF,
                                 tooltip=f"{COLUMN_NAMES['cd']}\n{COLUMN_HELP['cd']}")

    def place(self, row: int):
        self.cb.grid(row=row, column=0, padx=(8, 2), pady=4, sticky="ns")
        self.le.grid(row=row, column=1, padx=4,      pady=4, sticky="ew")
        self.pl.grid(row=row, column=2, padx=4,      pady=4, sticky="ew")
        self.t_r.grid(row=row, column=3, padx=10,    pady=4)
        self.t_g.grid(row=row, column=4, padx=10,    pady=4)
        self.t_d.grid(row=row, column=5, padx=10,    pady=4)

    def _open_dir(self, _=None):
        p = self.entry.get("path", "")
        if os.path.isdir(p):
            os.startfile(p)

    def _sync_label(self):
        self.entry["label"] = self._lv.get()

    def _set(self, key, val):
        self.entry[key] = val
        if self.on_change:
            self.on_change()

    def set_toggle(self, key: str, val: bool):
        self.entry[key] = val
        {"cc_allow": self.t_r, "cc_additional": self.t_g, "cd": self.t_d}[key].set(val)

    def is_checked(self) -> bool:
        return self._sel.get()

    def sync(self):
        self.entry["label"]         = self._lv.get()
        self.entry["cc_allow"]      = self.t_r.get()
        self.entry["cc_additional"] = self.t_g.get()
        self.entry["cd"]            = self.t_d.get()


# ─── main app ────────────────────────────────────────────────────────────────

class ClausyApp:
    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title("ClAuSy — Claude Paths Manager")
        self.root.configure(fg_color=BG)
        self.root.minsize(900, 600)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # bring window to front on launch
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(200, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()

        self._entries: list[dict] = []
        self._rows:    list[DirectoryRow] = []
        self._pending  = False
        self._undo_stack: list[list[dict]] = []

        self._cc_var   = tk.StringVar()
        self._cd_var   = tk.StringVar()
        self._sort_var = tk.StringVar(value="name_asc")
        self._view_var = tk.StringVar(value="list")

        self._build_ui()
        self._load_settings()

    # ── UI skeleton ───────────────────────────────────────────────────────────

    def _build_ui(self):
        self.nb = ctk.CTkTabview(
            self.root, fg_color=BG, anchor="w",
            segmented_button_fg_color=SURF2,
            segmented_button_selected_color=ACCENT,
            segmented_button_selected_hover_color=ACC2,
            segmented_button_unselected_color=SURF2,
            segmented_button_unselected_hover_color=SURF3,
            text_color=DIM, text_color_disabled=OFF_TXT,
            command=self._on_tab_changed,
        )
        self.nb.pack(fill="both", expand=True, padx=6, pady=(6, 0))

        self._tab_settings = self.nb.add("Settings")
        self._tab_dirs     = self.nb.add("Directories")
        self._tab_claudemd = self.nb.add("CLAUDE.md Map")
        self._tab_agents   = self.nb.add("Agents & Routines")
        self._tab_explain  = self.nb.add("Explained")

        for t in (self._tab_settings, self._tab_dirs, self._tab_claudemd,
                  self._tab_agents, self._tab_explain):
            t.configure(fg_color=BG)

        self._build_settings_tab(self._tab_settings)
        self._build_dirs_tab(self._tab_dirs)
        self._build_claudemd_tab(self._tab_claudemd)
        self._build_agents_tab(self._tab_agents)
        self._build_explain_tab(self._tab_explain)

    def _on_tab_changed(self):
        name = self.nb.get()
        if name == "CLAUDE.md Map":
            self._refresh_claudemd_tab()
        elif name == "Agents & Routines":
            self._refresh_agents_tab()

    def _on_close(self):
        if self._pending:
            if not messagebox.askyesno(
                "ClAuSy",
                "You have directory changes that were not written yet "
                "(Execute Changes was never pressed).\n\n"
                "Quit anyway and lose them?"):
                return
        self._save_window_state()
        self.root.destroy()

    def _save_window_state(self):
        try:
            maximized = self.root.state() == "zoomed"
        except tk.TclError:
            maximized = True
        data = storage.load()
        data["window_maximized"] = maximized
        if not maximized:
            data["window_geometry"] = self.root.geometry()
        storage.save(data)

    # ── Settings tab ─────────────────────────────────────────────────────────

    def _build_settings_tab(self, parent):
        wrap = ctk.CTkFrame(parent, fg_color=BG)
        wrap.pack(fill="both", expand=True, padx=34, pady=26)
        wrap.columnconfigure(0, weight=1)

        self._val_labels: dict = {}

        def row(label, var, r, cfg_type):
            ctk.CTkLabel(wrap, text=label, fg_color="transparent", text_color=TEXT,
                         font=("Segoe UI", 12, "bold"), anchor="w"
                         ).grid(row=r, column=0, sticky="w", pady=(16, 4))
            f = ctk.CTkFrame(wrap, fg_color="transparent")
            f.grid(row=r + 1, column=0, sticky="ew")
            f.columnconfigure(0, weight=1)
            ctk.CTkEntry(f, textvariable=var, fg_color=SURF2, text_color=TEXT,
                        border_color=OFF, border_width=1,
                        font=("Consolas", 10), height=32
                        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
            ctk.CTkButton(f, text="Browse", fg_color=SURF3, hover_color=ACCENT,
                         text_color=TEXT, width=80, height=32,
                         command=lambda v=var: self._browse_file(v)
                         ).grid(row=0, column=1)
            lbl = ctk.CTkLabel(f, text="—", fg_color="transparent", text_color=DIM,
                              font=("Segoe UI", 14), width=20)
            lbl.grid(row=0, column=2, padx=(10, 0))
            self._val_labels[cfg_type] = lbl

        row("Claude Code (CLI) settings file  —  controls the 🔴🟢 C toggles below  ( ~/.claude/settings.json )",
            self._cc_var, 0, "cc")
        row("Claude Desktop (app) config  —  controls the 🔵 D toggle below  ( claude_desktop_config.json )",
            self._cd_var, 2, "cd")

        btn_f = ctk.CTkFrame(wrap, fg_color="transparent")
        btn_f.grid(row=4, column=0, sticky="w", pady=24)

        def btn(parent, label, cmd, accent=False):
            c = ACCENT if accent else SURF3
            return ctk.CTkButton(parent, text=label, fg_color=c, hover_color=ACC2,
                                 text_color=TEXT, height=34, font=("Segoe UI", 10),
                                 command=cmd)

        btn(btn_f, "Auto-Detect",   self._auto_detect        ).pack(side="left", padx=(0, 10))
        btn(btn_f, "Save & Reload", self._save_and_reload,
            accent=True                                       ).pack(side="left", padx=(0, 10))
        btn(btn_f, "✔ Check",       self._validate_paths      ).pack(side="left")

        self._status_lbl = ctk.CTkLabel(wrap, text="", fg_color="transparent",
                                        text_color=DIM, font=("Segoe UI", 10), anchor="w")
        self._status_lbl.grid(row=5, column=0, sticky="w", pady=(6, 0))

    # ── Directories tab ───────────────────────────────────────────────────────

    def _build_dirs_tab(self, parent):
        # ── toolbar ──────────────────────────────────────────────────────────
        toolbar = ctk.CTkFrame(parent, fg_color=SURF2, corner_radius=0)
        toolbar.pack(fill="x", side="top")
        inner = ctk.CTkFrame(toolbar, fg_color="transparent")
        inner.pack(fill="x", padx=8, pady=6)

        def tbtn(text, cmd):
            b = ctk.CTkButton(inner, text=text, fg_color=SURF3, hover_color=ACCENT,
                              text_color=TEXT, height=30, font=("Segoe UI", 10),
                              command=cmd)
            b.pack(side="left", padx=4)
            return b

        tbtn("＋ Add",    self._add_directory)
        tbtn("✕ Delete", self._delete_selected)
        self._undo_btn = tbtn("↩ Undo", self._undo)
        self._undo_btn.configure(state="disabled", text_color=OFF_TXT)

        ctk.CTkLabel(inner, text="Sort:", fg_color="transparent", text_color=DIM,
                    font=("Segoe UI", 10)).pack(side="left", padx=(16, 6))
        self._sort_seg = ctk.CTkSegmentedButton(
            inner, values=list(SORT_LABELS.values()), command=self._on_sort_changed,
            fg_color=SURF, selected_color=ACCENT, selected_hover_color=ACC2,
            unselected_color=SURF3, unselected_hover_color=SURF3,
            text_color=TEXT, height=30)
        self._sort_seg.pack(side="left")

        ctk.CTkLabel(inner, text="View:", fg_color="transparent", text_color=DIM,
                    font=("Segoe UI", 10)).pack(side="left", padx=(16, 6))
        self._view_seg = ctk.CTkSegmentedButton(
            inner, values=list(VIEW_LABELS.values()), command=self._on_view_changed,
            fg_color=SURF, selected_color=ACCENT, selected_hover_color=ACC2,
            unselected_color=SURF3, unselected_hover_color=SURF3,
            text_color=TEXT, height=30)
        self._view_seg.pack(side="left")

        # ── column headers ────────────────────────────────────────────────────
        self._header = ctk.CTkFrame(parent, fg_color=SURF3, corner_radius=0)
        self._header.pack(fill="x", side="top")
        self._header.columnconfigure(2, weight=1)

        ctk.CTkLabel(self._header, text="", fg_color="transparent", width=20
                    ).grid(row=0, column=0, padx=(8, 2))
        ctk.CTkLabel(self._header, text="Label", fg_color="transparent", text_color=TEXT,
                    font=("Segoe UI", 10, "bold"), anchor="w", width=150
                    ).grid(row=0, column=1, padx=4, pady=6, sticky="w")
        ctk.CTkLabel(self._header, text="Path", fg_color="transparent", text_color=TEXT,
                    font=("Segoe UI", 10, "bold"), anchor="w"
                    ).grid(row=0, column=2, padx=4, sticky="ew")

        badge_defs = [
            ("C", "cc_allow",      CC_R),
            ("C", "cc_additional", CC_G),
            ("D", "cd",            CD_B),
        ]
        for col_idx, (letter, key, color) in enumerate(badge_defs, start=3):
            c = tk.Canvas(self._header, width=ICON_S, height=ICON_S,
                          bd=0, highlightthickness=0, bg=SURF3, cursor="hand2")
            c.create_oval(2, 2, ICON_S-2, ICON_S-2, fill=color, outline=color)
            c.create_text(ICON_S//2, ICON_S//2+1, text=letter,
                          fill="white", font=("Segoe UI", 8, "bold"))
            c.grid(row=0, column=col_idx, padx=10, pady=6)
            c.bind("<Button-1>", lambda e, k=key: self._header_toggle(k))
            Tooltip(c, f"{COLUMN_NAMES[key]}\n{COLUMN_HELP[key]}\n\n"
                       "Click to toggle checked rows (or ALL rows if none checked).")

        # ── legend row — grouped by product, plain-language ────────────────────
        legend = ctk.CTkFrame(parent, fg_color=SURF2, corner_radius=0)
        legend.pack(fill="x", side="top")
        legend_inner = ctk.CTkFrame(legend, fg_color="transparent")
        legend_inner.pack(fill="x", padx=12, pady=5)

        legend_groups = [
            ("Claude Code (CLI):", [
                (CC_R, "C", "Allow List — auto-approved, no per-action prompts"),
                (CC_G, "C", "Additional Directories — extra folders it can reach"),
            ]),
            ("Claude Desktop (app):", [
                (CD_B, "D", "MCP Filesystem — folders the desktop app can open"),
            ]),
        ]
        for i, (group_label, items) in enumerate(legend_groups):
            if i > 0:
                sep = ctk.CTkFrame(legend_inner, fg_color=OFF, width=1)
                sep.pack(side="left", fill="y", padx=12, pady=2)
            ctk.CTkLabel(legend_inner, text=group_label, fg_color="transparent",
                        text_color=TEXT, font=("Segoe UI", 9, "bold")
                        ).pack(side="left", padx=(0, 6))
            for color, letter, label in items:
                dot = tk.Canvas(legend_inner, width=10, height=10, bg=SURF2,
                                bd=0, highlightthickness=0)
                dot.create_oval(1, 1, 9, 9, fill=color, outline=color)
                dot.pack(side="left", padx=(8, 2))
                ctk.CTkLabel(legend_inner, text=f"{letter} ({label})", fg_color="transparent",
                            text_color=DIM, font=("Segoe UI", 9)
                            ).pack(side="left", padx=(0, 12))

        # ── content area ──────────────────────────────────────────────────────
        self._content = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        self._content.pack(fill="both", expand=True, side="top")

        self._sf = ctk.CTkScrollableFrame(self._content, fg_color=SURF,
                                          scrollbar_fg_color=SURF,
                                          scrollbar_button_color=SURF3,
                                          scrollbar_button_hover_color=ACCENT)
        self._sf.pack(fill="both", expand=True)
        self._configure_row_grid(self._sf)

        # thumbnail canvas
        self._thumb_outer = tk.Frame(self._content, bg=BG)
        self._thumb_cv    = tk.Canvas(self._thumb_outer, bg=BG, bd=0,
                                       highlightthickness=0)
        self._thumb_sb    = ctk.CTkScrollbar(self._thumb_outer, orientation="vertical",
                                             command=self._thumb_cv.yview,
                                             fg_color=BG, button_color=SURF3,
                                             button_hover_color=ACCENT)
        self._thumb_cv.configure(yscrollcommand=self._thumb_sb.set)
        self._thumb_cv.pack(side="left", fill="both", expand=True)
        self._thumb_sb.pack(side="right", fill="y")
        self._thumb_cv.bind("<Configure>", lambda e: self._draw_thumbs())
        self._thumb_cv.bind("<Button-1>",  self._thumb_click)
        self._thumb_cv.bind("<MouseWheel>", lambda e: self._thumb_cv.yview_scroll(
            int(-1 * e.delta / 120), "units"))
        self._thumb_cards: list[dict] = []

        # ── footer ────────────────────────────────────────────────────────────
        footer = ctk.CTkFrame(parent, fg_color=SURF2, corner_radius=0)
        footer.pack(fill="x", side="bottom")
        footer_inner = ctk.CTkFrame(footer, fg_color="transparent")
        footer_inner.pack(fill="x", padx=14, pady=8)

        self._exec_btn = ctk.CTkButton(
            footer_inner, text="▶  Execute Changes", fg_color=ACCENT, hover_color=ACC2,
            text_color="white", height=36, font=("Segoe UI", 11, "bold"),
            command=self._execute_changes)
        self._exec_btn.pack(side="left", padx=(0, 14))

        self._prog_bar = ctk.CTkProgressBar(footer_inner, width=200, height=10,
                                            progress_color=ACCENT, fg_color=SURF3)
        self._prog_bar.set(0)
        self._prog_bar.pack(side="left")
        self._prog_lbl = ctk.CTkLabel(footer_inner, text="", fg_color="transparent",
                                      text_color=DIM, font=("Segoe UI", 10))
        self._prog_lbl.pack(side="left", padx=8)

    @staticmethod
    def _configure_row_grid(frame):
        frame.grid_columnconfigure(2, weight=1, minsize=200)
        frame.grid_columnconfigure(3, minsize=44)
        frame.grid_columnconfigure(4, minsize=44)
        frame.grid_columnconfigure(5, minsize=44)

    def _on_sort_changed(self, display_value):
        keys = {v: k for k, v in SORT_LABELS.items()}
        self._sort_var.set(keys[display_value])
        self._apply_sort()

    def _on_view_changed(self, display_value):
        keys = {v: k for k, v in VIEW_LABELS.items()}
        self._view_var.set(keys[display_value])
        self._switch_view()

    # ── settings load / save ─────────────────────────────────────────────────

    def _load_settings(self):
        data = storage.load()
        self._cc_var.set(data.get("cc_settings", ""))
        self._cd_var.set(data.get("cd_config", ""))
        self._sort_var.set(data.get("sort_mode", "name_asc"))
        self._view_var.set(data.get("view_mode", "list"))
        self._sort_seg.set(SORT_LABELS.get(self._sort_var.get(), "Name A→Z"))
        self._view_seg.set(VIEW_LABELS.get(self._view_var.get(), "≡ List"))
        self._labels: dict = data.get("labels", {})
        self._reload_entries()
        self._switch_view()
        self._validate_paths(silent=True)

    def _save_settings_data(self):
        for r in self._rows:
            r.sync()
        labels = {e["path"]: e.get("label", "") for e in self._entries}
        storage.save({
            "cc_settings": self._cc_var.get(),
            "cd_config":   self._cd_var.get(),
            "labels":      labels,
            "sort_mode":   self._sort_var.get(),
            "view_mode":   self._view_var.get(),
        })

    def _browse_file(self, var: tk.StringVar):
        p = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if p:
            var.set(p)

    def _auto_detect(self):
        det = config_manager.auto_detect()
        if det["cc_settings"]:
            self._cc_var.set(det["cc_settings"])
        if det["cd_config"]:
            self._cd_var.set(det["cd_config"])
        self._set_status("Auto-detect done — press Save & Reload to apply.")

    def _save_and_reload(self):
        if self._pending:
            if not messagebox.askyesno(
                "ClAuSy",
                "You have directory changes on the Directories tab that were "
                "never written (Execute Changes was never pressed).\n\n"
                "Reloading now will discard them and reload straight from the "
                "config files. Continue?"):
                return
        self._save_settings_data()
        self._validate_paths(silent=True)
        self._reload_entries()
        self._set_status("Saved. Config files reloaded.")

    def _set_status(self, msg: str, color: str = DIM):
        self._status_lbl.configure(text=msg, text_color=color)

    def _validate_paths(self, silent: bool = False):
        """Update ✔/✗ indicators next to each path field.
        silent=True suppresses the status-bar message (used on load/reload)."""
        errors = []
        for cfg_type, var in [("cc", self._cc_var), ("cd", self._cd_var)]:
            lbl = self._val_labels.get(cfg_type)
            if lbl is None:
                continue
            path = var.get().strip()
            if not path:
                lbl.configure(text="—", text_color=DIM)
                continue
            ok, msg = config_manager.validate_path(path, cfg_type)
            if ok:
                lbl.configure(text="✔", text_color=CC_G)
            else:
                lbl.configure(text="✗", text_color=CC_R)
                errors.append(msg)
        if not silent:
            if errors:
                self._set_status("  ·  ".join(errors), CC_R)
            else:
                self._set_status("Config files look good ✔", CC_G)

    # ── entry management ─────────────────────────────────────────────────────

    def _reload_entries(self):
        cc = self._cc_var.get()
        cd = self._cd_var.get()
        try:
            path_states = config_manager.read_all_dirs(cc, cd)
        except config_manager.ConfigError as e:
            messagebox.showerror("ClAuSy — Config Error",
                                 f"Could not read config file:\n\n{e}\n\n"
                                 "Fix the file or select a different path in Settings.")
            return

        new_entries = []
        for path, flags in path_states.items():
            label = self._labels.get(path, Path(path).name)
            new_entries.append({"path": path, "label": label, **flags})

        existing_paths = {e["path"] for e in new_entries}
        for e in self._entries:
            if e["path"] not in existing_paths:
                new_entries.append(e)

        self._entries = new_entries
        self._undo_stack.clear()
        self._undo_btn.configure(state="disabled", text_color=OFF_TXT)
        self._pending = False
        self._apply_sort(refresh=True)

    def _apply_sort(self, refresh: bool = True):
        key = self._sort_var.get()
        if key == "name_asc":
            self._entries.sort(key=lambda e: e.get("label", "").lower())
        elif key == "name_desc":
            self._entries.sort(key=lambda e: e.get("label", "").lower(), reverse=True)
        elif key == "date_asc":
            self._entries.sort(key=lambda e: _ctime(e["path"]))
        elif key == "date_desc":
            self._entries.sort(key=lambda e: _ctime(e["path"]), reverse=True)
        if refresh:
            self._refresh_list()
            if self._view_var.get() == "thumb":
                self._draw_thumbs()

    def _refresh_list(self):
        for w in self._sf.winfo_children():
            w.destroy()
        self._rows.clear()
        for i, entry in enumerate(self._entries):
            r = DirectoryRow(self._sf, entry, i,
                             on_change=lambda: setattr(self, "_pending", True),
                             on_pre_change=self._push_undo)
            r.place(i)
            self._rows.append(r)
        self._configure_row_grid(self._sf)

    def _switch_view(self):
        if self._view_var.get() == "list":
            self._thumb_outer.pack_forget()
            self._sf.pack(fill="both", expand=True)
        else:
            self._sf.pack_forget()
            self._thumb_outer.pack(fill="both", expand=True)
            self._draw_thumbs()

    # ── undo ─────────────────────────────────────────────────────────────────

    def _push_undo(self):
        self._undo_stack.append(_snap(self._entries))
        if len(self._undo_stack) > 30:
            self._undo_stack.pop(0)
        self._undo_btn.configure(state="normal", text_color=TEXT)

    def _undo(self):
        if not self._undo_stack:
            return
        snapshot = self._undo_stack.pop()
        by_path  = {s["path"]: s for s in snapshot}
        for entry in self._entries:
            if entry["path"] in by_path:
                s = by_path[entry["path"]]
                entry["cc_allow"]      = s.get("cc_allow",      False)
                entry["cc_additional"] = s.get("cc_additional", False)
                entry["cd"]            = s.get("cd",            False)
        self._refresh_list()
        if self._view_var.get() == "thumb":
            self._draw_thumbs()
        self._pending = True
        if not self._undo_stack:
            self._undo_btn.configure(state="disabled", text_color=OFF_TXT)

    # ── add / delete ─────────────────────────────────────────────────────────

    def _add_directory(self):
        p = filedialog.askdirectory(title="Select directory to add")
        if not p:
            return
        norm = _norm(p)
        if any(e["path"] == norm for e in self._entries):
            messagebox.showinfo("ClAuSy", "This path is already in the list.")
            return
        self._push_undo()
        self._entries.append({
            "path": norm, "label": Path(norm).name,
            "cc_allow": False, "cc_additional": False, "cd": False,
        })
        self._apply_sort(refresh=True)
        self._pending = True

    def _delete_selected(self):
        if not self._rows:
            return
        for r in self._rows:
            r.sync()
        sel = {r.entry["path"] for r in self._rows if r.is_checked()}
        if not sel:
            messagebox.showinfo("ClAuSy", "Check rows with the checkbox first.")
            return
        if not messagebox.askyesno("ClAuSy",
                                   f"Remove {len(sel)} entr{'y' if len(sel)==1 else 'ies'} "
                                   "from the list?\n(Config files are not changed until Execute.)"):
            return
        self._push_undo()
        self._entries = [e for e in self._entries if e["path"] not in sel]
        self._refresh_list()
        if self._view_var.get() == "thumb":
            self._draw_thumbs()
        self._pending = True

    # ── header column toggle ─────────────────────────────────────────────────

    def _header_toggle(self, key: str):
        checked = [r for r in self._rows if r.is_checked()]
        targets = checked if checked else self._rows
        if not checked and len(targets) > 1:
            label = COLUMN_NAMES.get(key, key)
            if not messagebox.askyesno(
                "ClAuSy",
                f"No rows are checked, so this will change '{label}' for "
                f"ALL {len(targets)} directories.\n\nContinue?"):
                return
        current = [r.entry.get(key, False) for r in targets]
        new_val = not all(current)
        self._push_undo()
        for r in targets:
            r.set_toggle(key, new_val)
        self._pending = True
        if self._view_var.get() == "thumb":
            self._draw_thumbs()

    # ── thumbnail canvas ─────────────────────────────────────────────────────

    def _draw_thumbs(self):
        cv = self._thumb_cv
        cv.delete("all")
        self._thumb_cards.clear()

        cw   = cv.winfo_width() or 600
        cols = max(1, (cw - CPAD) // (THUMB_W + CPAD))

        for i, entry in enumerate(self._entries):
            col = i % cols
            row = i // cols
            x0  = CPAD + col * (THUMB_W + CPAD)
            y0  = CPAD + row * (THUMB_H + CPAD)
            x1  = x0 + THUMB_W
            y1  = y0 + THUMB_H

            cv.create_rectangle(x0, y0, x1, y1, fill=SURF2, outline=SURF3, width=1)

            # folder icon
            fx, fy = x0 + THUMB_W // 2 - 24, y0 + 34
            cv.create_rectangle(fx, fy + 9,  fx + 48, fy + 38, fill="#c87e1a", outline="")
            cv.create_rectangle(fx, fy + 7,  fx + 22, fy + 14, fill="#e6952a", outline="")
            cv.create_rectangle(fx + 2, fy + 10, fx + 46, fy + 36, fill="#e6952a", outline="")

            label = entry.get("label", Path(entry["path"]).name)
            if len(label) > 16:
                label = label[:14] + "…"
            cv.create_text(x0 + THUMB_W // 2, y0 + THUMB_H - 22,
                           text=label, fill=TEXT,
                           font=("Segoe UI", 9, "bold"), anchor="center")

            p = entry.get("path", "")
            if len(p) > 24:
                p = "…" + p[-23:]
            cv.create_text(x0 + THUMB_W // 2, y0 + THUMB_H - 8,
                           text=p, fill=DIM,
                           font=("Consolas", 7), anchor="center")

            # badges: D (left), C-green (center), C-red (right)
            badge_defs = [
                ("D", CD_B, entry.get("cd",            False), x0 + 20,          "cd"),
                ("C", CC_G, entry.get("cc_additional", False), x0 + THUMB_W // 2, "cc_additional"),
                ("C", CC_R, entry.get("cc_allow",      False), x1 - 20,           "cc_allow"),
            ]
            badge_centers: dict = {}
            for letter, color, state, bx, bkey in badge_defs:
                by      = y0 + 16
                fill    = color if state else ""
                outline = color if state else "#5858a8"
                cv.create_oval(bx - 10, by - 10, bx + 10, by + 10,
                               fill=fill, outline=outline, width=2)
                cv.create_text(bx, by + 1, text=letter,
                               fill="white" if state else "#6868b8",
                               font=("Segoe UI", 8, "bold"))
                badge_centers[bkey] = (bx, by)

            self._thumb_cards.append({
                "entry":  entry,
                "bounds": (x0, y0, x1, y1),
                "badges": badge_centers,
            })

        total_rows = (len(self._entries) + cols - 1) // cols if self._entries else 1
        cv.configure(scrollregion=(0, 0, cw, CPAD + total_rows * (THUMB_H + CPAD)))

    def _thumb_click(self, event):
        cv = self._thumb_cv
        cx = cv.canvasx(event.x)
        cy = cv.canvasy(event.y)
        for card in self._thumb_cards:
            x0, y0, x1, y1 = card["bounds"]
            if not (x0 <= cx <= x1 and y0 <= cy <= y1):
                continue
            for bkey, (bx, by) in card["badges"].items():
                if abs(cx - bx) <= 11 and abs(cy - by) <= 11:
                    self._push_undo()
                    card["entry"][bkey] = not card["entry"][bkey]
                    self._pending = True
                    self._draw_thumbs()
                    return

    # ── execute ───────────────────────────────────────────────────────────────

    def _execute_changes(self):
        for r in self._rows:
            r.sync()

        cc = self._cc_var.get()
        cd = self._cd_var.get()
        if not cc and not cd:
            messagebox.showerror("ClAuSy",
                                 "No config paths set.\nGo to Settings tab first.")
            return

        # Snapshot the entries before handing them to the background thread —
        # the Directories tab stays interactive while writing, so without this
        # copy, Add/Delete/toggle clicks during the write would mutate the
        # very list/dicts apply_changes() is iterating over.
        entries_snapshot = _snap(self._entries)

        self._exec_btn.configure(state="disabled")
        self._prog_bar.set(0)
        self._prog_lbl.configure(text="Writing…", text_color=DIM)

        def worker():
            def prog(pct):
                self.root.after(0, self._prog_bar.set, pct / 100)
                self.root.after(0, self._prog_lbl.configure, {"text": f"{pct}%"})
                time.sleep(0.08)

            try:
                config_manager.apply_changes(cc, cd, entries_snapshot, progress_cb=prog)
                self.root.after(0, self._on_exec_done, True, "")
            except Exception as exc:
                self.root.after(0, self._on_exec_done, False, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_exec_done(self, ok: bool, err: str):
        self._exec_btn.configure(state="normal")
        if ok:
            self._prog_lbl.configure(text="Done ✓", text_color=CC_G)
            self._save_settings_data()
            self._pending = False
        else:
            self._prog_bar.set(0)
            self._prog_lbl.configure(text="Error", text_color=CC_R)
            messagebox.showerror("ClAuSy", f"Write failed:\n{err}")
        self.root.after(3000, lambda: self._prog_lbl.configure(text="", text_color=DIM))

    # ── shared: tracked project directories (used by Map & Agents tabs) ────────

    def _project_dirs(self) -> list:
        return [e["path"] for e in self._entries if e.get("path")]

    # ── CLAUDE.md Map tab ────────────────────────────────────────────────────

    def _build_claudemd_tab(self, parent):
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(16, 4))
        ctk.CTkLabel(top, text="Where Claude's instruction & config files live",
                    fg_color="transparent", text_color=TEXT,
                    font=("Segoe UI", 14, "bold")).pack(side="left")
        ctk.CTkButton(top, text="↻ Refresh", fg_color=SURF3, hover_color=ACCENT,
                     text_color=TEXT, width=90, height=28,
                     command=self._refresh_claudemd_tab).pack(side="right")

        self._claudemd_scroll = ctk.CTkScrollableFrame(
            parent, fg_color=BG, scrollbar_fg_color=BG,
            scrollbar_button_color=SURF3, scrollbar_button_hover_color=ACCENT)
        self._claudemd_scroll.pack(fill="both", expand=True, padx=16, pady=(4, 16))
        self._claudemd_scroll.grid_columnconfigure(1, weight=1)

    def _claudemd_row(self, parent, row, scope_label, path, exists, allow_create=False):
        badge_color = CC_G if exists else OFF_TXT
        badge = ctk.CTkLabel(parent, text=("✔" if exists else "—"),
                             fg_color="transparent", text_color=badge_color,
                             font=("Segoe UI", 13, "bold"), width=24)
        badge.grid(row=row, column=0, padx=(4, 8), pady=6, sticky="w")

        text_f = ctk.CTkFrame(parent, fg_color="transparent")
        text_f.grid(row=row, column=1, sticky="ew", pady=6)
        ctk.CTkLabel(text_f, text=scope_label, fg_color="transparent", text_color=TEXT,
                    font=("Segoe UI", 10, "bold"), anchor="w").pack(anchor="w")
        ctk.CTkLabel(text_f, text=path, fg_color="transparent", text_color=DIM,
                    font=("Consolas", 9), anchor="w").pack(anchor="w")

        btn_f = ctk.CTkFrame(parent, fg_color="transparent")
        btn_f.grid(row=row, column=2, padx=(8, 4), pady=6, sticky="e")
        if exists:
            ctk.CTkButton(btn_f, text="Open", width=70, height=26, fg_color=SURF3,
                         hover_color=ACCENT, text_color=TEXT,
                         command=lambda: _open_path(path)).pack(side="left", padx=2)
        else:
            ctk.CTkButton(btn_f, text="Open Folder", width=90, height=26, fg_color=SURF3,
                         hover_color=ACCENT, text_color=TEXT,
                         command=lambda: _open_path(str(Path(path).parent))
                         ).pack(side="left", padx=2)
            if allow_create:
                ctk.CTkButton(btn_f, text="Create", width=70, height=26, fg_color=ACCENT,
                             hover_color=ACC2, text_color="white",
                             command=lambda: self._create_claude_md(path)
                             ).pack(side="left", padx=2)

    def _create_claude_md(self, path: str):
        p = Path(path)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(
                "# הוראות (Instructions)\n\n"
                "Project-specific instructions for Claude Code go here.\n"
                "See https://code.claude.com/docs for the CLAUDE.md format.\n",
                encoding="utf-8")
        except OSError as e:
            messagebox.showerror("ClAuSy", f"Could not create file:\n{e}")
            return
        self._refresh_claudemd_tab()

    def _refresh_claudemd_tab(self):
        for w in self._claudemd_scroll.winfo_children():
            w.destroy()

        r = 0
        ctk.CTkLabel(self._claudemd_scroll, text="CLAUDE.md — instructions Claude reads automatically",
                    fg_color="transparent", text_color=DIM, font=("Segoe UI", 9),
                    anchor="w").grid(row=r, column=0, columnspan=3, sticky="w", pady=(0, 4))
        r += 1
        for entry in claude_meta.find_claude_md_files(self._project_dirs()):
            label = "Global (~/.claude)" if entry["scope"] == "global" else f"Project — {entry['label']}"
            self._claudemd_row(self._claudemd_scroll, r, label, entry["path"], entry["exists"],
                               allow_create=True)
            r += 1

        sep = ctk.CTkFrame(self._claudemd_scroll, fg_color=OFF, height=1)
        sep.grid(row=r, column=0, columnspan=3, sticky="ew", pady=14)
        r += 1

        ctk.CTkLabel(self._claudemd_scroll, text="Other Claude config locations",
                    fg_color="transparent", text_color=DIM, font=("Segoe UI", 9),
                    anchor="w").grid(row=r, column=0, columnspan=3, sticky="w", pady=(0, 4))
        r += 1

        others = [
            ("Claude Code settings.json (Global)", self._cc_var.get() or
             str(claude_meta.global_claude_home() / "settings.json")),
            ("Claude Desktop config", self._cd_var.get() or "(not set — see Settings tab)"),
            ("Claude Code subagents (Global)", str(claude_meta.global_agents_dir())),
            ("Claude Code sessions & memory root", str(claude_meta.global_claude_home() / "projects")),
        ]
        for label, path in others:
            exists = os.path.exists(path) if path and not path.startswith("(") else False
            self._claudemd_row(self._claudemd_scroll, r, label, path, exists)
            r += 1

    # ── Agents & Routines tab ────────────────────────────────────────────────

    def _build_agents_tab(self, parent):
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(16, 4))
        ctk.CTkLabel(top, text="Subagents, hooks & routines",
                    fg_color="transparent", text_color=TEXT,
                    font=("Segoe UI", 14, "bold")).pack(side="left")
        ctk.CTkButton(top, text="↻ Refresh", fg_color=SURF3, hover_color=ACCENT,
                     text_color=TEXT, width=90, height=28,
                     command=self._refresh_agents_tab).pack(side="right")

        info = ctk.CTkFrame(parent, fg_color=SURF2)
        info.pack(fill="x", padx=16, pady=(4, 8))
        ctk.CTkLabel(
            info, fg_color="transparent", text_color=DIM, justify="left", anchor="w",
            wraplength=760, font=("Segoe UI", 10),
            text=(
                "Live sessions and cloud Routines/Scheduled Tasks are managed inside "
                "the Claude Code Desktop app itself (Agent View + Routines) — they run "
                "on Anthropic's servers, not as local files, so ClAuSy can't list or "
                "edit them. What ClAuSy CAN show you below are the local, file-based "
                "building blocks: subagent definitions (.claude/agents/*.md) and hooks "
                "configured in settings.json, for every directory tracked on the "
                "Directories tab."
            )
        ).pack(fill="x", padx=14, pady=10)
        ctk.CTkButton(info, text="Open Claude Code Desktop docs ↗", fg_color=SURF3,
                     hover_color=ACCENT, text_color=TEXT, height=28,
                     command=lambda: webbrowser.open(DOCS_SCHEDULED_TASKS_URL)
                     ).pack(anchor="w", padx=14, pady=(0, 10))

        self._agents_scroll = ctk.CTkScrollableFrame(
            parent, fg_color=BG, scrollbar_fg_color=BG,
            scrollbar_button_color=SURF3, scrollbar_button_hover_color=ACCENT)
        self._agents_scroll.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self._agents_scroll.grid_columnconfigure(2, weight=1)

    def _agents_section_header(self, parent, row, text):
        ctk.CTkLabel(parent, text=text, fg_color="transparent", text_color=TEXT,
                    font=("Segoe UI", 11, "bold"), anchor="w"
                    ).grid(row=row, column=0, columnspan=4, sticky="w", pady=(14, 4))

    def _refresh_agents_tab(self):
        for w in self._agents_scroll.winfo_children():
            w.destroy()

        project_dirs = self._project_dirs()
        agents = claude_meta.find_agents(project_dirs)
        hooks  = claude_meta.find_hooks(project_dirs)

        r = 0
        self._agents_section_header(self._agents_scroll, r, f"Subagents ({len(agents)})")
        r += 1
        if not agents:
            ctk.CTkLabel(self._agents_scroll, text="No .claude/agents/*.md files found.",
                        fg_color="transparent", text_color=OFF_TXT, font=("Segoe UI", 9)
                        ).grid(row=r, column=0, columnspan=4, sticky="w")
            r += 1
        for a in agents:
            ctk.CTkLabel(self._agents_scroll, text=a["scope_label"], fg_color="transparent",
                        text_color=DIM, font=("Segoe UI", 9), width=90, anchor="w"
                        ).grid(row=r, column=0, sticky="w", pady=3)
            ctk.CTkLabel(self._agents_scroll, text=a["name"], fg_color="transparent",
                        text_color=TEXT, font=("Segoe UI", 9, "bold"), width=140, anchor="w"
                        ).grid(row=r, column=1, sticky="w", pady=3)
            ctk.CTkLabel(self._agents_scroll, text=a["description"] or "—", fg_color="transparent",
                        text_color=DIM, font=("Segoe UI", 9), anchor="w", justify="left"
                        ).grid(row=r, column=2, sticky="ew", padx=8, pady=3)
            ctk.CTkButton(self._agents_scroll, text="Open", width=60, height=24, fg_color=SURF3,
                         hover_color=ACCENT, text_color=TEXT,
                         command=lambda p=a["path"]: _open_path(p)
                         ).grid(row=r, column=3, pady=3)
            r += 1

        self._agents_section_header(self._agents_scroll, r, f"Hooks ({len(hooks)})")
        r += 1
        if not hooks:
            ctk.CTkLabel(self._agents_scroll, text="No hooks configured in any tracked settings.json.",
                        fg_color="transparent", text_color=OFF_TXT, font=("Segoe UI", 9)
                        ).grid(row=r, column=0, columnspan=4, sticky="w")
            r += 1
        for h in hooks:
            ctk.CTkLabel(self._agents_scroll, text=h["scope_label"], fg_color="transparent",
                        text_color=DIM, font=("Segoe UI", 9), width=90, anchor="w"
                        ).grid(row=r, column=0, sticky="w", pady=3)
            ctk.CTkLabel(self._agents_scroll, text=h["event"], fg_color="transparent",
                        text_color=TEXT, font=("Segoe UI", 9, "bold"), width=140, anchor="w"
                        ).grid(row=r, column=1, sticky="w", pady=3)
            ctk.CTkLabel(self._agents_scroll, text=h["path"], fg_color="transparent",
                        text_color=DIM, font=("Consolas", 9), anchor="w"
                        ).grid(row=r, column=2, sticky="ew", padx=8, pady=3)
            ctk.CTkButton(self._agents_scroll, text="Open", width=60, height=24, fg_color=SURF3,
                         hover_color=ACCENT, text_color=TEXT,
                         command=lambda p=h["path"]: _open_path(p)
                         ).grid(row=r, column=3, pady=3)
            r += 1

    # ── Explained tab ─────────────────────────────────────────────────────────

    def _build_explain_tab(self, parent):
        scroll = ctk.CTkScrollableFrame(
            parent, fg_color=BG, scrollbar_fg_color=BG,
            scrollbar_button_color=SURF3, scrollbar_button_hover_color=ACCENT)
        scroll.pack(fill="both", expand=True, padx=20, pady=16)

        def section(title, body):
            ctk.CTkLabel(scroll, text=title, fg_color="transparent", text_color=TEXT,
                        font=("Segoe UI", 12, "bold"), anchor="w", justify="left"
                        ).pack(fill="x", pady=(16, 2))
            ctk.CTkLabel(scroll, text=body, fg_color="transparent", text_color=DIM,
                        font=("Segoe UI", 10), anchor="w", justify="left", wraplength=820
                        ).pack(fill="x")

        section("Claude Code vs. Claude Desktop — what's the difference?",
                 "Claude Code is the CLI / IDE agent: it runs on your machine and reads "
                 "and writes files directly. Claude Desktop is the chat app; it has no "
                 "built-in filesystem access — it only reaches folders through an MCP "
                 "(Model Context Protocol) server you configure, in this case the "
                 "'filesystem' MCP server. That's why there are two separate config "
                 "files, and why the toggles below are grouped by product.")

        section(f"🔴 {COLUMN_NAMES['cc_allow']}",
                 COLUMN_HELP['cc_allow'] + " This is stored in settings.json under "
                 "permissions.allow. Use it for folders you fully trust Claude Code "
                 "with — nothing here prompts you before Claude Code reads or writes.")

        section(f"🟢 {COLUMN_NAMES['cc_additional']}",
                 COLUMN_HELP['cc_additional'] + " This is stored under "
                 "permissions.additionalDirectories. Individual actions inside these "
                 "folders may still ask for confirmation, depending on your Claude "
                 "Code permission mode — this toggle only grants reachability, not "
                 "automatic approval. Use it for folders Claude Code sometimes needs "
                 "beyond the project it's currently working in.")

        section(f"🔵 {COLUMN_NAMES['cd']}",
                 COLUMN_HELP['cd'] + " This is stored in claude_desktop_config.json, "
                 "as an argument to the '@modelcontextprotocol/server-filesystem' MCP "
                 "server. Toggling this on/off adds or removes the folder from that "
                 "server's directory list.")

        section("A folder can have any combination of the three",
                 "The three toggles are independent — a directory can be Allow-Listed "
                 "for Claude Code, reachable through Additional Directories, and open "
                 "to Claude Desktop, all at once, or none of them. There's no "
                 "hierarchy between them.")

        section("What 'Execute Changes' actually does",
                 "Nothing is written to disk while you toggle circles, add rows, or "
                 "delete rows — those only change ClAuSy's in-memory list. Clicking "
                 "'▶ Execute Changes' is the one moment the two real config files "
                 "(settings.json and claude_desktop_config.json) get rewritten, and "
                 "only the directory-related keys are touched — everything else in "
                 "those files (other settings, other permission rules, other MCP "
                 "servers) is preserved untouched. A .bak backup of each file is kept "
                 "alongside it before every write.")

        section("Undo",
                 "Up to 30 steps of toggle history, kept only for this open session. "
                 "It undoes in-app edits (toggles, add, delete) — it does not touch "
                 "the config files on disk, since those are only written on Execute.")

        section("Auto-Detect",
                 "Looks for settings.json in the standard Claude Code location, and "
                 "for claude_desktop_config.json in the standard Windows / macOS / "
                 "Windows Store install locations, and fills in the Settings tab if "
                 "found. It never overwrites a path you already typed with an empty "
                 "result.")
