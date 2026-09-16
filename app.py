"""ClAuSy — Claude Paths Manager UI."""
import copy
import os
import threading
import time
import urllib.parse
import webbrowser
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox
from pathlib import Path

import customtkinter as ctk

import claude_meta
import config_manager
import git_status
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
WARN    = "#e0a030"   # missing paths, too-long docs, RTL warnings, etc.

ICON_S  = 24
THUMB_W = 160
THUMB_H = 148
CPAD    = 14

DOCS_SCHEDULED_TASKS_URL = "https://code.claude.com/docs/en/desktop-scheduled-tasks"

REPORT_ISSUE_URL = (
    "https://github.com/MeirYaakovi/ClAuSy/issues/new"
    "?title=" + urllib.parse.quote("Confusing config or permission behavior")
    + "&body=" + urllib.parse.quote(
        "**What were you trying to do?**\n\n\n"
        "**What was confusing or unexpected?**\n\n\n"
        "**Steps to reproduce (if applicable):**\n\n\n"
        "(Optional) OS + ClAuSy version:\n"
    )
)

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
                 on_change=None, on_pre_change=None, is_overlap: bool = False,
                 on_remove=None, is_denied: bool = False, is_sensitive: bool = False,
                 on_show_permissions=None):
        self.entry               = entry
        self.on_change           = on_change
        self.on_pre_change       = on_pre_change
        self.on_remove           = on_remove
        self.on_show_permissions = on_show_permissions
        self._sel                = tk.BooleanVar(value=False)

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

        path = entry.get("path", "")
        has_permission = any(entry.get(k) for k in ("cc_allow", "cc_additional", "cd"))
        missing = bool(path) and has_permission and not os.path.isdir(path)
        warnings = []
        if missing:
            warnings.append("This directory has permissions granted, but no longer "
                             "exists on disk — those grants aren't doing anything.")
        if is_overlap:
            warnings.append("This directory overlaps with another tracked directory "
                             "(one is a parent folder of the other) — their "
                             "permissions may be redundant.")
        if is_denied:
            warnings.append("This path is in BOTH an allow rule and a deny rule in "
                             "settings.json — the deny rule always wins, so the allow "
                             "grant here is silently doing nothing.")
        if is_sensitive and has_permission:
            warnings.append("This looks like a sensitive OS or credential directory "
                             "(System32, /etc, ~/.ssh, ~/.aws, ...) — granting broad "
                             "tool access here is higher risk than a normal project "
                             "folder.")
        self.pl = ctk.CTkLabel(parent, text=(f"⚠ {path}" if warnings else path),
                               fg_color="transparent", text_color=(WARN if warnings else DIM),
                               font=("Consolas", 10), anchor="w", cursor="hand2")
        self.pl.bind("<Double-Button-1>", self._open_dir)
        self.pl.bind("<Button-3>", self._show_context_menu)
        if warnings:
            Tooltip(self.pl, "\n\n".join(warnings))

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

    def _copy_path(self):
        self.pl.clipboard_clear()
        self.pl.clipboard_append(self.entry.get("path", ""))

    def _show_context_menu(self, event):
        menu = tk.Menu(self.pl, tearoff=0, bg=SURF2, fg=TEXT,
                       activebackground=ACCENT, activeforeground="white",
                       bd=0)
        menu.add_command(label="Open", command=self._open_dir)
        menu.add_command(label="Copy path", command=self._copy_path)
        menu.add_command(label="Show effective permissions", command=self._show_permissions)
        menu.add_separator()
        menu.add_command(label="Remove", command=self._remove)
        menu.tk_popup(event.x_root, event.y_root)

    def _show_permissions(self):
        if self.on_show_permissions:
            self.on_show_permissions(self.entry.get("path", ""))

    def _remove(self):
        if self.on_remove:
            self.on_remove(self.entry.get("path", ""))

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
        self._legend_collapsed = False
        self._cc_fingerprint = None
        self._cd_fingerprint = None
        self._baseline_entries: list[dict] = []

        self._cc_var   = tk.StringVar()
        self._cd_var   = tk.StringVar()
        self._sort_var = tk.StringVar(value="name_asc")
        self._view_var = tk.StringVar(value="list")

        self._build_ui()
        self._load_settings()
        self._bind_shortcuts()

    def _bind_shortcuts(self):
        self.root.bind_all("<Control-z>", lambda e: self._undo())
        self.root.bind_all("<Control-f>", self._focus_search)
        self.root.bind_all("<Delete>", self._on_delete_key)

    def _focus_search(self, event=None):
        self.nb.set("Directories")
        self._search_entry.focus_set()
        return "break"

    def _on_delete_key(self, event=None):
        if isinstance(self.root.focus_get(), tk.Entry):
            return  # let normal text-field deletion happen
        if self.nb.get() == "Directories":
            self._delete_selected()

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
        self._tab_gitpush  = self.nb.add("Git Push")
        self._tab_explain  = self.nb.add("Explained")

        for t in (self._tab_settings, self._tab_dirs, self._tab_claudemd,
                  self._tab_agents, self._tab_gitpush, self._tab_explain):
            t.configure(fg_color=BG)

        self._build_settings_tab(self._tab_settings)
        self._build_dirs_tab(self._tab_dirs)
        self._build_claudemd_tab(self._tab_claudemd)
        self._build_agents_tab(self._tab_agents)
        self._build_gitpush_tab(self._tab_gitpush)
        self._build_explain_tab(self._tab_explain)

    def _on_tab_changed(self):
        name = self.nb.get()
        if name == "CLAUDE.md Map":
            self._refresh_claudemd_tab()
        elif name == "Agents & Routines":
            self._refresh_agents_tab()
        elif name == "Git Push":
            self._refresh_gitpush_tab()

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
            ctk.CTkButton(f, text="↩ Restore", fg_color=SURF3, hover_color=ACCENT,
                         text_color=TEXT, width=90, height=32,
                         command=lambda ct=cfg_type, v=var: self._restore_backup(ct, v)
                         ).grid(row=0, column=3, padx=(10, 0))

        row("Claude Code (CLI) settings file  —  controls the 🔴🟢 C toggles below  ( ~/.claude/settings.json )",
            self._cc_var, 0, "cc")
        row("Claude Desktop (app) config  —  controls the 🔵 D toggle below  ( claude_desktop_config.json )",
            self._cd_var, 2, "cd")

        self._cd_candidates_frame = ctk.CTkFrame(wrap, fg_color="transparent")
        self._cd_candidates_frame.grid(row=4, column=0, sticky="ew")

        btn_f = ctk.CTkFrame(wrap, fg_color="transparent")
        btn_f.grid(row=5, column=0, sticky="w", pady=24)

        def btn(parent, label, cmd, accent=False):
            c = ACCENT if accent else SURF3
            return ctk.CTkButton(parent, text=label, fg_color=c, hover_color=ACC2,
                                 text_color=TEXT, height=34, font=("Segoe UI", 10),
                                 command=cmd)

        btn(btn_f, "Auto-Detect",   self._auto_detect        ).pack(side="left", padx=(0, 10))
        btn(btn_f, "Save & Reload", self._save_and_reload,
            accent=True                                       ).pack(side="left", padx=(0, 10))
        btn(btn_f, "✔ Check",       self._validate_paths      ).pack(side="left", padx=(0, 10))
        btn(btn_f, "🔒 Deny Secrets", self._deny_secrets_preset).pack(side="left", padx=(0, 10))
        btn(btn_f, "🔍 Find Ignored Secrets",
            self._scan_gitignored_secrets                     ).pack(side="left", padx=(0, 10))
        btn(btn_f, "🐞 Report Confusing Config",
            lambda: webbrowser.open(REPORT_ISSUE_URL)          ).pack(side="left")

        self._status_lbl = ctk.CTkLabel(wrap, text="", fg_color="transparent",
                                        text_color=DIM, font=("Segoe UI", 10), anchor="w")
        self._status_lbl.grid(row=6, column=0, sticky="w", pady=(6, 0))

        self._yolo_banner = ctk.CTkLabel(
            wrap, text="", fg_color="#3a2a1a", text_color=WARN, corner_radius=6,
            font=("Segoe UI", 10, "bold"), anchor="w", justify="left", wraplength=760,
            padx=12, pady=10)
        self._yolo_banner.grid(row=7, column=0, sticky="ew", pady=(10, 0))
        self._yolo_banner.grid_remove()

        self._schema_banner = ctk.CTkLabel(
            wrap, text="", fg_color="#3a2a1a", text_color=WARN, corner_radius=6,
            font=("Segoe UI", 10, "bold"), anchor="w", justify="left", wraplength=760,
            padx=12, pady=10)
        self._schema_banner.grid(row=8, column=0, sticky="ew", pady=(10, 0))
        self._schema_banner.grid_remove()

        self._wildcard_banner = ctk.CTkLabel(
            wrap, text="", fg_color="#3a2a1a", text_color=WARN, corner_radius=6,
            font=("Segoe UI", 10, "bold"), anchor="w", justify="left", wraplength=760,
            padx=12, pady=10)
        self._wildcard_banner.grid(row=9, column=0, sticky="ew", pady=(10, 0))
        self._wildcard_banner.grid_remove()

        self._tracked_local_banner = ctk.CTkLabel(
            wrap, text="", fg_color="#3a2a1a", text_color=WARN, corner_radius=6,
            font=("Segoe UI", 10, "bold"), anchor="w", justify="left", wraplength=760,
            padx=12, pady=10)
        self._tracked_local_banner.grid(row=10, column=0, sticky="ew", pady=(10, 0))
        self._tracked_local_banner.grid_remove()

        self._zero_deny_banner = ctk.CTkLabel(
            wrap, text="", fg_color="#3a2a1a", text_color=WARN, corner_radius=6,
            font=("Segoe UI", 10, "bold"), anchor="w", justify="left", wraplength=760,
            padx=12, pady=10)
        self._zero_deny_banner.grid(row=11, column=0, sticky="ew", pady=(10, 0))
        self._zero_deny_banner.grid_remove()

        self._mcp_secrets_banner = ctk.CTkLabel(
            wrap, text="", fg_color="#3a2a1a", text_color=WARN, corner_radius=6,
            font=("Segoe UI", 10, "bold"), anchor="w", justify="left", wraplength=760,
            padx=12, pady=10)
        self._mcp_secrets_banner.grid(row=12, column=0, sticky="ew", pady=(10, 0))
        self._mcp_secrets_banner.grid_remove()

        self._precedence_banner = ctk.CTkLabel(
            wrap, text="", fg_color="#3a2a1a", text_color=WARN, corner_radius=6,
            font=("Segoe UI", 10, "bold"), anchor="w", justify="left", wraplength=760,
            padx=12, pady=10)
        self._precedence_banner.grid(row=13, column=0, sticky="ew", pady=(10, 0))
        self._precedence_banner.grid_remove()

        sim_f = ctk.CTkFrame(wrap, fg_color=SURF2, corner_radius=8)
        sim_f.grid(row=14, column=0, sticky="ew", pady=(14, 0))
        sim_inner = ctk.CTkFrame(sim_f, fg_color="transparent")
        sim_inner.pack(fill="x", padx=12, pady=10)
        ctk.CTkLabel(
            sim_inner, text="Permission rule simulator — test a command/path against "
                             "the current allow/deny rules",
            fg_color="transparent", text_color=TEXT, font=("Segoe UI", 10, "bold"),
            anchor="w").pack(anchor="w")
        sim_row = ctk.CTkFrame(sim_inner, fg_color="transparent")
        sim_row.pack(fill="x", pady=(6, 0))
        self._sim_var = tk.StringVar()
        sim_entry = ctk.CTkEntry(
            sim_row, textvariable=self._sim_var, fg_color=SURF3, text_color=TEXT,
            border_color=OFF, border_width=1, font=("Consolas", 10), height=30,
            placeholder_text="e.g. Bash(npm install) or an absolute path")
        sim_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        sim_entry.bind("<Return>", lambda e: self._run_permission_simulator())
        ctk.CTkButton(sim_row, text="Test", width=70, height=30, fg_color=ACCENT,
                     hover_color=ACC2, text_color="white",
                     command=self._run_permission_simulator).pack(side="left")
        self._sim_result_lbl = ctk.CTkLabel(
            sim_inner, text="", fg_color="transparent", text_color=DIM,
            font=("Segoe UI", 9), anchor="w", justify="left", wraplength=760)
        self._sim_result_lbl.pack(anchor="w", pady=(6, 0))

    def _refresh_cd_candidates(self):
        for w in self._cd_candidates_frame.winfo_children():
            w.destroy()
        candidates = config_manager.find_cd_config_candidates()
        if len(candidates) <= 1:
            return
        current = _norm(self._cd_var.get()) if self._cd_var.get().strip() else None
        ctk.CTkLabel(
            self._cd_candidates_frame,
            text=f"⚠ Found {len(candidates)} possible Claude Desktop config files on this "
                 "machine — make sure this is the one Claude Desktop actually uses. "
                 "(A documented Windows bug lets the app's own 'Edit Config' button "
                 "open the wrong one.)",
            fg_color="transparent", text_color=WARN, font=("Segoe UI", 9, "bold"),
            anchor="w", justify="left", wraplength=760
        ).pack(anchor="w", pady=(4, 4))
        for c in candidates:
            row_f = ctk.CTkFrame(self._cd_candidates_frame, fg_color="transparent")
            row_f.pack(fill="x", pady=2)
            is_current = _norm(c) == current
            ctk.CTkLabel(row_f, text=("✔ " if is_current else "  ") + c,
                        fg_color="transparent", text_color=(CC_G if is_current else DIM),
                        font=("Consolas", 9), anchor="w").pack(side="left", fill="x", expand=True)
            if not is_current:
                ctk.CTkButton(row_f, text="Use this", width=80, height=24, fg_color=SURF3,
                             hover_color=ACCENT, text_color=TEXT,
                             command=lambda p=c: self._use_cd_candidate(p)
                             ).pack(side="right")

    def _use_cd_candidate(self, path: str):
        self._cd_var.set(path)
        self._validate_paths(silent=True)

    def _check_permission_mode(self):
        mode = config_manager.get_permission_mode(self._cc_var.get())
        is_yolo = mode == "bypassPermissions"
        cc_path = self._cc_var.get().strip()
        since_text = ""
        if cc_path:
            data = storage.load()
            yolo_since = storage.note_yolo_state(
                data.get("yolo_since", {}), cc_path, is_yolo, datetime.now().isoformat())
            data["yolo_since"] = yolo_since
            storage.save(data)
            since = yolo_since.get(cc_path)
            if is_yolo and since:
                try:
                    days = (datetime.now() - datetime.fromisoformat(since)).days
                    since_text = (f" It's been enabled for {days} day"
                                  f"{'s' if days != 1 else ''} (since {since[:10]}).")
                except ValueError:
                    pass
        if is_yolo:
            self._yolo_banner.configure(
                text="⚠ Claude Code's default permission mode is 'bypassPermissions' "
                     "(YOLO mode) — every action is auto-approved with no prompts at "
                     "all. This mode has caused real data loss (e.g. an unconfirmed "
                     "rm -rf wiping a user's home directory). Consider switching to "
                     "'default' or 'acceptEdits' in settings.json unless you fully "
                     "trust every command Claude Code might run here." + since_text)
            self._yolo_banner.grid()
        else:
            self._yolo_banner.grid_remove()

    def _check_unknown_settings_keys(self):
        cc = self._cc_var.get().strip()
        if not cc:
            self._schema_banner.grid_remove()
            return
        try:
            unknown = config_manager.find_unknown_keys(cc)
        except config_manager.ConfigError:
            self._schema_banner.grid_remove()
            return
        if unknown:
            self._schema_banner.configure(
                text=f"⚠ settings.json has {len(unknown)} top-level key(s) ClAuSy "
                     f"doesn't recognize — possibly a typo or a renamed/removed "
                     f"setting doing nothing: {', '.join(unknown)}")
            self._schema_banner.grid()
        else:
            self._schema_banner.grid_remove()

    def _check_unsafe_bash_wildcards(self):
        cc = self._cc_var.get().strip()
        if not cc:
            self._wildcard_banner.grid_remove()
            return
        flagged = config_manager.find_unsafe_bash_wildcards(cc)
        if flagged:
            self._wildcard_banner.configure(
                text=f"⚠ {len(flagged)} Bash allow rule(s) use a bare '*' wildcard "
                     f"instead of the safer ':*' prefix form — '*' matches any "
                     f"character, including shell operators like ; && | , so a "
                     f"command could slip through unintended: {', '.join(flagged)}")
            self._wildcard_banner.grid()
        else:
            self._wildcard_banner.grid_remove()

    def _check_tracked_settings_local(self):
        flagged = git_status.find_tracked_settings_local(self._project_dirs())
        if flagged:
            self._tracked_local_banner.configure(
                text=f"⚠ {len(flagged)} settings.local.json file(s) are committed to git "
                     f"instead of gitignored — that file is meant for personal/local-only "
                     f"overrides: {', '.join(flagged)}")
            self._tracked_local_banner.grid()
        else:
            self._tracked_local_banner.grid_remove()

    def _check_zero_deny_bypass_combo(self):
        cc = self._cc_var.get().strip()
        if cc and config_manager.is_zero_deny_bypass_combo(cc):
            self._zero_deny_banner.configure(
                text="⚠ bypassPermissions (YOLO mode) is on AND the deny list is empty "
                     "— there's no permission block at all right now, not even one that "
                     "would normally still stop reads/writes to specific denied paths. "
                     "Consider adding at least the 'Deny Secrets' preset above.")
            self._zero_deny_banner.grid()
        else:
            self._zero_deny_banner.grid_remove()

    def _check_mcp_exposed_secrets(self):
        cd = self._cd_var.get().strip()
        flagged = config_manager.find_mcp_exposed_secrets(cd) if cd else []
        if flagged:
            names = ", ".join(f"{f['server']}.{f['env_key']}" for f in flagged)
            self._mcp_secrets_banner.configure(
                text=f"⚠ {len(flagged)} MCP server env value(s) look like hardcoded "
                     f"secrets instead of ${{VAR}} references — {names}. If this file "
                     f"is ever committed to git, those values leak.")
            self._mcp_secrets_banner.grid()
        else:
            self._mcp_secrets_banner.grid_remove()

    def _check_bypass_precedence_blindspots(self):
        cc = self._cc_var.get().strip()
        flagged = config_manager.find_bypass_precedence_blindspots(
            cc, self._project_dirs()) if cc else []
        if flagged:
            names = ", ".join(os.path.basename(p) or p for p in flagged)
            self._precedence_banner.configure(
                text=f"⚠ bypassPermissions (YOLO mode) is set globally, but "
                     f"{len(flagged)} tracked project(s) have their own "
                     f".claude/settings.json permissions block, which takes "
                     f"precedence over the global one — bypass mode likely does NOT "
                     f"apply inside: {names}.")
            self._precedence_banner.grid()
        else:
            self._precedence_banner.grid_remove()

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

        self._search_var = tk.StringVar()
        self._search_entry = ctk.CTkEntry(
            inner, textvariable=self._search_var, placeholder_text="🔍 Search label or path…",
            fg_color=SURF, text_color=TEXT, border_color=OFF, border_width=1,
            font=("Segoe UI", 10), height=30, width=220)
        self._search_entry.pack(side="right")
        self._search_var.trace_add("write", lambda *_: self._on_search_changed())

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

        legend_head = ctk.CTkFrame(legend, fg_color="transparent")
        legend_head.pack(fill="x", padx=12, pady=(4, 0))
        self._legend_toggle_btn = ctk.CTkButton(
            legend_head, text="▾ Legend", fg_color="transparent", hover_color=SURF3,
            text_color=DIM, anchor="w", width=90, height=20, font=("Segoe UI", 9, "bold"),
            command=self._toggle_legend)
        self._legend_toggle_btn.pack(side="left")

        self._legend_inner = ctk.CTkFrame(legend, fg_color="transparent")
        self._legend_inner.pack(fill="x", padx=12, pady=5)
        legend_inner = self._legend_inner

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

    def _toggle_legend(self):
        self._apply_legend_state(not self._legend_collapsed)
        data = storage.load()
        data["legend_collapsed"] = self._legend_collapsed
        storage.save(data)

    def _apply_legend_state(self, collapsed: bool):
        self._legend_collapsed = collapsed
        if collapsed:
            self._legend_inner.pack_forget()
            self._legend_toggle_btn.configure(text="▸ Legend")
        else:
            self._legend_inner.pack(fill="x", padx=12, pady=5)
            self._legend_toggle_btn.configure(text="▾ Legend")

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
        self._apply_legend_state(data.get("legend_collapsed", False))
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

    def _deny_secrets_preset(self):
        cc = self._cc_var.get().strip()
        if not cc:
            messagebox.showerror("ClAuSy", "No Claude Code settings.json path set.\n"
                                           "Go to Settings and set/Auto-Detect it first.")
            return
        patterns = config_manager.DEFAULT_DENY_SECRET_PATTERNS
        preview = "\n".join(f"  • {p}" for p in patterns)
        if not messagebox.askyesno(
                "ClAuSy — Deny Secrets Preset",
                "Add deny rules for common secret files (.env, *.pem, *.key, "
                "id_rsa, credentials.json, .aws/, .ssh/) to settings.json?\n\n"
                f"{preview}\n\n"
                "Existing deny rules are kept; only missing ones are added."):
            return
        try:
            added = config_manager.add_deny_patterns(cc, patterns)
        except config_manager.ConfigError as e:
            messagebox.showerror("ClAuSy", f"Could not update settings.json:\n\n{e}")
            return
        if added:
            self._set_status(f"Added {added} deny rule(s) for secret files.", CC_G)
        else:
            self._set_status("All secret-file deny rules were already present.", DIM)

    def _run_permission_simulator(self):
        target = self._sim_var.get().strip()
        if not target:
            return
        allow, deny = config_manager.get_permission_rules(self._cc_var.get())
        result = config_manager.simulate_permission(allow, deny, target)
        verdict = result["verdict"]
        color = {"deny": CC_R, "allow": CC_G, "ask": WARN}[verdict]
        if verdict == "deny":
            detail = f"Matched deny rule: {result['deny_match']}"
        elif verdict == "allow":
            detail = f"Matched allow rule: {result['allow_match']}"
        else:
            detail = "No allow or deny rule matches — Claude Code will ask for permission."
        self._sim_result_lbl.configure(
            text=f"Verdict: {verdict.upper()} — {detail}", text_color=color)

    def _show_effective_permissions(self, path: str):
        if not path:
            return
        eff = config_manager.get_effective_permissions(
            path, self._cc_var.get(), self._cd_var.get())
        lines = [
            f"Directory: {path}\n",
            f"Global settings.json — allow: {'yes' if eff['global_allow'] else 'no'}, "
            f"additionalDirectories: {'yes' if eff['global_additional'] else 'no'}, "
            f"deny: {'yes' if eff['global_deny'] else 'no'}",
            f"Project .claude/settings.json (only applies if this IS a project "
            f"root) — allow: {'yes' if eff['project_allow'] else 'no'}, "
            f"deny: {'yes' if eff['project_deny'] else 'no'}",
            f"Claude Desktop filesystem MCP server — allow: "
            f"{'yes' if eff['cd_allow'] else 'no'}",
            "",
            f"Effective verdict: {eff['verdict'].upper()}"
            + (" (a deny rule wins over any allow)" if eff["verdict"] == "deny" else ""),
        ]
        messagebox.showinfo("ClAuSy — Effective Permissions", "\n".join(lines))

    def _scan_gitignored_secrets(self):
        found = []
        for d in self._project_dirs():
            found.extend(config_manager.find_gitignored_secrets(d))
        if not found:
            messagebox.showinfo(
                "ClAuSy", "No gitignored secret-looking files found under tracked "
                          "directories.")
            return
        preview = "\n".join(f"  • {p}" for p in found[:20])
        more = f"\n  …and {len(found) - 20} more" if len(found) > 20 else ""
        messagebox.showwarning(
            "ClAuSy — Gitignored secrets found",
            f"Found {len(found)} file(s) matching common secret patterns that are "
            f"excluded from git via .gitignore — deliberately kept out of version "
            f"control, but still readable by Claude if the containing directory is "
            f"granted access:\n\n{preview}{more}")

    def _restore_backup(self, cfg_type: str, var: tk.StringVar):
        path = var.get().strip()
        label = "Claude Code settings" if cfg_type == "cc" else "Claude Desktop config"
        if not path:
            messagebox.showerror("ClAuSy", f"No path set for {label}.")
            return
        backups = config_manager.list_backups(path)
        if not backups:
            messagebox.showinfo("ClAuSy", f"No backups found yet for {label}.")
            return
        if self._pending:
            if not messagebox.askyesno(
                    "ClAuSy",
                    "You have directory changes on the Directories tab that were "
                    "never written (Execute Changes was never pressed).\n\n"
                    "Restoring now will discard them and reload from disk. Continue?"):
                return
        if not messagebox.askyesno(
                "ClAuSy — Restore Backup",
                f"Restore {label} from its most recent backup "
                f"({backups[-1].name})?\n\n"
                "The current file content is itself backed up first, so this "
                "can be undone by restoring again."):
            return
        config_manager.restore_last_backup(path)
        self._reload_entries()
        self._validate_paths(silent=True)
        self._set_status(f"Restored {label} from backup.", CC_G)

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
        self._check_permission_mode()
        self._check_unknown_settings_keys()
        self._check_unsafe_bash_wildcards()
        self._check_tracked_settings_local()
        self._check_zero_deny_bypass_combo()
        self._check_mcp_exposed_secrets()
        self._check_bypass_precedence_blindspots()
        self._refresh_cd_candidates()

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
        self._capture_fingerprints()
        self._baseline_entries = _snap(self._entries)
        self._apply_sort(refresh=True)

    def _capture_fingerprints(self):
        """Snapshot cc/cd file state as of the last successful read, so
        Execute can detect if either file changed on disk since then."""
        self._cc_fingerprint = config_manager.file_fingerprint(self._cc_var.get())
        self._cd_fingerprint = config_manager.file_fingerprint(self._cd_var.get())
        self._cc_rule_counts = config_manager.count_non_path_rules(self._cc_var.get())

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

    def _visible_entries(self) -> list:
        q = self._search_var.get().strip().lower()
        if not q:
            return self._entries
        return [e for e in self._entries
                if q in e.get("label", "").lower() or q in e.get("path", "").lower()]

    def _on_search_changed(self):
        self._refresh_list()
        if self._view_var.get() == "thumb":
            self._draw_thumbs()

    def _refresh_list(self):
        for w in self._sf.winfo_children():
            w.destroy()
        self._rows.clear()
        overlaps = config_manager.find_overlapping_paths(
            [e.get("path", "") for e in self._entries])
        denied = config_manager.find_allow_deny_conflicts(self._cc_var.get())
        for i, entry in enumerate(self._visible_entries()):
            r = DirectoryRow(self._sf, entry, i,
                             on_change=lambda: setattr(self, "_pending", True),
                             on_pre_change=self._push_undo,
                             is_overlap=_norm(entry.get("path", "")) in overlaps,
                             is_denied=_norm(entry.get("path", "")) in denied,
                             is_sensitive=config_manager.is_sensitive_system_path(
                                 entry.get("path", "")),
                             on_remove=self._remove_single_path,
                             on_show_permissions=self._show_effective_permissions)
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

    def _remove_single_path(self, path: str):
        entry = next((e for e in self._entries if e["path"] == path), None)
        if entry is None:
            return
        label = entry.get("label") or path
        if not messagebox.askyesno(
                "ClAuSy", f"Remove '{label}' from the list?\n"
                          "(Config files are not changed until Execute.)"):
            return
        self._push_undo()
        self._entries = [e for e in self._entries if e["path"] != path]
        self._refresh_list()
        if self._view_var.get() == "thumb":
            self._draw_thumbs()
        self._pending = True

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
        visible = self._visible_entries()

        for i, entry in enumerate(visible):
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

        total_rows = (len(visible) + cols - 1) // cols if visible else 1
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

    def _check_external_changes(self) -> bool:
        """Returns True if it's safe to write (nothing changed on disk since
        ClAuSy last read it, or the user confirmed overwriting anyway)."""
        changed = []
        if self._cc_var.get() and \
                config_manager.file_fingerprint(self._cc_var.get()) != self._cc_fingerprint:
            changed.append("Claude Code settings.json")
        if self._cd_var.get() and \
                config_manager.file_fingerprint(self._cd_var.get()) != self._cd_fingerprint:
            changed.append("Claude Desktop config")
        if not changed:
            return True

        dropped_warning = ""
        current_counts = config_manager.count_non_path_rules(self._cc_var.get())
        dropped = {k: (old, current_counts[k]) for k, old in self._cc_rule_counts.items()
                   if current_counts[k] < old}
        if dropped:
            parts = [f"{k}: {old} → {new}" for k, (old, new) in dropped.items()]
            dropped_warning = (
                "\n\n⚠ Some Bash/Read/Edit-style rules (not bare directories) "
                "disappeared from settings.json since ClAuSy last read it — "
                f"{', '.join(parts)}. Writing now would permanently lose them, "
                "since ClAuSy only manages directory entries, not these rules.")

        return messagebox.askyesno(
            "ClAuSy — File Changed Externally",
            f"{' and '.join(changed)} changed on disk since ClAuSy last read "
            "it — possibly edited by Claude Code itself, another program, or "
            "another instance of ClAuSy.\n\n"
            "Writing now will overwrite those external changes with ClAuSy's "
            "in-memory version.\n\nOverwrite anyway? (Choose No, then use "
            "Save & Reload first to pick up the external changes instead.)" + dropped_warning)

    def _confirm_changes_summary(self, summary: dict) -> bool:
        lines = []

        def _section(title, paths):
            lines.append(f"{title} ({len(paths)}):")
            lines.extend(f"    {p}" for p in paths[:10])
            if len(paths) > 10:
                lines.append(f"    …and {len(paths) - 10} more")

        if summary["added"]:
            _section("+ New directories", summary["added"])
        if summary["removed"]:
            _section("− Removed directories", summary["removed"])
        if summary["changed"]:
            lines.append(f"~ Permission changes ({len(summary['changed'])}):")
            for path, diffs in list(summary["changed"].items())[:10]:
                parts = [f"{COLUMN_NAMES.get(k, k)} → {'ON' if new else 'off'}"
                         for k, (old, new) in diffs.items()]
                lines.append(f"    {path}: " + ", ".join(parts))
            if len(summary["changed"]) > 10:
                lines.append(f"    …and {len(summary['changed']) - 10} more")

        return messagebox.askyesno(
            "ClAuSy — Review Changes",
            "About to write these changes to the config file(s):\n\n" +
            "\n".join(lines) + "\n\nProceed?")

    def _execute_changes(self):
        for r in self._rows:
            r.sync()

        cc = self._cc_var.get()
        cd = self._cd_var.get()
        if not cc and not cd:
            messagebox.showerror("ClAuSy",
                                 "No config paths set.\nGo to Settings tab first.")
            return
        if not self._check_external_changes():
            return

        summary = config_manager.summarize_changes(self._baseline_entries, self._entries)
        if (summary["added"] or summary["removed"] or summary["changed"]) \
                and not self._confirm_changes_summary(summary):
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
            self._capture_fingerprints()
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
        head_f = ctk.CTkFrame(text_f, fg_color="transparent")
        head_f.pack(anchor="w", fill="x")
        ctk.CTkLabel(head_f, text=scope_label, fg_color="transparent", text_color=TEXT,
                    font=("Segoe UI", 10, "bold"), anchor="w").pack(side="left")
        if exists and allow_create:
            rtl = claude_meta.check_rtl_first_line(path)
            if rtl and not rtl["ok"]:
                warn = ctk.CTkLabel(
                    head_f, text="⚠ RTL", fg_color="transparent", text_color=WARN,
                    font=("Segoe UI", 9, "bold"))
                warn.pack(side="left", padx=(8, 0))
                Tooltip(warn, "This file has Hebrew text, but the first line isn't "
                              "Hebrew — Obsidian won't auto-detect RTL for it.\n"
                              "Add a Hebrew word to line 1 to fix this.")

            stats = claude_meta.claude_md_stats(path)
            if stats:
                count_color = WARN if stats["too_long"] else OFF_TXT
                count_lbl = ctk.CTkLabel(
                    head_f, text=f"{stats['lines']} lines", fg_color="transparent",
                    text_color=count_color, font=("Segoe UI", 9))
                count_lbl.pack(side="left", padx=(8, 0))
                if stats["too_long"]:
                    Tooltip(count_lbl,
                            f"{stats['lines']} lines / {stats['words']} words — Claude's "
                            "attention on CLAUDE.md drops off sharply past roughly "
                            f"{claude_meta.CLAUDE_MD_LINE_WARN_THRESHOLD} lines. "
                            "Consider trimming it.")
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

        rules_files = claude_meta.find_rules_files(self._project_dirs())
        if rules_files:
            sep_r = ctk.CTkFrame(self._claudemd_scroll, fg_color=OFF, height=1)
            sep_r.grid(row=r, column=0, columnspan=3, sticky="ew", pady=14)
            r += 1
            ctk.CTkLabel(
                self._claudemd_scroll,
                text=".claude/rules/*.md — a separate instruction source Claude Code "
                     "also loads for these projects",
                fg_color="transparent", text_color=DIM, font=("Segoe UI", 9),
                anchor="w").grid(row=r, column=0, columnspan=3, sticky="w", pady=(0, 4))
            r += 1
            for rf in rules_files:
                self._claudemd_row(self._claudemd_scroll, r, rf["label"], rf["path"], True)
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
        agent_issues = claude_meta.find_agent_description_issues(agents)
        for path, msgs in claude_meta.find_subagent_claude_md_blind_spots(agents).items():
            agent_issues.setdefault(path, []).extend(msgs)
        hook_issues: dict = {}
        for d in claude_meta.find_dangerous_hook_commands(hooks):
            hook_issues.setdefault((d["path"], d["event"]), []).append(
                f"Command looks dangerous — {d['reason']}: {d['command']}")
        for lr in claude_meta.find_hook_loop_risks(hooks):
            hook_issues.setdefault((lr["path"], lr["event"]), []).append(
                "This hook re-invokes 'claude', which risks an infinite loop or "
                f"runaway logs if it fires on every session/prompt: {lr['command']}")
        for wi in claude_meta.find_windows_incompatible_hooks(hooks):
            hook_issues.setdefault((wi["path"], wi["event"]), []).append(
                f"May silently fail on native Windows — {wi['reason']}: {wi['command']}")
        for br in claude_meta.find_hook_blocking_risks(hooks):
            hook_issues.setdefault((br["path"], br["event"]), []).append(
                f"May hang the whole session — {br['reason']}: {br['command']}")

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
            issues = agent_issues.get(a["path"])
            name_f = ctk.CTkFrame(self._agents_scroll, fg_color="transparent", width=140)
            name_f.grid(row=r, column=1, sticky="w", pady=3)
            ctk.CTkLabel(name_f, text=a["name"], fg_color="transparent",
                        text_color=TEXT, font=("Segoe UI", 9, "bold"), anchor="w"
                        ).pack(side="left")
            if issues:
                warn = ctk.CTkLabel(name_f, text=" ⚠", fg_color="transparent",
                                    text_color=WARN, font=("Segoe UI", 9, "bold"))
                warn.pack(side="left")
                Tooltip(warn, "\n".join(issues))
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
            event_f = ctk.CTkFrame(self._agents_scroll, fg_color="transparent", width=140)
            event_f.grid(row=r, column=1, sticky="w", pady=3)
            ctk.CTkLabel(event_f, text=h["event"], fg_color="transparent",
                        text_color=TEXT, font=("Segoe UI", 9, "bold"), anchor="w"
                        ).pack(side="left")
            h_issues = hook_issues.get((h["path"], h["event"]))
            if h_issues:
                warn = ctk.CTkLabel(event_f, text=" ⚠", fg_color="transparent",
                                    text_color=WARN, font=("Segoe UI", 9, "bold"))
                warn.pack(side="left")
                Tooltip(warn, "\n".join(h_issues))
            ctk.CTkLabel(self._agents_scroll, text=h["path"], fg_color="transparent",
                        text_color=DIM, font=("Consolas", 9), anchor="w"
                        ).grid(row=r, column=2, sticky="ew", padx=8, pady=3)
            ctk.CTkButton(self._agents_scroll, text="Open", width=60, height=24, fg_color=SURF3,
                         hover_color=ACCENT, text_color=TEXT,
                         command=lambda p=h["path"]: _open_path(p)
                         ).grid(row=r, column=3, pady=3)
            r += 1

    # ── Git Push tab ──────────────────────────────────────────────────────────

    def _build_gitpush_tab(self, parent):
        self._git_repos: list = []
        self._git_vars: dict = {}      # path -> tk.BooleanVar
        self._git_row_ui: dict = {}    # path -> {"push_btn", "status_lbl"}
        self._git_busy = False

        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(16, 4))
        ctk.CTkLabel(top, text="Repos with commits waiting to be pushed",
                    fg_color="transparent", text_color=TEXT,
                    font=("Segoe UI", 14, "bold")).pack(side="left")
        self._git_refresh_btn = ctk.CTkButton(
            top, text="↻ Refresh", fg_color=SURF3, hover_color=ACCENT,
            text_color=TEXT, width=90, height=28, command=self._refresh_gitpush_tab)
        self._git_refresh_btn.pack(side="right")

        self._git_summary_lbl = ctk.CTkLabel(
            top, text="", fg_color="transparent", text_color=DIM, font=("Segoe UI", 10))
        self._git_summary_lbl.pack(side="right", padx=(0, 16))

        toolbar = ctk.CTkFrame(parent, fg_color=SURF2, corner_radius=0)
        toolbar.pack(fill="x", padx=16, pady=(4, 0))
        tinner = ctk.CTkFrame(toolbar, fg_color="transparent")
        tinner.pack(fill="x", padx=8, pady=6)

        def tbtn(text, cmd):
            b = ctk.CTkButton(tinner, text=text, fg_color=SURF3, hover_color=ACCENT,
                              text_color=TEXT, height=28, font=("Segoe UI", 10),
                              command=cmd)
            b.pack(side="left", padx=4)
            return b

        tbtn("☑ Select Unpushed", lambda: self._git_select("unpushed"))
        tbtn("☐ Select None", lambda: self._git_select("none"))

        self._git_scroll = ctk.CTkScrollableFrame(
            parent, fg_color=BG, scrollbar_fg_color=BG,
            scrollbar_button_color=SURF3, scrollbar_button_hover_color=ACCENT)
        self._git_scroll.pack(fill="both", expand=True, padx=16, pady=(8, 0))
        self._git_scroll.grid_columnconfigure(2, weight=1)

        footer = ctk.CTkFrame(parent, fg_color=SURF2, corner_radius=0)
        footer.pack(fill="x", side="bottom", padx=0, pady=0)
        footer_inner = ctk.CTkFrame(footer, fg_color="transparent")
        footer_inner.pack(fill="x", padx=14, pady=8)

        self._git_push_btn = ctk.CTkButton(
            footer_inner, text="⬆ Push Selected", fg_color=ACCENT, hover_color=ACC2,
            text_color="white", height=34, font=("Segoe UI", 11, "bold"),
            command=self._push_selected)
        self._git_push_btn.pack(side="left")

        self._git_prog_bar = ctk.CTkProgressBar(footer_inner, progress_color=ACCENT,
                                                 fg_color=SURF3)
        self._git_prog_bar.set(0)
        self._git_prog_bar.pack(side="left", fill="x", expand=True, padx=14)

        self._git_status_lbl = ctk.CTkLabel(footer_inner, text="", fg_color="transparent",
                                            text_color=DIM, font=("Segoe UI", 10), width=220,
                                            anchor="e")
        self._git_status_lbl.pack(side="right")

        ctk.CTkLabel(
            parent, fg_color="transparent", text_color=OFF_TXT, anchor="w",
            font=("Segoe UI", 9),
            text=("Scans the immediate subfolders of every tracked directory "
                  "(Directories tab) for git repos with an upstream remote.")
        ).pack(fill="x", padx=20, pady=(2, 10), side="bottom")

    def _git_select(self, mode: str):
        for repo in self._git_repos:
            if mode == "none":
                self._git_vars[repo["path"]].set(False)
            elif mode == "unpushed":
                self._git_vars[repo["path"]].set(repo["ahead"] > 0 and not repo["error"])

    def _refresh_gitpush_tab(self):
        if self._git_busy:
            return
        self._set_git_busy(True, "Scanning…")
        for w in self._git_scroll.winfo_children():
            w.destroy()
        self._git_row_ui = {}
        ctk.CTkLabel(self._git_scroll, text="Scanning repos…", fg_color="transparent",
                    text_color=DIM, font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w")

        project_dirs = self._project_dirs()

        def worker():
            repos = git_status.scan(project_dirs)
            self.root.after(0, self._on_gitpush_scanned, repos)

        threading.Thread(target=worker, daemon=True).start()

    def _on_gitpush_scanned(self, repos: list):
        data = storage.load()
        known = data.get("git_known_branches", {})
        last_heads = data.get("git_last_head", {})
        for r in repos:
            r["history_rewritten"] = False
            if r.get("error") or not r.get("branch"):
                r["new_branch"] = False
                continue
            is_new, known = storage.note_branch_seen(known, r["path"], r["branch"])
            r["new_branch"] = is_new

            previous_head = storage.note_head_seen(last_heads, r["path"], r.get("head_sha", ""))
            if previous_head and previous_head != r.get("head_sha") and r.get("head_sha"):
                ancestor = git_status.is_ancestor(r["path"], previous_head, r["head_sha"])
                if ancestor is False:
                    r["history_rewritten"] = True
        data["git_known_branches"] = known
        data["git_last_head"] = last_heads
        storage.save(data)

        self._git_repos = repos
        self._git_vars = {r["path"]: tk.BooleanVar(value=False) for r in repos}
        self._set_git_busy(False, "")
        self._render_gitpush_rows()

    def _set_git_busy(self, busy: bool, status: str):
        self._git_busy = busy
        state = "disabled" if busy else "normal"
        self._git_refresh_btn.configure(state=state)
        self._git_push_btn.configure(state=state)
        self._git_status_lbl.configure(text=status)

    def _render_gitpush_rows(self):
        for w in self._git_scroll.winfo_children():
            w.destroy()
        self._git_row_ui = {}

        unpushed = [r for r in self._git_repos if r["ahead"] > 0]
        dirty = [r for r in self._git_repos if r["dirty_count"] > 0]
        self._git_summary_lbl.configure(
            text=f"{len(self._git_repos)} repos · {len(unpushed)} with unpushed commits "
                 f"· {len(dirty)} with uncommitted changes")

        if not self._git_repos:
            ctk.CTkLabel(self._git_scroll, text="No git repos found under the tracked "
                        "directories (see Directories tab).", fg_color="transparent",
                        text_color=OFF_TXT, font=("Segoe UI", 10)
                        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=8)
            return

        for r, repo in enumerate(self._git_repos):
            self._gitpush_row(self._git_scroll, r * 2, repo)

    def _gitpush_row(self, parent, row, repo):
        path = repo["path"]

        cb = ctk.CTkCheckBox(parent, text="", variable=self._git_vars[path], width=20,
                             fg_color=ACCENT, hover_color=ACC2, checkmark_color="white")
        cb.grid(row=row, column=0, padx=(4, 8), pady=8, sticky="n")
        if repo["error"] or repo["ahead"] == 0:
            cb.configure(state="disabled")

        name_f = ctk.CTkFrame(parent, fg_color="transparent")
        name_f.grid(row=row, column=1, sticky="nw", pady=8, padx=(0, 8))
        ctk.CTkLabel(name_f, text=repo["name"], fg_color="transparent", text_color=TEXT,
                    font=("Segoe UI", 11, "bold"), anchor="w").pack(anchor="w")
        ctk.CTkLabel(name_f, text=repo["branch"] or "—", fg_color="transparent",
                    text_color=DIM, font=("Consolas", 9), anchor="w").pack(anchor="w")

        mid_f = ctk.CTkFrame(parent, fg_color="transparent")
        mid_f.grid(row=row, column=2, sticky="ew", pady=8, padx=(0, 8))

        badges = ctk.CTkFrame(mid_f, fg_color="transparent")
        badges.pack(anchor="w", fill="x")

        if repo["error"]:
            ctk.CTkLabel(badges, text=f"⚠ {repo['error']}", fg_color="transparent",
                        text_color=CC_R, font=("Segoe UI", 9, "bold")).pack(side="left")
        else:
            if not repo["has_upstream"]:
                self._git_badge(badges, "no upstream", OFF_TXT)
            elif repo["ahead"] > 0:
                self._git_badge(badges, f"⬆ {repo['ahead']} unpushed", CC_R)
            else:
                self._git_badge(badges, "✔ pushed", CC_G)
            if repo["dirty_count"] > 0:
                self._git_badge(badges, f"● {repo['dirty_count']} uncommitted", WARN)
            if repo.get("direct_on_main"):
                self._git_badge(badges, "⚠ direct on main", WARN)
            if repo.get("behind", 0) > 0:
                self._git_badge(badges, f"⇕ {repo['behind']} behind — push may be rejected", WARN)
            if repo.get("new_branch"):
                self._git_badge(badges, "🌿 new branch", WARN)
            if repo.get("history_rewritten"):
                self._git_badge(badges, "⚠ history rewritten (amend/rebase?)", WARN)

        if repo["unpushed_commits"]:
            latest = repo["unpushed_commits"][0]
            commit_txt = f"{latest['hash']}  {latest['subject']}"
            if len(repo["unpushed_commits"]) > 1:
                commit_txt += f"   (+{len(repo['unpushed_commits']) - 1} more)"
            lbl = ctk.CTkLabel(mid_f, text=commit_txt, fg_color="transparent", text_color=DIM,
                              font=("Consolas", 9), anchor="w", justify="left", wraplength=420)
            lbl.pack(anchor="w", pady=(4, 0))
            if len(repo["unpushed_commits"]) > 1:
                full = "\n".join(f"{c['hash']}  {c['subject']}  ({c['date']})"
                                 for c in repo["unpushed_commits"])
                Tooltip(lbl, full)

        status_lbl = ctk.CTkLabel(mid_f, text="", fg_color="transparent",
                                  text_color=DIM, font=("Segoe UI", 9), anchor="w")
        status_lbl.pack(anchor="w", pady=(4, 0))

        btn_f = ctk.CTkFrame(parent, fg_color="transparent")
        btn_f.grid(row=row, column=3, padx=(8, 4), pady=8, sticky="ne")
        ctk.CTkButton(btn_f, text="Open", width=64, height=26, fg_color=SURF3,
                     hover_color=ACCENT, text_color=TEXT,
                     command=lambda p=path: _open_path(p)).pack(side="left", padx=2)
        can_push = not repo["error"] and repo["has_upstream"] and repo["ahead"] > 0
        push_btn = ctk.CTkButton(
            btn_f, text="Push", width=64, height=26,
            fg_color=(ACCENT if can_push else SURF3),
            hover_color=(ACC2 if can_push else SURF3),
            text_color=(TEXT if can_push else OFF_TXT),
            state=("normal" if can_push else "disabled"),
            command=lambda p=path, n=repo["name"]: self._push_paths([p], [n]))
        push_btn.pack(side="left", padx=2)

        self._git_row_ui[path] = {"push_btn": push_btn, "status_lbl": status_lbl}

        sep = ctk.CTkFrame(parent, fg_color=OFF, height=1)
        sep.grid(row=row + 1, column=0, columnspan=4, sticky="ew", pady=(0, 2))

    def _git_badge(self, parent, text, color):
        ctk.CTkLabel(parent, text=text, fg_color=color, text_color="white", corner_radius=10,
                    font=("Segoe UI", 9, "bold"), height=20, padx=8
                    ).pack(side="left", padx=(0, 6))

    def _push_selected(self):
        selected = [(p, r["name"]) for p, v in self._git_vars.items() if v.get()
                    for r in self._git_repos if r["path"] == p]
        if not selected:
            messagebox.showinfo("ClAuSy", "No repos selected.\nCheck the box next to any "
                                "repo with unpushed commits, or use \"Select Unpushed\".")
            return
        paths = [p for p, _ in selected]
        names = [n for _, n in selected]
        self._push_paths(paths, names)

    def _push_paths(self, paths: list, names: list):
        if self._git_busy:
            return
        diverged = [n for p, n in zip(paths, names)
                    for r in self._git_repos if r["path"] == p and r.get("behind", 0) > 0]
        diverged_warning = ""
        if diverged:
            diverged_warning = (
                "\n\n⚠ " + ", ".join(diverged) + " diverged from the remote — "
                "git push will likely be rejected as non-fast-forward (ClAuSy never "
                "force-pushes, so nothing on the remote can be lost by this action).")

        rewritten = [n for p, n in zip(paths, names)
                     for r in self._git_repos if r["path"] == p and r.get("history_rewritten")]
        rewritten_warning = ""
        if rewritten:
            rewritten_warning = (
                "\n\n⚠ " + ", ".join(rewritten) + " has local history that looks amended "
                "or rebased since ClAuSy last saw it — a plain push will be rejected unless "
                "the remote already expects this (ClAuSy never force-pushes).")

        if not messagebox.askyesno(
            "ClAuSy — Push to remote",
            f"This will run 'git push' for {len(paths)} repo(s):\n\n" +
            "\n".join(f"  • {n}" for n in names) +
            "\n\nThis pushes to the remote (GitHub) and is visible to anyone with "
            "access to it. Continue?" + diverged_warning + rewritten_warning
        ):
            return

        self._set_git_busy(True, "Pushing…")
        self._git_prog_bar.set(0)
        for p in paths:
            ui = self._git_row_ui.get(p)
            if ui:
                ui["status_lbl"].configure(text="Queued…", text_color=DIM)

        def worker():
            total = len(paths)
            failures = []
            for i, p in enumerate(paths):
                name = next((n for pp, n in zip(paths, names) if pp == p), p)
                self.root.after(0, self._on_git_push_progress, p, name, i, total)
                result = git_status.push_repo(p)
                self.root.after(0, self._on_git_push_result, p, name, result)
                if not result["ok"]:
                    failures.append(name)
            self.root.after(0, self._on_git_push_done, total, failures)

        threading.Thread(target=worker, daemon=True).start()

    def _on_git_push_progress(self, path, name, index, total):
        self._git_status_lbl.configure(text=f"Pushing {name}… ({index + 1}/{total})")
        self._git_prog_bar.set(index / total)
        ui = self._git_row_ui.get(path)
        if ui:
            ui["status_lbl"].configure(text="Pushing…", text_color=DIM)

    def _on_git_push_result(self, path, name, result):
        ui = self._git_row_ui.get(path)
        if not ui:
            return
        if result["ok"]:
            ui["status_lbl"].configure(text="Pushed ✓", text_color=CC_G)
        else:
            ui["status_lbl"].configure(text="Push failed", text_color=CC_R)
            first_line = (result["output"].splitlines() or [""])[0]
            Tooltip(ui["status_lbl"], result["output"] or "Unknown error")
            if first_line:
                ui["status_lbl"].configure(text=f"Push failed — {first_line[:60]}",
                                           text_color=CC_R)

    def _on_git_push_done(self, total, failures):
        self._git_prog_bar.set(1)
        if failures:
            self._git_status_lbl.configure(
                text=f"{total - len(failures)}/{total} pushed, {len(failures)} failed",
                text_color=CC_R)
        else:
            self._git_status_lbl.configure(text=f"All {total} pushed ✓", text_color=CC_G)
        self._set_git_busy(False, self._git_status_lbl.cget("text"))
        self.root.after(3000, self._refresh_gitpush_tab)

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
                 "servers) is preserved untouched. A timestamped .bak backup of each "
                 f"file is kept alongside it before every write (last "
                 f"{config_manager.BACKUP_KEEP_COUNT} kept, older ones pruned).")

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
