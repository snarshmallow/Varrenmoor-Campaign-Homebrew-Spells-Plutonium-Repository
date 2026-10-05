"""Varrenmoor Foundry Tools: desktop GUI for the vtt commands.   python foundry-tools/vtt_gui.py   (or double-click vtt_gui.cmd)

Tabs: NPC, Item, Scene, Encounter, Place, Publish. Long jobs (art, 3D, scene builds) run in a worker thread and stream their output to the log at the bottom,
so the window stays usable. Every create button has a Dry run beside it. Specs can be loaded and saved as JSON, so the GUI and the command line share files.
"""
import contextlib
import json
import queue
import subprocess
import sys
import threading
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vtt import art, docs, encounter, item, npc, scene  # noqa: E402
from vtt.common import GEN, ROOT, bridge, find, scene_frame, slug, to_scene, uuid_id  # noqa: E402

SIZES = ["tiny", "sm", "med", "lg", "huge"]
ABIL = ["str", "dex", "con", "int", "wis", "cha"]
DTYPES = ["bludgeoning", "piercing", "slashing", "fire", "cold", "lightning", "acid", "poison", "necrotic", "radiant", "psychic", "force", "thunder"]
SHAPES = ["paper", "book", "tag", "tin", "box", "plate"]
DOORS = scene.DOOR_SOUNDS
FACINGS = ["n", "s", "e", "w"]


class QueueWriter:
    def __init__(self, q):
        self.q = q

    def write(self, s):
        if s:
            self.q.put(s)

    def flush(self):
        pass


class Table(ttk.Frame):
    """A small editable table: columns [(key, heading, width)], rows as dicts, a row editor underneath with Add / Update / Remove."""

    def __init__(self, parent, columns, choices=None, height=5):
        super().__init__(parent)
        self.cols = columns
        self.choices = choices or {}
        self.tree = ttk.Treeview(self, columns=[c[0] for c in columns], show="headings", height=height, selectmode="browse")
        for k, h, w in columns:
            self.tree.heading(k, text=h)
            self.tree.column(k, width=w, anchor="w")
        self.tree.grid(row=0, column=0, columnspan=99, sticky="nsew")
        self.vars = {}
        for i, (k, h, w) in enumerate(columns):
            v = tk.StringVar()
            self.vars[k] = v
            if k in self.choices:
                w_ = ttk.Combobox(self, textvariable=v, values=self.choices[k], width=max(6, w // 9))
            else:
                w_ = ttk.Entry(self, textvariable=v, width=max(6, w // 9))
            w_.grid(row=1, column=i, sticky="ew", padx=1, pady=2)
        bar = ttk.Frame(self)
        bar.grid(row=2, column=0, columnspan=99, sticky="w")
        ttk.Button(bar, text="Add", command=self.add).pack(side="left", padx=2)
        ttk.Button(bar, text="Update selected", command=self.update_sel).pack(side="left", padx=2)
        ttk.Button(bar, text="Remove", command=self.remove).pack(side="left", padx=2)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.columnconfigure(0, weight=1)

    def row(self):
        return {k: self.vars[k].get() for k, _, _ in self.cols}

    def add(self):
        r = self.row()
        if r[self.cols[0][0]].strip():
            self.tree.insert("", "end", values=[r[k] for k, _, _ in self.cols])

    def update_sel(self):
        s = self.tree.selection()
        if s:
            self.tree.item(s[0], values=[self.vars[k].get() for k, _, _ in self.cols])

    def remove(self):
        for s in self.tree.selection():
            self.tree.delete(s)

    def on_select(self, _):
        s = self.tree.selection()
        if s:
            for (k, _, _), v in zip(self.cols, self.tree.item(s[0], "values")):
                self.vars[k].set(v)

    def rows(self):
        return [dict(zip([k for k, _, _ in self.cols], self.tree.item(i, "values"))) for i in self.tree.get_children()]

    def set_rows(self, rows):
        self.tree.delete(*self.tree.get_children())
        for r in rows:
            self.tree.insert("", "end", values=[r.get(k, "") for k, _, _ in self.cols])


def labeled(parent, row, text, widget, col=0, span=1):
    ttk.Label(parent, text=text).grid(row=row, column=col, sticky="w", padx=3, pady=2)
    widget.grid(row=row, column=col + 1, columnspan=span, sticky="ew", padx=3, pady=2)
    return widget


def text_box(parent, height=3, width=48):
    t = tk.Text(parent, height=height, width=width, wrap="word", undo=True)
    return t


def get_text(t):
    return t.get("1.0", "end").strip()


def set_text(t, s):
    t.delete("1.0", "end")
    t.insert("1.0", s or "")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Varrenmoor Foundry Tools")
        self.geometry("1080x860")
        self.q = queue.Queue()
        self.busy = False
        self.cache = {"Scene": [], "Actor": [], "Item": [], "Playlist": [], "Folder": []}
        self.concept_image = None
        self._style()
        self._menu()
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=6, pady=(6, 0))
        self.build_npc()
        self.build_item()
        self.build_scene()
        self.build_encounter()
        self.build_place()
        self.build_publish()
        self._bottom()
        self.after(100, self.pump)
        self.after(300, lambda: self.run_job("Connecting to Foundry", self.job_refresh))

    # ------------------------------------------------------------------ chrome
    def _style(self):
        st = ttk.Style(self)
        with contextlib.suppress(tk.TclError):
            st.theme_use("vista")
        st.configure("Accent.TButton", font=("Segoe UI", 9, "bold"))

    def _menu(self):
        m = tk.Menu(self)
        f = tk.Menu(m, tearoff=0)
        f.add_command(label="Refresh Foundry lists (scenes, actors, items, playlists)", command=lambda: self.run_job("Refreshing", self.job_refresh))
        f.add_command(label="Open README", command=lambda: self.open_path(ROOT / "foundry-tools" / "README.md"))
        f.add_command(label="Open generated-content guide", command=lambda: self.open_path(docs.GEN_FILE))
        f.add_separator()
        f.add_command(label="Exit", command=self.destroy)
        m.add_cascade(label="File", menu=f)
        self.config(menu=m)

    def _bottom(self):
        fr = ttk.Frame(self)
        fr.pack(fill="both", padx=6, pady=6)
        top = ttk.Frame(fr)
        top.pack(fill="x")
        self.status = tk.StringVar(value="Idle")
        ttk.Label(top, textvariable=self.status).pack(side="left")
        self.bar = ttk.Progressbar(top, mode="indeterminate", length=160)
        self.bar.pack(side="right")
        ttk.Button(top, text="Clear log", command=lambda: self.log.delete("1.0", "end")).pack(side="right", padx=6)
        self.log = tk.Text(fr, height=11, wrap="word", bg="#101418", fg="#d7e0e8", insertbackground="#fff")
        sb = ttk.Scrollbar(fr, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True)

    def pump(self):
        try:
            while True:
                s = self.q.get_nowait()
                if callable(s):                                          # callbacks queued by worker threads run here, on the UI thread
                    s()
                else:
                    self.log.insert("end", s)
                    self.log.see("end")
        except queue.Empty:
            pass
        self.after(100, self.pump)

    def say(self, s):
        self.q.put(s + "\n")

    def open_path(self, p):
        try:
            import os
            os.startfile(str(p))
        except OSError as e:
            messagebox.showerror("Open", str(e))

    # ------------------------------------------------------------------ jobs (worker thread, output streamed to the log)
    def run_job(self, title, fn, after=None):
        if self.busy:
            messagebox.showinfo("Busy", "A job is already running. Wait for it to finish.")
            return
        self.busy = True
        self.status.set(title + " ...")
        self.bar.start(12)
        self.say(f"=== {title}")

        def work():
            res = None
            try:
                with contextlib.redirect_stdout(QueueWriter(self.q)), contextlib.redirect_stderr(QueueWriter(self.q)):
                    res = fn()
                self.say(f"--- done: {title}")
            except Exception as e:                                       # noqa: BLE001
                self.say("!!! " + "".join(traceback.format_exception_only(type(e), e)).strip())
                self.say(traceback.format_exc(limit=3))
            finally:
                self.busy = False
                self.q.put(lambda: (self.bar.stop(), self.status.set("Idle")))
                if after:
                    self.q.put(lambda: after(res))

        threading.Thread(target=work, daemon=True).start()

    def job_refresh(self):
        for coll in ("Scene", "Actor", "Item", "Playlist"):
            self.cache[coll] = sorted(r["name"] for r in bridge("list", collection=coll))
        self.cache["Folder"] = bridge("list", collection="Folder")
        self.q.put(self.apply_lists)
        print(f"Foundry connected: {len(self.cache['Scene'])} scenes, {len(self.cache['Actor'])} actors, {len(self.cache['Item'])} items")

    def apply_lists(self):
        for w, key in self.combos:
            w["values"] = self.cache[key] if key in self.cache else self.folder_names(key)

    def folder_names(self, ftype):
        return sorted({r["name"] for r in self.cache["Folder"] if r.get("type") == ftype})

    # ------------------------------------------------------------------ shared pieces
    def combo(self, parent, var, kind, width=34):
        c = ttk.Combobox(parent, textvariable=var, width=width)
        self.combos.append((c, kind))
        return c

    combos = []

    def place_block(self, parent, row, prefix, with_z=True, wall=False):
        """Scene / at-x / at-y / at-z controls. Returns dict of variables."""
        v = {k: tk.StringVar() for k in ("scene", "x", "y", "z")}
        v["z"].set("0.1")
        v["place"] = tk.BooleanVar(value=False)
        v["wall"] = tk.BooleanVar(value=False)
        v["facing"] = tk.StringVar(value="n")
        v["scale"] = tk.StringVar(value="3")
        box = ttk.LabelFrame(parent, text="Place in a scene")
        box.grid(row=row, column=0, columnspan=4, sticky="ew", padx=3, pady=6)
        ttk.Checkbutton(box, text="Place it", variable=v["place"]).grid(row=0, column=0, sticky="w")
        ttk.Label(box, text="Scene").grid(row=0, column=1, sticky="e")
        self.combo(box, v["scene"], "Scene", 36).grid(row=0, column=2, columnspan=5, sticky="ew", padx=3)
        for i, (k, t) in enumerate((("x", "x (m)"), ("y", "y (m)"), ("z", "z surface (m)"))):
            ttk.Label(box, text=t).grid(row=1, column=1 + i * 2, sticky="e")
            ttk.Entry(box, textvariable=v[k], width=8).grid(row=1, column=2 + i * 2, sticky="w", padx=3, pady=2)
        if wall:
            ttk.Checkbutton(box, text="Wall plate (z = centre height)", variable=v["wall"]).grid(row=2, column=0, columnspan=2, sticky="w")
            ttk.Label(box, text="faces").grid(row=2, column=2, sticky="e")
            ttk.Combobox(box, textvariable=v["facing"], values=FACINGS, width=4).grid(row=2, column=3, sticky="w")
            ttk.Label(box, text="scale").grid(row=2, column=4, sticky="e")
            ttk.Entry(box, textvariable=v["scale"], width=6).grid(row=2, column=5, sticky="w")
        box.columnconfigure(2, weight=1)
        return v

    def at_of(self, v):
        return float(v["x"].get() or 0), float(v["y"].get() or 0), float(v["z"].get() or 0.1)

    def scene_uuid(self, name):
        return find("Scene", name)["uuid"]

    def spec_io(self, parent, row, collect, fill, kind):
        bar = ttk.Frame(parent)
        bar.grid(row=row, column=0, columnspan=4, sticky="ew", pady=6)
        ttk.Button(bar, text="Load spec...", command=lambda: self.load_spec(fill)).pack(side="left", padx=3)
        ttk.Button(bar, text="Save spec...", command=lambda: self.save_spec(collect, kind)).pack(side="left", padx=3)
        return bar

    def load_spec(self, fill):
        f = filedialog.askopenfilename(initialdir=str(ROOT / "foundry-tools" / "examples"), filetypes=[("JSON", "*.json")])
        if f:
            fill(json.loads(Path(f).read_text(encoding="utf-8-sig")))

    def save_spec(self, collect, kind):
        f = filedialog.asksaveasfilename(initialdir=str(ROOT / "foundry-tools" / "examples"), defaultextension=".json", filetypes=[("JSON", "*.json")])
        if f:
            Path(f).write_text(json.dumps(collect(), indent=2, ensure_ascii=False), encoding="utf-8")
            self.say(f"saved {f}")

    def scrolled(self, tab):
        """Scrollable frame inside a notebook tab."""
        cv = tk.Canvas(tab, highlightthickness=0)
        sb = ttk.Scrollbar(tab, orient="vertical", command=cv.yview)
        fr = ttk.Frame(cv)
        fr.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        win = cv.create_window((0, 0), window=fr, anchor="nw")
        cv.bind("<Configure>", lambda e: cv.itemconfigure(win, width=e.width))
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        cv.bind_all("<MouseWheel>", lambda e: cv.yview_scroll(-1 * (e.delta // 120), "units") if self.nb.select() == str(tab) else None)
        fr.columnconfigure(1, weight=1)
        fr.columnconfigure(3, weight=1)
        return fr

    # ================================================================== NPC
    def build_npc(self):
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text=" NPC ")
        f = self.scrolled(tab)
        s = self.n = {k: tk.StringVar() for k in ("name", "cr", "type", "subtype", "alignment", "hp", "hp_formula", "ac", "darkvision", "languages", "folder",
                                                  "walk", "fly", "swim", "climb", "seed", "height", "tris", "scale", "image", "model", "mode")}
        s.update(size=tk.StringVar(value="med"), disposition=tk.StringVar(value="0"), named=tk.BooleanVar(value=True), seq=tk.BooleanVar(value=True),
                 doc=tk.BooleanVar(value=True))
        for k, v in dict(cr="0.5", type="humanoid", subtype="human", alignment="neutral", hp="22", hp_formula="4d8+4", ac="12", languages="common", walk="30",
                         folder="Quest NPCs (Side Quests)", seed="29", height="1.75", tris="9000", scale="1.0", mode="none").items():
            s[k].set(v)
        labeled(f, 0, "Name", ttk.Entry(f, textvariable=s["name"]), 0, 3)
        labeled(f, 1, "CR", ttk.Entry(f, textvariable=s["cr"], width=8))
        labeled(f, 1, "Size", ttk.Combobox(f, textvariable=s["size"], values=SIZES, width=8), 2)
        labeled(f, 2, "Type", ttk.Entry(f, textvariable=s["type"]))
        labeled(f, 2, "Subtype", ttk.Entry(f, textvariable=s["subtype"]), 2)
        labeled(f, 3, "Alignment", ttk.Entry(f, textvariable=s["alignment"]))
        labeled(f, 3, "Disposition", ttk.Combobox(f, textvariable=s["disposition"], values=["-1", "0", "1"], width=6), 2)
        labeled(f, 4, "HP", ttk.Entry(f, textvariable=s["hp"], width=8))
        labeled(f, 4, "HP formula", ttk.Entry(f, textvariable=s["hp_formula"]), 2)
        labeled(f, 5, "AC", ttk.Entry(f, textvariable=s["ac"], width=8))
        labeled(f, 5, "Languages (comma)", ttk.Entry(f, textvariable=s["languages"]), 2)
        ab = ttk.LabelFrame(f, text="Ability scores")
        ab.grid(row=6, column=0, columnspan=4, sticky="ew", padx=3, pady=4)
        self.abil = []
        for i, a in enumerate(ABIL):
            ttk.Label(ab, text=a.upper()).grid(row=0, column=i * 2, padx=(8, 2))
            sp = ttk.Spinbox(ab, from_=1, to=30, width=5)
            sp.set(10)
            sp.grid(row=0, column=i * 2 + 1)
            self.abil.append(sp)
        sp_ = ttk.LabelFrame(f, text="Speed (ft) and senses")
        sp_.grid(row=7, column=0, columnspan=4, sticky="ew", padx=3, pady=4)
        for i, (k, t) in enumerate((("walk", "walk"), ("fly", "fly"), ("swim", "swim"), ("climb", "climb"), ("darkvision", "darkvision"))):
            ttk.Label(sp_, text=t).grid(row=0, column=i * 2, padx=(8, 2))
            ttk.Entry(sp_, textvariable=s[k], width=6).grid(row=0, column=i * 2 + 1)
        self.n_bio = labeled(f, 8, "Player-facing bio", text_box(f, 4), 0, 3)
        self.n_gm = labeled(f, 9, "GM notes (secrets, DCs)", text_box(f, 4), 0, 3)
        ttk.Label(f, text="Features / traits").grid(row=10, column=0, sticky="nw", padx=3)
        self.n_feat = Table(f, [("name", "Name", 160), ("text", "What it does", 520)], height=4)
        self.n_feat.grid(row=10, column=1, columnspan=3, sticky="ew", padx=3, pady=3)
        ttk.Label(f, text="Attacks").grid(row=11, column=0, sticky="nw", padx=3)
        self.n_att = Table(f, [("name", "Name", 140), ("ability", "Ability", 60), ("dice", "Dice (1d6)", 80), ("dtype", "Damage type", 110), ("bonus", "Bonus", 50),
                               ("reach", "Reach ft", 60)], choices={"ability": ABIL, "dtype": DTYPES}, height=3)
        self.n_att.grid(row=11, column=1, columnspan=3, sticky="ew", padx=3, pady=3)
        labeled(f, 12, "Actor folder", self.combo(f, s["folder"], "Actor"), 0, 3)
        ttk.Checkbutton(f, text="Linked token (named NPC; tick for single, unique characters)", variable=s["named"]).grid(row=13, column=1, columnspan=3, sticky="w")

        art_box = ttk.LabelFrame(f, text="3D token (generated from art, an existing image, or an existing model)")
        art_box.grid(row=14, column=0, columnspan=4, sticky="ew", padx=3, pady=6)
        for i, (val, txt) in enumerate((("none", "Flat icon (no 3D)"), ("prompt", "Generate from a prompt"), ("image", "Use an image file"), ("model", "Existing model file"))):
            ttk.Radiobutton(art_box, text=txt, value=val, variable=s["mode"]).grid(row=0, column=i, sticky="w", padx=4)
        ttk.Label(art_box, text="Concept prompt").grid(row=1, column=0, sticky="nw")
        self.n_prompt = text_box(art_box, 3, 70)
        self.n_prompt.grid(row=1, column=1, columnspan=3, sticky="ew", pady=2)
        set_text(self.n_prompt, "painterly fantasy character concept art, a ... standing upright, front view")
        ttk.Label(art_box, text="Image file").grid(row=2, column=0, sticky="w")
        ttk.Entry(art_box, textvariable=s["image"], width=50).grid(row=2, column=1, columnspan=2, sticky="ew")
        ttk.Button(art_box, text="Browse...", command=self.browse_image).grid(row=2, column=3, sticky="w")
        ttk.Label(art_box, text="Model file name").grid(row=3, column=0, sticky="w")
        ttk.Entry(art_box, textvariable=s["model"], width=50).grid(row=3, column=1, columnspan=2, sticky="ew")
        opt = ttk.Frame(art_box)
        opt.grid(row=4, column=0, columnspan=4, sticky="w", pady=3)
        for i, (k, t, w) in enumerate((("seed", "seed", 6), ("height", "height m", 6), ("tris", "triangles", 7), ("scale", "token scale", 6))):
            ttk.Label(opt, text=t).grid(row=0, column=i * 2, padx=(8, 2))
            ttk.Entry(opt, textvariable=s[k], width=w).grid(row=0, column=i * 2 + 1)
        ttk.Checkbutton(opt, text="Low-memory mode (slower, ~10 min)", variable=s["seq"]).grid(row=0, column=9, padx=12)
        ttk.Button(art_box, text="1. Generate concept image", command=self.npc_concept).grid(row=5, column=0, columnspan=2, sticky="w", pady=3)
        self.preview = ttk.Label(art_box, text="(preview appears here)")
        self.preview.grid(row=6, column=0, columnspan=4, sticky="w")

        self.n_place = self.place_block(f, 15, "npc")
        ttk.Checkbutton(f, text="Document in the GM guide", variable=s["doc"]).grid(row=16, column=0, columnspan=2, sticky="w", padx=3)
        bar = self.spec_io(f, 17, self.collect_npc, self.fill_npc, "npc")
        ttk.Button(bar, text="Dry run", command=lambda: self.npc_run(True)).pack(side="left", padx=12)
        ttk.Button(bar, text="Create NPC in Foundry", style="Accent.TButton", command=lambda: self.npc_run(False)).pack(side="left", padx=3)

    def browse_image(self):
        f = filedialog.askopenfilename(initialdir=str(ROOT / "foundry-3d" / "ai" / "characters"), filetypes=[("Images", "*.png *.jpg *.webp")])
        if f:
            self.n["image"].set(f)
            self.n["mode"].set("image")
            self.show_preview(f)

    def show_preview(self, path):
        try:
            from PIL import Image, ImageTk
            im = Image.open(path)
            im.thumbnail((300, 300))
            self._pv = ImageTk.PhotoImage(im)
            self.preview.configure(image=self._pv, text="")
        except Exception as e:                                           # noqa: BLE001
            self.preview.configure(text=f"(no preview: {e})")

    def collect_npc(self):
        s = self.n
        num = lambda v, d=0: (float(v) if "." in str(v) else int(v)) if str(v).strip() else d
        spec = {"name": s["name"].get().strip(), "cr": num(s["cr"].get()), "size": s["size"].get(), "type": s["type"].get(), "subtype": s["subtype"].get(),
                "alignment": s["alignment"].get(), "hp": int(s["hp"].get() or 1), "hp_formula": s["hp_formula"].get(), "ac": int(s["ac"].get() or 10),
                "abilities": [int(a.get()) for a in self.abil],
                "speed": {k: int(s[k].get()) for k in ("walk", "fly", "swim", "climb") if s[k].get().strip()},
                "senses": {"darkvision": int(s["darkvision"].get())} if s["darkvision"].get().strip() else {},
                "languages": [x.strip() for x in s["languages"].get().split(",") if x.strip()], "bio": get_text(self.n_bio), "gm_notes": get_text(self.n_gm),
                "features": self.n_feat.rows(), "attacks": [dict(r, bonus=int(r["bonus"] or 0), reach=int(r["reach"] or 5)) for r in self.n_att.rows()],
                "disposition": int(s["disposition"].get()), "named": s["named"].get(), "folder": s["folder"].get()}
        mode = s["mode"].get()
        if mode != "none":
            a = {"height": float(s["height"].get()), "seed": int(s["seed"].get()), "tris": int(s["tris"].get()), "seq_offload": s["seq"].get(), "scale": float(s["scale"].get())}
            if mode == "prompt":
                a["prompt"] = get_text(self.n_prompt)
            elif mode == "image":
                a["image"] = s["image"].get()
            else:
                a["model"] = s["model"].get()
            spec["art"] = a
        return spec

    def fill_npc(self, spec):
        s = self.n
        for k in ("name", "cr", "type", "subtype", "alignment", "hp", "hp_formula", "ac", "folder", "size", "disposition"):
            if k in spec:
                s[k].set(str(spec[k]))
        s["named"].set(spec.get("named", True))
        s["languages"].set(", ".join(spec.get("languages", [])))
        for a, v in zip(self.abil, spec.get("abilities", [10] * 6)):
            a.set(v)
        for k in ("walk", "fly", "swim", "climb"):
            s[k].set(str(spec.get("speed", {}).get(k, "")))
        s["darkvision"].set(str(spec.get("senses", {}).get("darkvision", "")))
        set_text(self.n_bio, spec.get("bio", ""))
        set_text(self.n_gm, spec.get("gm_notes", ""))
        self.n_feat.set_rows(spec.get("features", []))
        self.n_att.set_rows(spec.get("attacks", []))
        a = spec.get("art") or {}
        s["mode"].set("prompt" if a.get("prompt") else "image" if a.get("image") else "model" if a.get("model") else "none")
        set_text(self.n_prompt, a.get("prompt", get_text(self.n_prompt)))
        s["image"].set(a.get("image", ""))
        s["model"].set(a.get("model", ""))
        for k in ("seed", "height", "tris", "scale"):
            if k in a:
                s[k].set(str(a[k]))

    def npc_concept(self):
        s = self.n
        name, prompt = s["name"].get().strip(), get_text(self.n_prompt)
        if not name or not prompt:
            return messagebox.showinfo("Concept", "Give the NPC a name and a prompt first.")
        seed, seq = int(s["seed"].get()), s["seq"].get()

        def job():
            return art.concept(name, prompt, seed, seq)

        def done(path):
            if path:
                s["image"].set(str(path))
                s["mode"].set("image")
                self.show_preview(path)
                self.say("Concept image ready. If you like it, press Create; otherwise change the seed or prompt and generate again.")

        self.run_job("Generating concept image (this can take a while)", job, done)

    def npc_run(self, dry):
        try:
            spec = self.collect_npc()
        except ValueError as e:
            return messagebox.showerror("Check the fields", str(e))
        if not spec["name"]:
            return messagebox.showinfo("NPC", "Name is required.")
        pl = self.n_place
        at = self.at_of(pl) if pl["place"].get() else None
        scene_name = pl["scene"].get()

        def job():
            actor, uuid = npc.create(spec, dry=dry)
            placed = None
            if uuid and at and scene_name:
                npc.place_token(uuid, self.scene_uuid(scene_name), *at)
                placed = f"{scene_name} at {at[0]},{at[1]}"
            if uuid and self.n["doc"].get():
                docs.npc_entry(spec, uuid, placed)
                print("documented in", docs.GEN_FILE)
            return uuid

        self.run_job(("Dry run: " if dry else "Creating NPC: ") + spec["name"], job, lambda r: r and self.run_job("Refreshing", self.job_refresh))

    # ================================================================== Item
    def build_item(self):
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text=" Item ")
        f = self.scrolled(tab)
        s = self.i = {k: tk.StringVar() for k in ("name", "folder", "w", "d", "h", "color", "weight", "price", "rarity", "rev")}
        s.update(shape=tk.StringVar(value="paper"), doc=tk.BooleanVar(value=True))
        for k, v in dict(folder="Quest Items (Side Quests)", w="0.2", d="0.28", h="0.01", color="#d8c9a0", weight="0", price="0").items():
            s[k].set(v)
        labeled(f, 0, "Name", ttk.Entry(f, textvariable=s["name"]), 0, 3)
        self.i_desc = labeled(f, 1, "Player-facing description", text_box(f, 4), 0, 3)
        self.i_gm = labeled(f, 2, "GM notes (guide only)", text_box(f, 4), 0, 3)
        sh = ttk.LabelFrame(f, text="3D prop")
        sh.grid(row=3, column=0, columnspan=4, sticky="ew", padx=3, pady=6)
        ttk.Label(sh, text="Shape").grid(row=0, column=0)
        ttk.Combobox(sh, textvariable=s["shape"], values=SHAPES, width=10).grid(row=0, column=1, sticky="w")
        for i, (k, t) in enumerate((("w", "width m"), ("d", "depth m"), ("h", "height m"))):
            ttk.Label(sh, text=t).grid(row=0, column=2 + i * 2, padx=(10, 2))
            ttk.Entry(sh, textvariable=s[k], width=7).grid(row=0, column=3 + i * 2)
        ttk.Label(sh, text="Colour").grid(row=1, column=0)
        ttk.Entry(sh, textvariable=s["color"], width=10).grid(row=1, column=1, sticky="w")
        ttk.Button(sh, text="Pick...", command=self.pick_color).grid(row=1, column=2)
        ttk.Label(sh, text="Text printed on it (one line per row)").grid(row=2, column=0, columnspan=3, sticky="w")
        self.i_text = text_box(sh, 3, 50)
        self.i_text.grid(row=3, column=0, columnspan=8, sticky="ew", pady=2)
        ttk.Label(sh, text="Model revision suffix (change to bypass browser cache)").grid(row=4, column=0, columnspan=4, sticky="w")
        ttk.Entry(sh, textvariable=s["rev"], width=6).grid(row=4, column=4, sticky="w")
        labeled(f, 4, "Item folder", self.combo(f, s["folder"], "Item"), 0, 3)
        self.i_place = self.place_block(f, 5, "item", wall=True)
        ttk.Checkbutton(f, text="Document in the GM guide", variable=s["doc"]).grid(row=6, column=0, columnspan=2, sticky="w", padx=3)
        bar = self.spec_io(f, 7, self.collect_item, self.fill_item, "item")
        ttk.Button(bar, text="Dry run", command=lambda: self.item_run(True)).pack(side="left", padx=12)
        ttk.Button(bar, text="Create item in Foundry", style="Accent.TButton", command=lambda: self.item_run(False)).pack(side="left", padx=3)

    def pick_color(self):
        c = colorchooser.askcolor(color=self.i["color"].get())[1]
        if c:
            self.i["color"].set(c)

    def collect_item(self):
        s = self.i
        spec = {"name": s["name"].get().strip(), "description": get_text(self.i_desc), "gm_notes": get_text(self.i_gm), "shape": s["shape"].get(),
                "w": float(s["w"].get()), "d": float(s["d"].get()), "h": float(s["h"].get()), "color": s["color"].get(), "folder": s["folder"].get(),
                "wall": self.i_place["wall"].get() or s["shape"].get() == "plate"}
        if get_text(self.i_text):
            spec["text"] = get_text(self.i_text)
        if s["rev"].get().strip():
            spec["rev"] = s["rev"].get().strip()
        return spec

    def fill_item(self, spec):
        s = self.i
        for k in ("name", "folder", "w", "d", "h", "color", "shape", "rev"):
            if k in spec:
                s[k].set(str(spec[k]))
        set_text(self.i_desc, spec.get("description", ""))
        set_text(self.i_gm, spec.get("gm_notes", ""))
        set_text(self.i_text, spec.get("text", ""))
        self.i_place["wall"].set(bool(spec.get("wall")))

    def item_run(self, dry):
        try:
            spec = self.collect_item()
        except ValueError as e:
            return messagebox.showerror("Check the fields", str(e))
        if not spec["name"]:
            return messagebox.showinfo("Item", "Name is required.")
        pl = self.i_place
        at = self.at_of(pl) if pl["place"].get() else None
        scene_name, wall, facing, scale = pl["scene"].get(), pl["wall"].get(), pl["facing"].get(), float(pl["scale"].get() or 3)

        def job():
            it, uuid, model = item.create(spec, dry=dry)
            placed = None
            if uuid and at and scene_name:
                item.place_tile(uuid, self.scene_uuid(scene_name), *at, model, wall=wall, facing=facing, scale=scale)
                placed = f"{scene_name} at {at[0]},{at[1]},{at[2]}" + (" (wall)" if wall else "")
            if uuid and self.i["doc"].get():
                docs.item_entry(spec, uuid, placed)
                print("documented in", docs.GEN_FILE)
            return uuid

        self.run_job(("Dry run: " if dry else "Creating item: ") + spec["name"], job, lambda r: r and self.run_job("Refreshing", self.job_refresh))

    # ================================================================== Scene
    def build_scene(self):
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text=" Scene ")
        f = ttk.Frame(tab, padding=8)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)
        s = self.s = {k: tk.StringVar() for k in ("generator", "name", "folder", "playlist", "door")}
        s.update(vision=tk.BooleanVar(value=False), rebuild=tk.BooleanVar(value=True), doc=tk.BooleanVar(value=True))
        s["folder"].set("The Ossuary Exchange")
        s["door"].set("woodCreaky")
        gens = sorted(p.stem for p in GEN.glob("*.py") if not p.stem.startswith("_") and not p.stem.startswith(("token_", "item_")))
        labeled(f, 0, "Generator", ttk.Combobox(f, textvariable=s["generator"], values=gens, width=40))
        labeled(f, 1, "Scene name", ttk.Entry(f, textvariable=s["name"]))
        labeled(f, 2, "Scene folder", self.combo(f, s["folder"], "Scene"))
        labeled(f, 3, "Playlist", self.combo(f, s["playlist"], "Playlist"))
        labeled(f, 4, "Door sound", ttk.Combobox(f, textvariable=s["door"], values=DOORS))
        ttk.Checkbutton(f, text="Token vision ON (default off = whole scene visible, better performance)", variable=s["vision"]).grid(row=5, column=1, sticky="w")
        ttk.Checkbutton(f, text="Rebuild the model first (untick to reuse the existing .glb)", variable=s["rebuild"]).grid(row=6, column=1, sticky="w")
        ttk.Checkbutton(f, text="Document in the GM guide", variable=s["doc"]).grid(row=7, column=1, sticky="w")
        ttk.Label(f, text="Existing scenes are never changed or deleted; delete old versions by hand in Foundry.", foreground="#666").grid(row=8, column=1, sticky="w", pady=6)
        ttk.Button(f, text="Build model and create scene", style="Accent.TButton", command=self.scene_run).grid(row=9, column=1, sticky="w", pady=8)

    def scene_run(self):
        s = self.s
        if not s["generator"].get() or not s["name"].get().strip():
            return messagebox.showinfo("Scene", "Pick a generator and give the scene a name.")
        a = dict(generator=s["generator"].get(), name=s["name"].get().strip(), folder=s["folder"].get(), playlist=s["playlist"].get() or None,
                 door_sound=s["door"].get(), vision=s["vision"].get(), rebuild=s["rebuild"].get())

        def job():
            uuid = scene.create(**a)
            if s["doc"].get():
                docs.scene_entry(a["name"], a["generator"], uuid)
                print("documented in", docs.GEN_FILE)
            return uuid

        self.run_job("Creating scene " + a["name"], job, lambda r: r and self.run_job("Refreshing", self.job_refresh))

    # ================================================================== Encounter
    def build_encounter(self):
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text=" Encounter ")
        f = self.scrolled(tab)
        s = self.e = {k: tk.StringVar() for k in ("name", "scene")}
        s["doc"] = tk.BooleanVar(value=True)
        labeled(f, 0, "Encounter name", ttk.Entry(f, textvariable=s["name"]), 0, 3)
        labeled(f, 1, "Scene", self.combo(f, s["scene"], "Scene"), 0, 3)
        self.e_sum = labeled(f, 2, "What the players see", text_box(f, 3), 0, 3)
        self.e_tac = labeled(f, 3, "Tactics", text_box(f, 3), 0, 3)
        self.e_rew = labeled(f, 4, "Rewards", text_box(f, 2), 0, 3)
        self.e_gm = labeled(f, 5, "GM notes", text_box(f, 3), 0, 3)
        ttk.Label(f, text="Foes (actor name must match one in Foundry)").grid(row=6, column=0, columnspan=4, sticky="w", padx=3, pady=(8, 0))
        self.e_foes = Table(f, [("actor", "Actor", 220), ("count", "Count", 60), ("x", "x (m)", 70), ("y", "y (m)", 70), ("spread", "Spread m", 70), ("hidden", "Hidden", 60)],
                            choices={"hidden": ["no", "yes"]}, height=5)
        self.e_foes.grid(row=7, column=0, columnspan=4, sticky="ew", padx=3)
        self.actor_cb = None
        ttk.Checkbutton(f, text="Document in the GM guide", variable=s["doc"]).grid(row=8, column=0, columnspan=2, sticky="w", padx=3, pady=4)
        bar = self.spec_io(f, 9, self.collect_enc, self.fill_enc, "encounter")
        ttk.Button(bar, text="Dry run", command=lambda: self.enc_run(True)).pack(side="left", padx=12)
        ttk.Button(bar, text="Place foes and write journal", style="Accent.TButton", command=lambda: self.enc_run(False)).pack(side="left", padx=3)

    def collect_enc(self):
        foes = []
        for r in self.e_foes.rows():
            foes.append({"actor": r["actor"], "count": int(r["count"] or 1), "at": [float(r["x"] or 0), float(r["y"] or 0)], "spread": float(r["spread"] or 1.2),
                         "hidden": r["hidden"] == "yes"})
        return {"name": self.e["name"].get().strip(), "scene": self.e["scene"].get(), "summary": get_text(self.e_sum), "tactics": get_text(self.e_tac),
                "rewards": get_text(self.e_rew), "gm_notes": get_text(self.e_gm), "foes": foes}

    def fill_enc(self, spec):
        self.e["name"].set(spec.get("name", ""))
        self.e["scene"].set(spec.get("scene", ""))
        for w, k in ((self.e_sum, "summary"), (self.e_tac, "tactics"), (self.e_rew, "rewards"), (self.e_gm, "gm_notes")):
            set_text(w, spec.get(k, ""))
        self.e_foes.set_rows([{"actor": f["actor"], "count": f.get("count", 1), "x": f["at"][0], "y": f["at"][1], "spread": f.get("spread", 1.2),
                               "hidden": "yes" if f.get("hidden") else "no"} for f in spec.get("foes", [])])

    def enc_run(self, dry):
        try:
            spec = self.collect_enc()
        except ValueError as e:
            return messagebox.showerror("Check the fields", str(e))
        if not spec["name"] or not spec["scene"] or not spec["foes"]:
            return messagebox.showinfo("Encounter", "Name, scene and at least one foe are required.")

        def job():
            uuid = encounter.create(spec, dry=dry)
            if uuid and self.e["doc"].get():
                docs.encounter_entry(spec, uuid)
                print("documented in", docs.GEN_FILE)

        self.run_job(("Dry run: " if dry else "Encounter: ") + spec["name"], job)

    # ================================================================== Place
    def build_place(self):
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text=" Place / Where ")
        f = ttk.Frame(tab, padding=8)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)
        s = self.p = {k: tk.StringVar() for k in ("kind", "thing")}
        s["kind"].set("actor")
        s["hidden"] = tk.BooleanVar(value=False)
        ttk.Radiobutton(f, text="Actor (token)", value="actor", variable=s["kind"]).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(f, text="Item (model tile)", value="item", variable=s["kind"]).grid(row=0, column=1, sticky="w")
        self.p_actor = ttk.Combobox(f, textvariable=s["thing"], width=40)
        self.combos.append((self.p_actor, "Actor"))
        labeled(f, 1, "Name", self.p_actor)
        ttk.Checkbutton(f, text="Hidden token", variable=s["hidden"]).grid(row=2, column=1, sticky="w")
        self.p_block = self.place_block(f, 3, "place", wall=True)
        self.p_block["place"].set(True)
        bar = ttk.Frame(f)
        bar.grid(row=4, column=0, columnspan=4, sticky="w", pady=6)
        ttk.Button(bar, text="Place it", style="Accent.TButton", command=self.place_run).pack(side="left", padx=3)
        ttk.Button(bar, text="Where? (convert metres to pixels)", command=self.where_run).pack(side="left", padx=10)
        ttk.Label(f, text="Coordinates are the same metres used inside the generator file; the tool applies the model's recentring shift.", foreground="#666").grid(
            row=5, column=0, columnspan=4, sticky="w")
        s["kind"].trace_add("write", lambda *a: self.p_actor.configure(values=self.cache["Actor" if s["kind"].get() == "actor" else "Item"]))

    def place_run(self):
        s, b = self.p, self.p_block
        name, scene_name = s["thing"].get().strip(), b["scene"].get()
        if not name or not scene_name:
            return messagebox.showinfo("Place", "Pick what to place and the scene.")
        x, y, z = self.at_of(b)
        kind, hidden, wall, facing, scale = s["kind"].get(), s["hidden"].get(), b["wall"].get(), b["facing"].get(), float(b["scale"].get() or 3)

        def job():
            sc = self.scene_uuid(scene_name)
            if kind == "actor":
                npc.place_token(find("Actor", name)["uuid"], sc, x, y, z, hidden=hidden)
            else:
                row = find("Item", name)
                model = bridge("get", uuid=row["uuid"])["flags"]["levels-3d-preview"]["model3d"].split("/")[-1]
                item.place_tile(row["uuid"], sc, x, y, z, model, wall=wall, facing=facing, scale=scale)

        self.run_job(f"Placing {name}", job)

    def where_run(self):
        b = self.p_block
        if not b["scene"].get():
            return messagebox.showinfo("Where", "Pick a scene.")
        x, y, z = self.at_of(b)

        def job():
            fr = scene_frame(self.scene_uuid(b["scene"].get()))
            print("pixels / elevation:", to_scene(fr, x, y, z))

        self.run_job("Converting coordinates", job)

    # ================================================================== Publish
    def build_publish(self):
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text=" Publish ")
        f = ttk.Frame(tab, padding=8)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)
        self.msg = tk.StringVar(value="Add new Varrenmoor content")
        self.push = tk.BooleanVar(value=True)
        labeled(f, 0, "Commit message", ttk.Entry(f, textvariable=self.msg))
        ttk.Checkbutton(f, text="Push to GitHub after committing", variable=self.push).grid(row=1, column=1, sticky="w")
        bar = ttk.Frame(f)
        bar.grid(row=2, column=1, sticky="w", pady=8)
        ttk.Button(bar, text="Show git status", command=self.git_status).pack(side="left", padx=3)
        ttk.Button(bar, text="Commit and push", style="Accent.TButton", command=self.git_commit).pack(side="left", padx=10)
        ttk.Button(bar, text="Open generated-content guide", command=lambda: self.open_path(docs.GEN_FILE)).pack(side="left", padx=3)
        ttk.Label(f, text="Commits the GM guide, foundry-tools, generators and textures only.", foreground="#666").grid(row=3, column=1, sticky="w")

    def git_status(self):
        def job():
            r = subprocess.run(["git", "status", "--short"], cwd=str(ROOT), capture_output=True, text=True)
            print(r.stdout or "clean")
        self.run_job("git status", job)

    def git_commit(self):
        msg, push = self.msg.get().strip(), self.push.get()
        if not msg:
            return messagebox.showinfo("Publish", "Write a commit message.")
        if not messagebox.askyesno("Publish", "Commit" + (" and push to GitHub" if push else "") + "?"):
            return
        self.run_job("Publishing", lambda: docs.commit(msg, push=push))


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
