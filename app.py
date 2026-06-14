"""ClAuSy — Claude Paths Manager UI."""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import threading
import time
from pathlib import Path
import datetime

import config_manager
import storage

# ─── palette ─────────────────────────────────────────────────────────────────
BG      = "#12121e"
SURF    = "#1c1c2e"
SURF2   = "#26263e"
SURF3   = "#30304a"
TEXT    = "#dcdcf0"
DIM     = "#6868a0"
ACCENT  = "#7c6af7"
ACC2    = "#5a4ec0"

CC_R    = "#e74c3c"   # red   — permissions.allow
CC_G    = "#27ae60"   # green — additionalDirectories
CD_B    = "#2980b9"   # blue  — Desktop MCP
OFF     = "#3a3a5c"
OFF_TXT = "#555580"

ICON_S  = 24
THUMB_W = 160
THUMB_H = 148
CPAD    = 14


# ─── helpers ─────────────────────────────────────────────────────────────────

def _norm(p: str) -> str:
    return os.path.normpath(p)


def _ctime(p: str) -> float:
    try:
        return os.path.getctime(p)
    except OSError:
        return 0.0


# ─── widgets ─────────────────────────────────────────────────────────────────

class ToggleCircle(tk.Canvas):
    """24×24 clickable circle toggle."""

    def __init__(self, parent, letter: str, on_color: str,
                 state: bool = False, on_toggle=None, bg: str = SURF, **kw):
        super().__init__(parent, width=ICON_S, height=ICON_S,
                         bd=0, highlightthickness=0, bg=bg, **kw)
        self.letter    = letter
        self.on_color  = on_color
        self._state    = state
        self.on_toggle = on_toggle
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>",    lambda e: self.config(cursor="hand2"))
        self.bind("<Leave>",    lambda e: self.config(cursor="arrow"))
        self._draw()

    def _draw(self):
        self.delete("all")
        fill    = self.on_color if self._state else SURF
        outline = self.on_color if self._state else OFF
        self.create_oval(2, 2, ICON_S - 2, ICON_S - 2,
                         fill=fill, outline=outline, width=2)
        self.create_text(ICON_S // 2, ICON_S // 2 + 1,
                         text=self.letter,
                         fill="white" if self._state else OFF_TXT,
                         font=("Segoe UI", 8, "bold"))

    def _click(self, _=None):
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


class ScrollableFrame(tk.Frame):
    """Vertically scrollable container."""

    def __init__(self, parent, bg: str = SURF, **kw):
        super().__init__(parent, bg=bg, **kw)
        self._cv  = tk.Canvas(self, bg=bg, bd=0, highlightthickness=0)
        self._sb  = ttk.Scrollbar(self, orient="vertical", command=self._cv.yview)
        self.inner = tk.Frame(self._cv, bg=bg)
        self._wid  = self._cv.create_window((0, 0), window=self.inner, anchor="nw")

        self._cv.configure(yscrollcommand=self._sb.set)
        self._cv.pack(side="left", fill="both", expand=True)
        self._sb.pack(side="right", fill="y")

        self.inner.bind("<Configure>",   self._inner_cfg)
        self._cv.bind("<Configure>",     self._canvas_cfg)
        self._cv.bind("<MouseWheel>",    self._wheel)
        self.inner.bind("<MouseWheel>",  self._wheel)

    def _inner_cfg(self, _):
        self._cv.configure(scrollregion=self._cv.bbox("all"))

    def _canvas_cfg(self, ev):
        self._cv.itemconfig(self._wid, width=ev.width)

    def _wheel(self, ev):
        self._cv.yview_scroll(int(-1 * (ev.delta / 120)), "units")


class DirectoryRow:
    """One row in the list view."""

    ROW_COLORS = [SURF, SURF2]

    def __init__(self, parent, entry: dict, idx: int, on_change=None):
        self.entry     = entry
        self.on_change = on_change
        bg             = self.ROW_COLORS[idx % 2]
        self._sel      = tk.BooleanVar(value=False)

        self.cb = tk.Checkbutton(parent, variable=self._sel,
                                 bg=bg, fg=TEXT, selectcolor=bg,
                                 activebackground=bg, relief="flat",
                                 highlightthickness=0, cursor="hand2")

        self._lv = tk.StringVar(value=entry.get("label", ""))
        self.le  = tk.Entry(parent, textvariable=self._lv,
                            bg=bg, fg=TEXT, insertbackground=TEXT,
                            relief="flat", highlightthickness=1,
                            highlightcolor=ACCENT, highlightbackground=OFF,
                            font=("Segoe UI", 9), width=15)
        self.le.bind("<FocusOut>", lambda e: self._sync_label())
        self.le.bind("<Return>",   lambda e: self._sync_label())

        self.pl = tk.Label(parent, text=entry.get("path", ""),
                           bg=bg, fg=DIM, font=("Consolas", 8),
                           anchor="w", cursor="hand2")
        self.pl.bind("<Double-Button-1>", self._open_dir)

        self.t_r = ToggleCircle(parent, "C", CC_R,
                                 state=entry.get("cc_allow", False),
                                 on_toggle=lambda v: self._set("cc_allow", v), bg=bg)
        self.t_g = ToggleCircle(parent, "C", CC_G,
                                 state=entry.get("cc_additional", False),
                                 on_toggle=lambda v: self._set("cc_additional", v), bg=bg)
        self.t_d = ToggleCircle(parent, "D", CD_B,
                                 state=entry.get("cd", False),
                                 on_toggle=lambda v: self._set("cd", v), bg=bg)

    def place(self, row: int):
        self.cb.grid(row=row, column=0, padx=(8, 2), pady=3, sticky="ns")
        self.le.grid(row=row, column=1, padx=4,     pady=3, sticky="ew")
        self.pl.grid(row=row, column=2, padx=4,     pady=3, sticky="ew")
        self.t_r.grid(row=row, column=3, padx=10,   pady=3)
        self.t_g.grid(row=row, column=4, padx=10,   pady=3)
        self.t_d.grid(row=row, column=5, padx=10,   pady=3)

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
        self.entry["label"] = self._lv.get()
        self.entry["cc_allow"]      = self.t_r.get()
        self.entry["cc_additional"] = self.t_g.get()
        self.entry["cd"]            = self.t_d.get()


# ─── main app ────────────────────────────────────────────────────────────────

class ClausyApp:
    def __init__(self, root: tk.Tk):
        self.root     = root
        self.root.title("ClAuSy — Claude Paths Manager")
        self.root.configure(bg=BG)
        self.root.minsize(820, 560)

        self._entries: list[dict] = []
        self._rows:    list[DirectoryRow] = []
        self._pending  = False

        self._cc_var   = tk.StringVar()
        self._cd_var   = tk.StringVar()
        self._sort_var = tk.StringVar(value="name_asc")
        self._view_var = tk.StringVar(value="list")
        self._prog_var = tk.IntVar(value=0)

        self._setup_styles()
        self._build_ui()
        self._load_settings()

    # ── styles ────────────────────────────────────────────────────────────────

    def _setup_styles(self):
        s = ttk.Style(self.root)
        s.theme_use("clam")
        s.configure("TNotebook",        background=BG,    borderwidth=0)
        s.configure("TNotebook.Tab",    background=SURF2, foreground=DIM,
                    padding=[14, 6],    font=("Segoe UI", 10))
        s.map("TNotebook.Tab",
              background=[("selected", SURF3)],
              foreground=[("selected", TEXT)])
        s.configure("TFrame",           background=BG)
        s.configure("Vertical.TScrollbar", background=SURF2, troughcolor=SURF,
                    arrowcolor=DIM)
        s.configure("TProgressbar",     troughcolor=SURF2, background=ACCENT,
                    darkcolor=ACCENT,   lightcolor=ACCENT, bordercolor=BG)

    # ── UI skeleton ───────────────────────────────────────────────────────────

    def _build_ui(self):
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=0, pady=0)

        self._tab_settings = ttk.Frame(nb)
        self._tab_dirs     = ttk.Frame(nb)
        nb.add(self._tab_settings, text="  Settings  ")
        nb.add(self._tab_dirs,     text="  Directories  ")

        self._build_settings_tab(self._tab_settings)
        self._build_dirs_tab(self._tab_dirs)

    # ── Settings tab ─────────────────────────────────────────────────────────

    def _build_settings_tab(self, parent):
        parent.configure(style="TFrame")
        wrap = tk.Frame(parent, bg=BG)
        wrap.pack(fill="both", expand=True, padx=40, pady=30)

        def row(label, var, r):
            tk.Label(wrap, text=label, bg=BG, fg=DIM,
                     font=("Segoe UI", 9)).grid(row=r, column=0, sticky="w", pady=(14, 2))
            f = tk.Frame(wrap, bg=BG)
            f.grid(row=r+1, column=0, sticky="ew", pady=(0, 4))
            f.columnconfigure(0, weight=1)
            e = tk.Entry(f, textvariable=var, bg=SURF2, fg=TEXT,
                         insertbackground=TEXT, relief="flat",
                         highlightthickness=1, highlightcolor=ACCENT,
                         highlightbackground=OFF,
                         font=("Consolas", 9), width=60)
            e.grid(row=0, column=0, sticky="ew", ipady=5, padx=(0, 6))
            tk.Button(f, text="Browse", bg=SURF3, fg=TEXT,
                      activebackground=ACCENT, activeforeground="white",
                      relief="flat", cursor="hand2", padx=10,
                      command=lambda v=var: self._browse_file(v)
                      ).grid(row=0, column=1)

        row("Claude Code settings file  ( ~/.claude/settings.json )", self._cc_var, 0)
        row("Claude Desktop config  ( claude_desktop_config.json )",  self._cd_var, 2)

        wrap.columnconfigure(0, weight=1)

        btn_f = tk.Frame(wrap, bg=BG)
        btn_f.grid(row=4, column=0, sticky="w", pady=24)

        def btn(parent, label, cmd, accent=False):
            c = ACCENT if accent else SURF3
            return tk.Button(parent, text=label, bg=c, fg=TEXT,
                             activebackground=ACC2, activeforeground="white",
                             relief="flat", cursor="hand2", padx=14, pady=6,
                             command=cmd)

        btn(btn_f, "Auto-Detect",   self._auto_detect      ).pack(side="left", padx=(0, 10))
        btn(btn_f, "Save & Reload", self._save_and_reload,
            accent=True                                     ).pack(side="left")

        self._status_lbl = tk.Label(wrap, text="", bg=BG, fg=DIM,
                                    font=("Segoe UI", 9))
        self._status_lbl.grid(row=5, column=0, sticky="w")

    # ── Directories tab ───────────────────────────────────────────────────────

    def _build_dirs_tab(self, parent):
        parent.configure(style="TFrame")

        # ── toolbar ──────────────────────────────────────────────────────────
        toolbar = tk.Frame(parent, bg=SURF2, pady=6)
        toolbar.pack(fill="x", side="top")

        def tbtn(text, cmd, tip=""):
            b = tk.Button(toolbar, text=text, bg=SURF3, fg=TEXT,
                          activebackground=ACCENT, activeforeground="white",
                          relief="flat", cursor="hand2", padx=10, pady=4,
                          font=("Segoe UI", 9), command=cmd)
            b.pack(side="left", padx=4, pady=0)
            return b

        tbtn("＋ Add",    self._add_directory)
        tbtn("✕ Delete", self._delete_selected)

        tk.Frame(toolbar, bg=SURF2, width=18).pack(side="left")
        tk.Label(toolbar, text="Sort:", bg=SURF2, fg=DIM,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))

        sort_opts = [("Name A→Z", "name_asc"), ("Name Z→A", "name_desc"),
                     ("Date ↑",   "date_asc"), ("Date ↓",   "date_desc")]
        for label, val in sort_opts:
            tk.Radiobutton(toolbar, text=label, variable=self._sort_var,
                           value=val, bg=SURF2, fg=TEXT, selectcolor=SURF2,
                           activebackground=SURF2, activeforeground=TEXT,
                           font=("Segoe UI", 9), cursor="hand2",
                           command=self._apply_sort
                           ).pack(side="left", padx=2)

        tk.Frame(toolbar, bg=SURF2, width=18).pack(side="left")

        for label, val in (("≡ List", "list"), ("⊞ Thumb", "thumb")):
            tk.Radiobutton(toolbar, text=label, variable=self._view_var,
                           value=val, bg=SURF2, fg=TEXT, selectcolor=SURF2,
                           activebackground=SURF2, activeforeground=TEXT,
                           font=("Segoe UI", 9), cursor="hand2",
                           command=self._switch_view
                           ).pack(side="left", padx=2)

        # ── column headers (list view only) ──────────────────────────────────
        self._header = tk.Frame(parent, bg=SURF3)
        self._header.pack(fill="x", side="top")

        tk.Label(self._header, text="", bg=SURF3, width=2).grid(row=0, column=0, padx=(8,2))
        tk.Label(self._header, text="Label", bg=SURF3, fg=DIM,
                 font=("Segoe UI", 9, "bold"), anchor="w", width=15
                 ).grid(row=0, column=1, padx=4, pady=5, sticky="w")
        tk.Label(self._header, text="Path", bg=SURF3, fg=DIM,
                 font=("Segoe UI", 9, "bold"), anchor="w"
                 ).grid(row=0, column=2, padx=4, sticky="ew")
        self._header.columnconfigure(2, weight=1)

        for col_idx, (letter, key, color) in enumerate(
            [("C", "cc_allow", CC_R), ("C", "cc_additional", CC_G), ("D", "cd", CD_B)],
            start=3
        ):
            c = tk.Canvas(self._header, width=ICON_S, height=ICON_S,
                          bd=0, highlightthickness=0, bg=SURF3, cursor="hand2")
            c.create_oval(2, 2, ICON_S-2, ICON_S-2, fill=color, outline=color, width=2)
            c.create_text(ICON_S//2, ICON_S//2+1, text=letter,
                          fill="white", font=("Segoe UI", 8, "bold"))
            c.grid(row=0, column=col_idx, padx=10, pady=5)
            c.bind("<Button-1>", lambda e, k=key: self._header_toggle(k))
            c.bind("<Enter>",    lambda e, cv=c: cv.config(cursor="hand2"))

        # ── content area (list + thumb share same slot) ───────────────────────
        self._content = tk.Frame(parent, bg=BG)
        self._content.pack(fill="both", expand=True, side="top")

        self._sf = ScrollableFrame(self._content, bg=SURF)
        self._sf.pack(fill="both", expand=True)
        self._sf.inner.columnconfigure(2, weight=1)

        self._thumb_outer = tk.Frame(self._content, bg=BG)
        self._thumb_cv    = tk.Canvas(self._thumb_outer, bg=BG, bd=0,
                                       highlightthickness=0)
        self._thumb_sb    = ttk.Scrollbar(self._thumb_outer, orient="vertical",
                                           command=self._thumb_cv.yview)
        self._thumb_cv.configure(yscrollcommand=self._thumb_sb.set)
        self._thumb_cv.pack(side="left", fill="both", expand=True)
        self._thumb_sb.pack(side="right", fill="y")
        self._thumb_cv.bind("<Configure>", lambda e: self._draw_thumbs())
        self._thumb_cv.bind("<Button-1>",  self._thumb_click)
        self._thumb_cv.bind("<MouseWheel>", lambda e: self._thumb_cv.yview_scroll(
            int(-1 * e.delta / 120), "units"))

        self._thumb_cards: list[dict] = []

        # ── footer ────────────────────────────────────────────────────────────
        footer = tk.Frame(parent, bg=SURF2, pady=8)
        footer.pack(fill="x", side="bottom")

        self._exec_btn = tk.Button(
            footer, text="▶  Execute Changes", bg=ACCENT, fg="white",
            activebackground=ACC2, activeforeground="white",
            relief="flat", cursor="hand2", padx=18, pady=7,
            font=("Segoe UI", 10, "bold"), command=self._execute_changes)
        self._exec_btn.pack(side="left", padx=14)

        prog_frame = tk.Frame(footer, bg=SURF2)
        prog_frame.pack(side="left", fill="x", expand=True, padx=(0, 14))

        self._prog_bar = ttk.Progressbar(prog_frame, variable=self._prog_var,
                                          maximum=100, length=200,
                                          style="TProgressbar")
        self._prog_bar.pack(side="left")
        self._prog_lbl = tk.Label(prog_frame, text="", bg=SURF2, fg=DIM,
                                   font=("Segoe UI", 9))
        self._prog_lbl.pack(side="left", padx=8)

    # ── settings load / save ─────────────────────────────────────────────────

    def _load_settings(self):
        data = storage.load()
        self._cc_var.set(data.get("cc_settings", ""))
        self._cd_var.set(data.get("cd_config", ""))
        self._sort_var.set(data.get("sort_mode", "name_asc"))
        self._view_var.set(data.get("view_mode", "list"))
        self._labels: dict = data.get("labels", {})
        self._reload_entries()
        self._switch_view()

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
        p = filedialog.askopenfilename(filetypes=[("JSON files", "*.json"), ("All", "*.*")])
        if p:
            var.set(p)

    def _auto_detect(self):
        detected = config_manager.auto_detect()
        if detected["cc_settings"]:
            self._cc_var.set(detected["cc_settings"])
        if detected["cd_config"]:
            self._cd_var.set(detected["cd_config"])
        self._set_status("Auto-detect done. Press 'Save & Reload' to apply.")

    def _save_and_reload(self):
        self._save_settings_data()
        self._reload_entries()
        self._set_status("Saved. Config files reloaded.")

    def _set_status(self, msg: str, color: str = DIM):
        self._status_lbl.config(text=msg, fg=color)

    # ── entry management ─────────────────────────────────────────────────────

    def _reload_entries(self):
        cc = self._cc_var.get()
        cd = self._cd_var.get()
        path_states = config_manager.read_all_dirs(cc, cd)

        new_entries = []
        for path, flags in path_states.items():
            label = self._labels.get(path, Path(path).name)
            new_entries.append({"path": path, "label": label, **flags})

        # preserve labels from existing entries not overwritten
        existing_paths = {e["path"] for e in new_entries}
        for e in self._entries:
            if e["path"] not in existing_paths:
                new_entries.append(e)

        self._entries = new_entries
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
        for w in self._sf.inner.winfo_children():
            w.destroy()
        self._rows.clear()

        for i, entry in enumerate(self._entries):
            r = DirectoryRow(self._sf.inner, entry, i,
                             on_change=lambda: setattr(self, "_pending", True))
            r.place(i)
            self._rows.append(r)

        self._sf.inner.columnconfigure(2, weight=1)

    def _switch_view(self):
        mode = self._view_var.get()
        if mode == "list":
            self._thumb_outer.pack_forget()
            self._sf.pack(fill="both", expand=True)
            self._header.pack(fill="x", side="top", before=self._content)
        else:
            self._header.pack_forget()
            self._sf.pack_forget()
            self._thumb_outer.pack(fill="both", expand=True)
            self._draw_thumbs()

    # ── add / delete ─────────────────────────────────────────────────────────

    def _add_directory(self):
        p = filedialog.askdirectory(title="Select directory to add")
        if not p:
            return
        norm = _norm(p)
        if any(e["path"] == norm for e in self._entries):
            messagebox.showinfo("ClAuSy", "This path is already in the list.")
            return
        label = Path(norm).name
        self._entries.append({
            "path": norm, "label": label,
            "cc_allow": False, "cc_additional": False, "cd": False,
        })
        self._apply_sort(refresh=True)
        self._pending = True

    def _delete_selected(self):
        if not self._rows:
            return
        sel_paths = {r.entry["path"] for r in self._rows if r.is_checked()}
        if not sel_paths:
            messagebox.showinfo("ClAuSy", "Select rows with the checkbox first.")
            return
        if not messagebox.askyesno("ClAuSy", f"Remove {len(sel_paths)} entry/ies from the list?\n"
                                             "(Config files are NOT changed until you press Execute.)"):
            return
        self._entries = [e for e in self._entries if e["path"] not in sel_paths]
        self._refresh_list()
        if self._view_var.get() == "thumb":
            self._draw_thumbs()
        self._pending = True

    # ── header column toggle ─────────────────────────────────────────────────

    def _header_toggle(self, key: str):
        checked = [r for r in self._rows if r.is_checked()]
        targets  = checked if checked else self._rows
        current  = [r.entry.get(key, False) for r in targets]
        new_val  = not all(current)
        for r in targets:
            r.set_toggle(key, new_val)
        self._pending = True
        if self._view_var.get() == "thumb":
            self._draw_thumbs()

    # ── thumbnail canvas ─────────────────────────────────────────────────────

    def _draw_thumbs(self):
        cv       = self._thumb_cv
        cv.delete("all")
        self._thumb_cards.clear()

        cw       = cv.winfo_width() or 600
        cols     = max(1, (cw - CPAD) // (THUMB_W + CPAD))
        card_w   = THUMB_W
        card_h   = THUMB_H

        for i, entry in enumerate(self._entries):
            col = i % cols
            row = i // cols
            x0  = CPAD + col * (card_w + CPAD)
            y0  = CPAD + row * (card_h + CPAD)
            x1  = x0 + card_w
            y1  = y0 + card_h

            # card background
            cv.create_rectangle(x0, y0, x1, y1, fill=SURF2, outline=SURF3,
                                 width=1, tags="card")

            # folder icon (two rectangles)
            fx, fy = x0 + card_w // 2 - 24, y0 + 32
            cv.create_rectangle(fx, fy + 9, fx + 48, fy + 38,
                                 fill="#c87e1a", outline="")
            cv.create_rectangle(fx, fy + 7, fx + 22, fy + 14,
                                 fill="#e6952a", outline="")
            cv.create_rectangle(fx + 2, fy + 10, fx + 46, fy + 36,
                                 fill="#e6952a", outline="")

            # label
            label = entry.get("label", Path(entry["path"]).name)
            if len(label) > 16:
                label = label[:14] + "…"
            cv.create_text(x0 + card_w // 2, y0 + card_h - 22,
                           text=label, fill=TEXT,
                           font=("Segoe UI", 9, "bold"), anchor="center")

            # path tiny
            p = entry.get("path", "")
            if len(p) > 24:
                p = "…" + p[-23:]
            cv.create_text(x0 + card_w // 2, y0 + card_h - 8,
                           text=p, fill=DIM,
                           font=("Consolas", 7), anchor="center")

            # badge circles: D (left), C-green (center), C-red (right)
            badges = [
                ("D",  CD_B,  entry.get("cd",             False), x0 + 20),
                ("C",  CC_G,  entry.get("cc_additional",  False), x0 + card_w // 2),
                ("C",  CC_R,  entry.get("cc_allow",       False), x1 - 20),
            ]
            badge_centers = {}
            keys_map = {0: "cd", 1: "cc_additional", 2: "cc_allow"}
            for bi, (letter, color, state, bx) in enumerate(badges):
                by     = y0 + 14
                fill   = color if state else SURF
                outline = color if state else OFF
                r      = 10
                cv.create_oval(bx - r, by - r, bx + r, by + r,
                               fill=fill, outline=outline, width=2)
                cv.create_text(bx, by + 1, text=letter,
                               fill="white" if state else OFF_TXT,
                               font=("Segoe UI", 8, "bold"))
                badge_centers[keys_map[bi]] = (bx, by)

            self._thumb_cards.append({
                "entry":  entry,
                "bounds": (x0, y0, x1, y1),
                "badges": badge_centers,
            })

        total_rows = (len(self._entries) + cols - 1) // cols
        total_h    = CPAD + total_rows * (card_h + CPAD)
        cv.configure(scrollregion=(0, 0, cw, total_h))

    def _thumb_click(self, event):
        cv = self._thumb_cv
        cx = cv.canvasx(event.x)
        cy = cv.canvasy(event.y)
        HIT = 11
        for card in self._thumb_cards:
            x0, y0, x1, y1 = card["bounds"]
            if not (x0 <= cx <= x1 and y0 <= cy <= y1):
                continue
            for key, (bx, by) in card["badges"].items():
                if abs(cx - bx) <= HIT and abs(cy - by) <= HIT:
                    card["entry"][key] = not card["entry"][key]
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
                                 "No config paths set. Go to Settings tab first.")
            return

        self._exec_btn.config(state="disabled")
        self._prog_var.set(0)
        self._prog_lbl.config(text="Writing…")

        def worker():
            def prog(pct):
                self.root.after(0, self._prog_var.set, pct)
                self.root.after(0, self._prog_lbl.config,
                                {"text": f"{pct}%"})
                time.sleep(0.08)

            try:
                config_manager.apply_changes(cc, cd, self._entries, progress_cb=prog)
                self._save_settings_data()
                self.root.after(0, self._on_exec_done, True, "")
            except Exception as exc:
                self.root.after(0, self._on_exec_done, False, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_exec_done(self, ok: bool, err: str):
        self._exec_btn.config(state="normal")
        if ok:
            self._prog_lbl.config(text="Done ✓", fg=CC_G)
            self._pending = False
        else:
            self._prog_var.set(0)
            self._prog_lbl.config(text="Error", fg=CC_R)
            messagebox.showerror("ClAuSy", f"Write failed:\n{err}")
        self.root.after(3000, lambda: self._prog_lbl.config(text="", fg=DIM))
