"""
Debug UI — OCR Region Calibrator & Plugin Manager

Run via debug_ui.bat. Do NOT run alongside the main app (both would use EasyOCR).

Left panel : plugin toggles, region list, coordinate readout, action buttons
Right panel: scaled screenshot with colour-coded draggable OCR region boxes
             Scroll wheel to zoom · Right-click drag to pan · Double-click empty space to reset zoom
Bottom bar : live OCR result for the selected region
"""

import os
import sys
import threading
import yaml
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from typing import List, Optional

# ── Path setup ───────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent.parent   # project root

sys.path.insert(0, str(_ROOT / "src"))

try:
    import mss
    MSS_OK = True
except ImportError:
    MSS_OK = False

try:
    from PIL import Image, ImageTk
    PIL_OK = True
except ImportError:
    PIL_OK = False

# ── Constants ────────────────────────────────────────────────────────────────
CANVAS_W, CANVAS_H = 960, 540
HANDLE  = 9         # half-size of corner drag handles in canvas pixels
ZOOM_MIN, ZOOM_MAX = 1.0, 10.0
COLORS  = ["#FF5555", "#55FF99", "#5599FF", "#FFDD55", "#FF55FF", "#55FFFF", "#FF9955"]

DEFAULT_REGIONS = [
    {"name": "player_kills",   "bbox": [820, 1197, 50, 64], "event_type": "screen.player_kills"},
    {"name": "player_deaths",  "bbox": [877, 1197, 50, 64], "event_type": "screen.player_deaths"},
    {"name": "player_assists", "bbox": [934, 1197, 50, 64], "event_type": "screen.player_assists"},
    {"name": "game_timer",     "bbox": [880, 15,  160, 45], "event_type": "screen.timer"},
]

# Add new plugins here as you create them
KNOWN_PLUGINS = ["death_sounds", "kill_tracker"]

REGIONS_FILE = _ROOT / "config" / "regions.yaml"
PLUGINS_FILE = _ROOT / "config" / "plugins.yaml"


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────
class RegionData:
    def __init__(self, name: str, bbox: list, event_type: str, color: str):
        self.name = name
        self.bbox = list(bbox)      # [left, top, width, height] in screen pixels
        self.event_type = event_type
        self.color = color

    def to_dict(self):
        return {"bbox": list(self.bbox), "event_type": self.event_type}


# ─────────────────────────────────────────────────────────────────────────────
# Canvas with draggable region boxes, scroll-zoom, and right-click pan
# ─────────────────────────────────────────────────────────────────────────────
class RegionCanvas(tk.Canvas):
    """
    Displays a screenshot with draggable OCR region overlays.

    Navigation:
      Scroll wheel         — zoom in/out centred on cursor
      Right-click drag     — pan
      Double-click (empty) — reset zoom to fit
    """

    def __init__(self, master, regions: List[RegionData], base_scale: float,
                 on_select, on_view_change=None, **kw):
        super().__init__(master, **kw)
        self.regions    = regions
        self.base_scale = base_scale   # screen→canvas scale at zoom 1
        self.on_select  = on_select
        self.on_view_change = on_view_change

        self._photo: Optional[ImageTk.PhotoImage] = None
        self._pil_full: Optional[Image.Image] = None

        self._drag      = None   # region drag state
        self._pan_drag  = None   # pan drag state
        self._selected: Optional[str] = None

        self._zoom = 1.0
        self._ox   = 0.0   # pan offset in screen pixels
        self._oy   = 0.0

        self.bind("<ButtonPress-1>",    self._on_press)
        self.bind("<B1-Motion>",        self._on_motion)
        self.bind("<ButtonRelease-1>",  self._on_release)

        self.bind("<ButtonPress-3>",    self._on_pan_press)
        self.bind("<B3-Motion>",        self._on_pan_motion)
        self.bind("<ButtonRelease-3>",  self._on_pan_release)

        self.bind("<ButtonPress-2>",    self._on_pan_press)
        self.bind("<B2-Motion>",        self._on_pan_motion)
        self.bind("<ButtonRelease-2>",  self._on_pan_release)

        self.bind("<MouseWheel>",       self._on_wheel)   # Windows
        self.bind("<Button-4>",         self._on_wheel)   # Linux up
        self.bind("<Button-5>",         self._on_wheel)   # Linux down

        self.bind("<Double-Button-1>",  self._on_double_click)

    # ── Coordinate helpers ──────────────────────────────────────────────────

    def _s2c(self, sx, sy):
        """Screen pixels → canvas pixels."""
        f = self.base_scale * self._zoom
        return (sx - self._ox) * f, (sy - self._oy) * f

    def _c2s(self, cx, cy):
        """Canvas pixels → screen pixels."""
        f = self.base_scale * self._zoom
        return cx / f + self._ox, cy / f + self._oy

    @property
    def zoom(self):
        return self._zoom

    # ── Image ───────────────────────────────────────────────────────────────

    def set_full_image(self, pil_img: Image.Image):
        self._pil_full = pil_img
        self._update_image()

    def _update_image(self):
        if self._pil_full is None:
            return
        W, H = int(self.cget("width")), int(self.cget("height"))
        f = self.base_scale * self._zoom
        vis_w = W / f
        vis_h = H / f
        img_w, img_h = self._pil_full.size
        left   = max(0, self._ox)
        top    = max(0, self._oy)
        right  = min(img_w, left  + vis_w)
        bottom = min(img_h, top   + vis_h)
        cropped = self._pil_full.crop((int(left), int(top), int(right), int(bottom)))
        scaled  = cropped.resize((W, H), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(scaled)
        self.delete("all")
        self.create_image(0, 0, anchor="nw", image=self._photo)
        self.redraw()

    # ── Region drawing ───────────────────────────────────────────────────────

    def redraw(self):
        self.delete("region")
        for r in self.regions:
            self._draw_one(r)

    def select(self, name: Optional[str]):
        self._selected = name
        self.redraw()

    def _draw_one(self, r: RegionData):
        l, t, w, h = r.bbox
        x1, y1 = self._s2c(l,     t)
        x2, y2 = self._s2c(l + w, t + h)
        lw = 3 if r.name == self._selected else 2
        self.create_rectangle(x1, y1, x2, y2, outline=r.color, width=lw, tags="region")
        self.create_text(x1 + 5, y1 + 14, text=r.name, anchor="w",
                         fill=r.color, font=("Consolas", 9, "bold"), tags="region")
        for cx, cy in [(x1,y1),(x2,y1),(x2,y2),(x1,y2)]:
            self.create_rectangle(cx-HANDLE, cy-HANDLE, cx+HANDLE, cy+HANDLE,
                                  fill=r.color, outline="white", tags="region")

    # ── Hit testing ──────────────────────────────────────────────────────────

    def _hit(self, x, y):
        """Return (region_name, mode) or None. mode: move | tl | tr | br | bl"""
        hs = HANDLE * 1.5
        for r in self.regions:
            l, t, w, h = r.bbox
            x1, y1 = self._s2c(l,     t)
            x2, y2 = self._s2c(l + w, t + h)
            for corner, (cx, cy) in [("tl",(x1,y1)),("tr",(x2,y1)),
                                      ("br",(x2,y2)),("bl",(x1,y2))]:
                if abs(x - cx) <= hs and abs(y - cy) <= hs:
                    return r.name, corner
        for r in self.regions:
            l, t, w, h = r.bbox
            x1, y1 = self._s2c(l,     t)
            x2, y2 = self._s2c(l + w, t + h)
            if x1 < x < x2 and y1 < y < y2:
                return r.name, "move"
        return None

    # ── Region drag ──────────────────────────────────────────────────────────

    def _on_press(self, e):
        hit = self._hit(e.x, e.y)
        if not hit:
            return
        name, mode = hit
        r = next(x for x in self.regions if x.name == name)
        sx, sy = self._c2s(e.x, e.y)
        self._drag = {"r": r, "mode": mode,
                      "sx": sx, "sy": sy, "orig": list(r.bbox)}
        self._selected = name
        self.on_select(name)
        self.redraw()

    def _on_motion(self, e):
        if not self._drag:
            return
        d  = self._drag
        r  = d["r"]
        sx, sy = self._c2s(e.x, e.y)
        dx = sx - d["sx"]
        dy = sy - d["sy"]
        ol, ot, ow, oh = d["orig"]
        m = d["mode"]

        if   m == "move": r.bbox[0]=int(ol+dx);        r.bbox[1]=int(ot+dy)
        elif m == "tl":   r.bbox[0]=int(ol+dx);        r.bbox[1]=int(ot+dy); r.bbox[2]=max(4,int(ow-dx)); r.bbox[3]=max(4,int(oh-dy))
        elif m == "tr":   r.bbox[1]=int(ot+dy);        r.bbox[2]=max(4,int(ow+dx)); r.bbox[3]=max(4,int(oh-dy))
        elif m == "br":   r.bbox[2]=max(4,int(ow+dx)); r.bbox[3]=max(4,int(oh+dy))
        elif m == "bl":   r.bbox[0]=int(ol+dx);        r.bbox[2]=max(4,int(ow-dx)); r.bbox[3]=max(4,int(oh+dy))

        self.redraw()
        self.on_select(r.name)

    def _on_release(self, e):
        self._drag = None

    # ── Pan ──────────────────────────────────────────────────────────────────

    def _on_pan_press(self, e):
        self._pan_drag = {"cx": e.x, "cy": e.y, "ox": self._ox, "oy": self._oy}
        self.config(cursor="fleur")

    def _on_pan_motion(self, e):
        if not self._pan_drag:
            return
        d = self._pan_drag
        f = self.base_scale * self._zoom
        self._ox = d["ox"] - (e.x - d["cx"]) / f
        self._oy = d["oy"] - (e.y - d["cy"]) / f
        self._clamp_pan()
        self._update_image()
        if self.on_view_change:
            self.on_view_change()

    def _on_pan_release(self, e):
        self._pan_drag = None
        self.config(cursor="")

    # ── Zoom ─────────────────────────────────────────────────────────────────

    def _on_wheel(self, e):
        if e.num == 4 or e.delta > 0:
            factor = 1.2
        else:
            factor = 1 / 1.2
        new_zoom = max(ZOOM_MIN, min(ZOOM_MAX, self._zoom * factor))
        if new_zoom == self._zoom:
            return
        # Keep the screen point under the cursor fixed after zoom
        sx, sy   = self._c2s(e.x, e.y)
        self._zoom = new_zoom
        self._ox = sx - e.x / (self.base_scale * self._zoom)
        self._oy = sy - e.y / (self.base_scale * self._zoom)
        self._clamp_pan()
        self._update_image()
        if self.on_view_change:
            self.on_view_change()

    def _on_double_click(self, e):
        if not self._hit(e.x, e.y):
            self.reset_zoom()

    def reset_zoom(self):
        self._zoom = 1.0
        self._ox   = 0.0
        self._oy   = 0.0
        self._update_image()
        if self.on_view_change:
            self.on_view_change()

    def _clamp_pan(self):
        if self._pil_full is None:
            return
        img_w, img_h = self._pil_full.size
        W = int(self.cget("width"))
        H = int(self.cget("height"))
        f = self.base_scale * self._zoom
        self._ox = max(0.0, min(self._ox, img_w - W / f))
        self._oy = max(0.0, min(self._oy, img_h - H / f))


# ─────────────────────────────────────────────────────────────────────────────
# Main application
# ─────────────────────────────────────────────────────────────────────────────
class DebugApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Smite Plugin Base — Debug UI")
        self.configure(bg="#1e1e1e")
        self.resizable(False, False)

        self._ocr_reader  = None
        self._ocr_loading = False

        # Base scale: fit primary monitor into CANVAS_W × CANVAS_H
        if MSS_OK:
            with mss.mss() as sct:
                mon = sct.monitors[1]
                self.base_scale = CANVAS_W / mon["width"]
        else:
            self.base_scale = CANVAS_W / 1920

        self.regions = self._load_regions()
        plugin_states = self._load_plugins()
        self.plugin_vars: dict = {}
        self._screenshot_pil = None

        self._build_ui(plugin_states)
        self._refresh_screenshot()

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build_ui(self, plugin_states: dict):
        SIDE_W = 230
        BG     = "#252526"
        FG     = "#cccccc"
        ACCENT = "#0e639c"
        GREEN  = "#4e8c4e"
        FONT   = ("Consolas", 10)
        LABEL  = ("Arial", 8, "bold")

        def section(parent, text):
            tk.Label(parent, text=text, bg=BG, fg="#888888", font=LABEL).pack(anchor="w", pady=(6,2))

        # ── Sidebar ──────────────────────────────────────────────────────────
        side = tk.Frame(self, bg=BG, width=SIDE_W, padx=10, pady=10)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        section(side, "PLUGINS")
        for name in KNOWN_PLUGINS:
            var = tk.BooleanVar(value=plugin_states.get(name, True))
            self.plugin_vars[name] = var
            tk.Checkbutton(side, text=name, variable=var,
                           bg=BG, fg=FG, selectcolor=BG,
                           activebackground=BG, activeforeground="#fff",
                           font=FONT).pack(anchor="w")

        ttk.Separator(side).pack(fill="x", pady=6)
        section(side, "OCR REGIONS")

        self._listbox = tk.Listbox(side, height=len(self.regions),
                                   bg="#1e1e1e", fg=FG,
                                   selectbackground="#094771",
                                   font=FONT, bd=0, highlightthickness=0)
        for r in self.regions:
            self._listbox.insert("end", f"  {r.name}")
        self._listbox.pack(fill="x")
        self._listbox.bind("<<ListboxSelect>>", self._on_listbox_select)

        ttk.Separator(side).pack(fill="x", pady=6)

        self._coords = tk.Label(side, text="Click a region to select it",
                                bg=BG, fg="#aaaaaa", font=("Consolas", 9),
                                justify="left")
        self._coords.pack(anchor="w")

        ttk.Separator(side).pack(fill="x", pady=6)

        def btn(parent, label, cmd, color=ACCENT):
            tk.Button(parent, text=label, command=cmd,
                      bg=color, fg="white", relief="flat",
                      padx=8, pady=5, activebackground=color,
                      cursor="hand2", font=("Arial", 9)).pack(fill="x", pady=2)

        btn(side, "⟳  Refresh Screenshot",    self._refresh_screenshot)
        btn(side, "⤢  Reset Zoom",             self._reset_zoom)
        self._ocr_btn = tk.Button(side, text="🔍  Test OCR on Selected",
                                  command=self._test_ocr,
                                  bg=ACCENT, fg="white", relief="flat",
                                  padx=8, pady=5, activebackground=ACCENT,
                                  cursor="hand2", font=("Arial", 9))
        self._ocr_btn.pack(fill="x", pady=2)
        btn(side, "💾  Save Changes", self._save, color=GREEN)

        self._status = tk.Label(side, text="", bg=BG, fg="#6dbf67",
                                font=("Consolas", 9), wraplength=SIDE_W - 20,
                                justify="left")
        self._status.pack(anchor="w", pady=4)

        # ── Right: canvas + info bar ──────────────────────────────────────────
        right = tk.Frame(self, bg="#1e1e1e")
        right.pack(side="right")

        self.canvas = RegionCanvas(
            right, self.regions, self.base_scale,
            self._on_region_select,
            on_view_change=self._on_view_change,
            width=CANVAS_W, height=CANVAS_H,
            bg="#111111", highlightthickness=0,
        )
        self.canvas.pack()

        # Bottom info bar: zoom level left, OCR result right
        bar = tk.Frame(right, bg="#1e1e1e")
        bar.pack(fill="x", padx=8, pady=4)

        self._zoom_label = tk.Label(bar, text="Zoom: 1.0×",
                                    bg="#1e1e1e", fg="#888888",
                                    font=("Consolas", 9))
        self._zoom_label.pack(side="left")

        self._ocr_result = tk.Label(
            bar, text="Scroll to zoom · Right-drag to pan · Double-click empty to reset",
            bg="#1e1e1e", fg="#555555",
            font=("Consolas", 9), justify="left",
        )
        self._ocr_result.pack(side="left", padx=12)

    # ── Data I/O ──────────────────────────────────────────────────────────────

    def _load_regions(self) -> List[RegionData]:
        data = DEFAULT_REGIONS[:]
        if REGIONS_FILE.exists():
            with open(REGIONS_FILE) as f:
                saved = yaml.safe_load(f) or {}
            data = [{"name": n, "bbox": v["bbox"], "event_type": v["event_type"]}
                    for n, v in saved.items()]
        return [RegionData(d["name"], d["bbox"], d["event_type"], COLORS[i % len(COLORS)])
                for i, d in enumerate(data)]

    def _load_plugins(self) -> dict:
        if PLUGINS_FILE.exists():
            with open(PLUGINS_FILE) as f:
                return yaml.safe_load(f) or {}
        return {n: True for n in KNOWN_PLUGINS}

    # ── Actions ───────────────────────────────────────────────────────────────

    def _refresh_screenshot(self):
        if not MSS_OK or not PIL_OK:
            self._status.config(text="⚠ mss/Pillow not installed")
            return
        with mss.mss() as sct:
            mon = sct.monitors[1]
            shot = sct.grab(mon)
            self._screenshot_pil = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        self.canvas.set_full_image(self._screenshot_pil)
        self._status.config(text="Screenshot refreshed.")

    def _reset_zoom(self):
        self.canvas.reset_zoom()

    def _on_view_change(self):
        self._zoom_label.config(text=f"Zoom: {self.canvas.zoom:.1f}×")

    def _on_region_select(self, name: str):
        r = next((x for x in self.regions if x.name == name), None)
        if r:
            l, t, w, h = r.bbox
            self._coords.config(text=f"{name}\nL: {l}  T: {t}\nW: {w}  H: {h}")
        names = [x.name for x in self.regions]
        if name in names:
            idx = names.index(name)
            self._listbox.selection_clear(0, "end")
            self._listbox.selection_set(idx)

    def _on_listbox_select(self, _event):
        sel = self._listbox.curselection()
        if sel:
            name = self.regions[sel[0]].name
            self.canvas.select(name)
            self._on_region_select(name)

    def _test_ocr(self):
        if not self.canvas._selected:
            self._status.config(text="Select a region first.")
            return
        if self._screenshot_pil is None:
            self._status.config(text="Take a screenshot first.")
            return
        if self._ocr_loading:
            return
        self._ocr_loading = True
        self._ocr_btn.config(text="⏳  Running OCR...", state="disabled")
        self._ocr_result.config(text="Running OCR on screenshot region...", fg="#aaaaaa")
        threading.Thread(target=self._run_ocr, daemon=True).start()

    def _run_ocr(self):
        try:
            if self._ocr_reader is None:
                self.after(0, lambda: self._ocr_result.config(
                    text="Initialising EasyOCR (first run takes ~30s)...", fg="#aaaaaa"))
                import easyocr
                self._ocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)

            name = self.canvas._selected
            r = next(x for x in self.regions if x.name == name)
            l, t, w, h = r.bbox

            import numpy as np
            import cv2
            region_img = self._screenshot_pil.crop((l, t, l + w, t + h))
            arr = np.array(region_img)

            DIGIT_EVENTS = {"screen.player_kills", "screen.player_deaths", "screen.player_assists"}
            is_digit = r.event_type in DIGIT_EVENTS

            if is_digit:
                # Greyscale, upscale 4× minimum, OTSU threshold
                grey = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
                rh, rw = grey.shape[:2]
                sc = max(80 / rh, 80 / rw, 4.0)
                grey = cv2.resize(grey, (int(rw * sc), int(rh * sc)), interpolation=cv2.INTER_LANCZOS4)
                _, arr = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                result = self._ocr_reader.readtext(arr, allowlist="0123456789", detail=1)
            else:
                result = self._ocr_reader.readtext(arr)

            text    = " | ".join(x[1] for x in result).strip() or "(nothing detected)"
            conf    = [round(x[2], 2) for x in result]
            display = f"[{name}]  \"{text}\"   confidence: {conf}"
            self.after(0, lambda: self._ocr_result.config(text=display, fg="#6dbf67"))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._ocr_result.config(text=f"Error: {err}", fg="#f14c4c"))
        finally:
            self._ocr_loading = False
            self.after(0, lambda: self._ocr_btn.config(
                text="🔍  Test OCR on Selected", state="normal"))

    def _save(self):
        REGIONS_FILE.parent.mkdir(exist_ok=True)

        with open(REGIONS_FILE, "w") as f:
            yaml.dump({r.name: r.to_dict() for r in self.regions}, f,
                      default_flow_style=False, sort_keys=False)

        with open(PLUGINS_FILE, "w") as f:
            yaml.dump({n: bool(v.get()) for n, v in self.plugin_vars.items()}, f,
                      default_flow_style=False)

        self._status.config(text="✓ Saved!\nRestart the main app\nto apply plugin changes.")


# ─────────────────────────────────────────────────────────────────────────────
def main():
    missing = []
    if not PIL_OK:
        missing.append("Pillow  (pip install Pillow)")
    if not MSS_OK:
        missing.append("mss     (pip install mss)")
    if missing:
        print("ERROR — missing dependencies:\n  " + "\n  ".join(missing))
        input("Press Enter to exit...")
        return
    DebugApp().mainloop()


if __name__ == "__main__":
    main()

