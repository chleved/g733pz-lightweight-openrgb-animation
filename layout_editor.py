"""
OpenRGB Keyboard Layout Editor
Visual interactive editor to reorganize position (X, Y) and dimensions (Width, Height) of each key.
Supports single-key editing and multi-key selection via marquee drag-selection box, group dragging, and batch alignment.
Saves directly to layout_coords.json which is loaded by animation.py.
"""

import copy
import json
import os
import sys
import tkinter as tk
from tkinter import messagebox, ttk

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

LAYOUT_FILE = os.path.join(SCRIPT_DIR, "layout_coords.json")

try:
    from animation import KB_LAYOUT
except ImportError:
    KB_LAYOUT = []


def generate_default_coords():
    """Generates clean default coordinates from KB_LAYOUT."""
    coords = {}
    UNIT = 44
    GAP = 4
    ROW_H = 34
    
    y = 15
    for r_idx, row in enumerate(KB_LAYOUT):
        x = 15
        h = ROW_H
        if r_idx == 0:
            h = 26
            x = 15 + int(UNIT * 1.5)
        elif r_idx == 7:
            h = 24
            x = 80
            
        for key_id, label, width_mult in row:
            if not key_id or key_id.startswith("spacer_"):
                x += int(width_mult * UNIT) + GAP
                continue
            
            w = int(width_mult * UNIT)
            if width_mult > 1.0:
                w += int((width_mult - 1) * GAP)
                
            coords[key_id] = {
                "label": label,
                "x": x,
                "y": y,
                "w": w,
                "h": h
            }
            x += w + GAP
            
        y += h + GAP + (6 if r_idx in (0, 1, 6) else 2)

    return coords


class LayoutEditorUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("OpenRGB Keyboard Layout & Offset Editor")
        self.root.geometry("1380x760")
        self.root.configure(bg="#18181B")

        self.coords: dict[str, dict] = {}
        self.selected_keys: set[str] = set()

        # Undo / Redo Stacks
        self.history: list[dict] = []
        self.redo_stack: list[dict] = []
        self.max_history: int = 50
        self.is_dragging_committed: bool = False
        
        # Dragging / Interaction State
        self.drag_mode: str | None = None  # "move", "resize", or "marquee"
        self.drag_start_x: float = 0.0
        self.drag_start_y: float = 0.0
        self.marquee_start: tuple[float, float] = (0.0, 0.0)
        self.initial_positions: dict[str, tuple[int, int]] = {}
        self.initial_key_geom: dict = {}
        self.initial_selected_keys: set[str] = set()

        self.snap_grid_var = tk.BooleanVar(value=True)
        self.grid_size_var = tk.IntVar(value=5)

        self.load_coords()
        self._build_ui()
        self._bind_keys()
        self.draw_all_keys()

    @property
    def primary_selected_key(self) -> str | None:
        """Returns the single selected key if exactly one is selected, else None."""
        if len(self.selected_keys) == 1:
            return next(iter(self.selected_keys))
        return None

    def load_coords(self):
        if os.path.exists(LAYOUT_FILE):
            try:
                with open(LAYOUT_FILE, "r", encoding="utf-8") as f:
                    self.coords = json.load(f)
                    return
            except Exception as e:
                print(f"Error loading {LAYOUT_FILE}: {e}")
        self.coords = generate_default_coords()

    def save_coords(self):
        try:
            with open(LAYOUT_FILE, "w", encoding="utf-8") as f:
                json.dump(self.coords, f, indent=2)
            self.status_var.set(f"Saved layout successfully to {os.path.basename(LAYOUT_FILE)}!")
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save layout: {e}")

    def push_history(self):
        self.history.append(copy.deepcopy(self.coords))
        if len(self.history) > self.max_history:
            self.history.pop(0)
        self.redo_stack.clear()
        self._update_undo_button_states()

    def undo(self):
        if not self.history:
            self.status_var.set("Nothing to undo.")
            return
        self.redo_stack.append(copy.deepcopy(self.coords))
        self.coords = self.history.pop()
        self.draw_all_keys()
        self.update_inspector()
        self._update_undo_button_states()
        self.status_var.set(f"Undid action. ({len(self.history)} states left in undo history)")

    def redo(self):
        if not self.redo_stack:
            self.status_var.set("Nothing to redo.")
            return
        self.history.append(copy.deepcopy(self.coords))
        self.coords = self.redo_stack.pop()
        self.draw_all_keys()
        self.update_inspector()
        self._update_undo_button_states()
        self.status_var.set(f"Redid action. ({len(self.redo_stack)} states left in redo stack)")

    def _update_undo_button_states(self):
        if hasattr(self, "btn_undo") and hasattr(self, "btn_redo"):
            self.btn_undo.configure(state="normal" if self.history else "disabled")
            self.btn_redo.configure(state="normal" if self.redo_stack else "disabled")

    def reset_to_defaults(self):
        if messagebox.askyesno("Reset Layout", "Reset all key positions and dimensions to default KB_LAYOUT?"):
            self.push_history()
            self.coords = generate_default_coords()
            self.selected_keys.clear()
            self.draw_all_keys()
            self.update_inspector()
            self.status_var.set("Reset layout to default layout coordinates.")

    def _build_ui(self):
        # 1. Top Toolbar
        toolbar = tk.Frame(self.root, bg="#27272A", padx=12, pady=8)
        toolbar.pack(fill="x", padx=10, pady=(10, 6))

        save_btn = tk.Button(
            toolbar, text="💾 Save Layout (Ctrl+S)", bg="#2563EB", fg="#FFFFFF",
            activebackground="#1D4ED8", activeforeground="#FFFFFF",
            font=("Segoe UI", 9, "bold"), relief="flat", padx=12, pady=4,
            command=self.save_coords
        )
        save_btn.pack(side="left", padx=4)

        reload_btn = tk.Button(
            toolbar, text="🔄 Reload Saved", bg="#3F3F46", fg="#FFFFFF",
            font=("Segoe UI", 9), relief="flat", padx=10, pady=4,
            command=self._on_reload
        )
        reload_btn.pack(side="left", padx=4)

        reset_btn = tk.Button(
            toolbar, text="↩ Reset to Defaults", bg="#71717A", fg="#FFFFFF",
            font=("Segoe UI", 9), relief="flat", padx=10, pady=4,
            command=self.reset_to_defaults
        )
        reset_btn.pack(side="left", padx=4)

        # Undo / Redo controls
        tk.Frame(toolbar, bg="#52525B", width=1, height=24).pack(side="left", padx=8)

        self.btn_undo = tk.Button(
            toolbar, text="↶ Undo (Ctrl+Z)", bg="#3F3F46", fg="#FFFFFF",
            disabledforeground="#71717A", font=("Segoe UI", 9), relief="flat", padx=10, pady=4,
            command=self.undo, state="disabled"
        )
        self.btn_undo.pack(side="left", padx=3)

        self.btn_redo = tk.Button(
            toolbar, text="↷ Redo (Ctrl+Y)", bg="#3F3F46", fg="#FFFFFF",
            disabledforeground="#71717A", font=("Segoe UI", 9), relief="flat", padx=10, pady=4,
            command=self.redo, state="disabled"
        )
        self.btn_redo.pack(side="left", padx=3)

        # Snap to grid controls
        tk.Frame(toolbar, bg="#52525B", width=1, height=24).pack(side="left", padx=12)

        cb_snap = tk.Checkbutton(
            toolbar, text="Snap to Grid", variable=self.snap_grid_var,
            bg="#27272A", fg="#E4E4E7", selectcolor="#18181B",
            activebackground="#27272A", font=("Segoe UI", 9)
        )
        cb_snap.pack(side="left", padx=4)

        tk.Label(toolbar, text="Step (px):", bg="#27272A", fg="#A1A1AA", font=("Segoe UI", 9)).pack(side="left", padx=(6, 2))
        sp_grid = tk.Spinbox(
            toolbar, from_=1, to=50, textvariable=self.grid_size_var, width=4,
            bg="#18181B", fg="#FFFFFF", insertbackground="#FFFFFF"
        )
        sp_grid.pack(side="left", padx=2)

        # Quick select shortcuts
        tk.Frame(toolbar, bg="#52525B", width=1, height=24).pack(side="left", padx=12)
        tk.Button(
            toolbar, text="Select All (Ctrl+A)", bg="#3F3F46", fg="#E4E4E7",
            font=("Segoe UI", 8), relief="flat", padx=6, pady=2,
            command=self.select_all_keys
        ).pack(side="left", padx=2)
        tk.Button(
            toolbar, text="Clear (Esc)", bg="#3F3F46", fg="#E4E4E7",
            font=("Segoe UI", 8), relief="flat", padx=6, pady=2,
            command=self.clear_selection
        ).pack(side="left", padx=2)

        self.status_var = tk.StringVar(value="Click+drag canvas to box-select. Drag selected keys to move together.")
        status_lbl = tk.Label(toolbar, textvariable=self.status_var, bg="#27272A", fg="#34D399", font=("Segoe UI", 9))
        status_lbl.pack(side="right", padx=10)

        # 2. Main Content (Canvas on Left, Inspector on Right)
        content_frame = tk.Frame(self.root, bg="#18181B")
        content_frame.pack(fill="both", expand=True, padx=10, pady=6)

        # Canvas Frame with Scrollbars
        canvas_container = tk.Frame(content_frame, bg="#09090B", bd=1, relief="solid")
        canvas_container.pack(side="left", fill="both", expand=True, padx=(0, 10))

        self.canvas = tk.Canvas(
            canvas_container, bg="#09090B", highlightthickness=0,
            xscrollincrement=1, yscrollincrement=1
        )
        self.canvas.pack(side="left", fill="both", expand=True)

        self.hbar = ttk.Scrollbar(canvas_container, orient="horizontal", command=self.canvas.xview)
        self.vbar = ttk.Scrollbar(canvas_container, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=self.hbar.set, yscrollcommand=self.vbar.set)
        self.hbar.pack(side="bottom", fill="x")
        self.vbar.pack(side="right", fill="y")

        self.canvas.bind("<ButtonPress-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)

        # Inspector Panel
        self._build_inspector(content_frame)

    def _build_inspector(self, parent):
        panel = tk.Frame(parent, bg="#27272A", width=330, padx=14, pady=14, bd=1, relief="solid")
        panel.pack(side="right", fill="y")
        panel.pack_propagate(False)

        self.lbl_inspector_title = tk.Label(panel, text="KEY INSPECTOR", font=("Segoe UI", 11, "bold"), fg="#60A5FA", bg="#27272A")
        self.lbl_inspector_title.pack(anchor="w")

        # Selection Summary Counter
        self.lbl_selection_count = tk.Label(panel, text="No keys selected", fg="#A1A1AA", bg="#27272A", font=("Segoe UI", 9, "italic"))
        self.lbl_selection_count.pack(anchor="w", pady=(2, 6))

        # Key Selector Dropdown (for quick single-key picking)
        tk.Label(panel, text="Quick Select Key:", fg="#A1A1AA", bg="#27272A", font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 2))
        self.key_combo_var = tk.StringVar()
        all_keys = sorted(list(self.coords.keys()))
        self.key_combo = ttk.Combobox(panel, textvariable=self.key_combo_var, values=all_keys, state="readonly")
        self.key_combo.pack(fill="x", pady=(0, 6))
        self.key_combo.bind("<<ComboboxSelected>>", self.on_combo_select)

        # Single-Key Properties Section
        self.single_prop_frame = tk.Frame(panel, bg="#27272A")
        self.single_prop_frame.pack(fill="x", pady=2)

        id_frame = tk.Frame(self.single_prop_frame, bg="#27272A")
        id_frame.pack(fill="x", pady=2)
        tk.Label(id_frame, text="Key ID:", fg="#A1A1AA", bg="#27272A", width=10, anchor="w").pack(side="left")
        self.lbl_key_id = tk.Label(id_frame, text="None", fg="#FCD34D", bg="#27272A", font=("Segoe UI", 9, "bold"))
        self.lbl_key_id.pack(side="left")

        lbl_frame = tk.Frame(self.single_prop_frame, bg="#27272A")
        lbl_frame.pack(fill="x", pady=2)
        tk.Label(lbl_frame, text="Label:", fg="#A1A1AA", bg="#27272A", width=10, anchor="w").pack(side="left")
        self.entry_label_var = tk.StringVar()
        self.entry_label = tk.Entry(lbl_frame, textvariable=self.entry_label_var, bg="#18181B", fg="#FFFFFF", insertbackground="#FFFFFF", width=12)
        self.entry_label.pack(side="left")
        self.entry_label.bind("<Return>", lambda e: self.apply_inspector_inputs())
        self.entry_label.bind("<FocusOut>", lambda e: self.apply_inspector_inputs())

        # Coordinate Inputs (X, Y, W, H)
        geom_grid = tk.Frame(self.single_prop_frame, bg="#27272A")
        geom_grid.pack(fill="x", pady=4)

        self.val_x = tk.IntVar(value=0)
        self.val_y = tk.IntVar(value=0)
        self.val_w = tk.IntVar(value=0)
        self.val_h = tk.IntVar(value=0)

        # X & Y
        tk.Label(geom_grid, text="X (px):", fg="#A1A1AA", bg="#27272A").grid(row=0, column=0, sticky="w", pady=2)
        self.sp_x = tk.Spinbox(geom_grid, from_=-500, to=3000, textvariable=self.val_x, width=7, bg="#18181B", fg="#FFFFFF", insertbackground="#FFFFFF", command=self.apply_inspector_inputs)
        self.sp_x.grid(row=0, column=1, padx=4, pady=2)
        self.sp_x.bind("<Return>", lambda e: self.apply_inspector_inputs())
        self.sp_x.bind("<FocusOut>", lambda e: self.apply_inspector_inputs())

        tk.Label(geom_grid, text="Y (px):", fg="#A1A1AA", bg="#27272A").grid(row=0, column=2, sticky="w", pady=2)
        self.sp_y = tk.Spinbox(geom_grid, from_=-500, to=3000, textvariable=self.val_y, width=7, bg="#18181B", fg="#FFFFFF", insertbackground="#FFFFFF", command=self.apply_inspector_inputs)
        self.sp_y.grid(row=0, column=3, padx=4, pady=2)
        self.sp_y.bind("<Return>", lambda e: self.apply_inspector_inputs())
        self.sp_y.bind("<FocusOut>", lambda e: self.apply_inspector_inputs())

        # W & H
        tk.Label(geom_grid, text="Width (W):", fg="#A1A1AA", bg="#27272A").grid(row=1, column=0, sticky="w", pady=2)
        self.sp_w = tk.Spinbox(geom_grid, from_=10, to=1000, textvariable=self.val_w, width=7, bg="#18181B", fg="#FFFFFF", insertbackground="#FFFFFF", command=self.apply_inspector_inputs)
        self.sp_w.grid(row=1, column=1, padx=4, pady=2)
        self.sp_w.bind("<Return>", lambda e: self.apply_inspector_inputs())
        self.sp_w.bind("<FocusOut>", lambda e: self.apply_inspector_inputs())

        tk.Label(geom_grid, text="Height (H):", fg="#A1A1AA", bg="#27272A").grid(row=1, column=2, sticky="w", pady=2)
        self.sp_h = tk.Spinbox(geom_grid, from_=10, to=1000, textvariable=self.val_h, width=7, bg="#18181B", fg="#FFFFFF", insertbackground="#FFFFFF", command=self.apply_inspector_inputs)
        self.sp_h.grid(row=1, column=3, padx=4, pady=2)
        self.sp_h.bind("<Return>", lambda e: self.apply_inspector_inputs())
        self.sp_h.bind("<FocusOut>", lambda e: self.apply_inspector_inputs())

        tk.Frame(panel, bg="#3F3F46", height=1).pack(fill="x", pady=8)

        # Batch Alignment Tools (multi-selection)
        tk.Label(panel, text="Batch Alignment Tools:", fg="#60A5FA", bg="#27272A", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(2, 4))
        align_row1 = tk.Frame(panel, bg="#27272A")
        align_row1.pack(fill="x", pady=2)
        self.btn_align_top = tk.Button(align_row1, text="Align Top", bg="#3B82F6", fg="#FFFFFF", relief="flat", padx=6, command=self.align_top)
        self.btn_align_top.pack(side="left", padx=2, expand=True, fill="x")
        self.btn_align_bottom = tk.Button(align_row1, text="Align Bottom", bg="#3B82F6", fg="#FFFFFF", relief="flat", padx=6, command=self.align_bottom)
        self.btn_align_bottom.pack(side="left", padx=2, expand=True, fill="x")

        align_row2 = tk.Frame(panel, bg="#27272A")
        align_row2.pack(fill="x", pady=2)
        self.btn_align_left = tk.Button(align_row2, text="Align Left", bg="#3B82F6", fg="#FFFFFF", relief="flat", padx=6, command=self.align_left)
        self.btn_align_left.pack(side="left", padx=2, expand=True, fill="x")
        self.btn_match_w = tk.Button(align_row2, text="Match Width", bg="#4B5563", fg="#FFFFFF", relief="flat", padx=6, command=self.match_width)
        self.btn_match_w.pack(side="left", padx=2, expand=True, fill="x")
        self.btn_match_h = tk.Button(align_row2, text="Match Height", bg="#4B5563", fg="#FFFFFF", relief="flat", padx=6, command=self.match_height)
        self.btn_match_h.pack(side="left", padx=2, expand=True, fill="x")

        tk.Frame(panel, bg="#3F3F46", height=1).pack(fill="x", pady=8)

        # Quick Nudge & Resize (Applies to all selected keys)
        tk.Label(panel, text="Nudge Selected (Group / Single):", fg="#A1A1AA", bg="#27272A", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(2, 2))
        
        nudge_box = tk.Frame(panel, bg="#27272A")
        nudge_box.pack(fill="x", pady=2)

        tk.Button(nudge_box, text="← 1px", width=5, bg="#3F3F46", fg="#FFFFFF", relief="flat", command=lambda: self.nudge_selected(-1, 0)).pack(side="left", padx=2)
        tk.Button(nudge_box, text="→ 1px", width=5, bg="#3F3F46", fg="#FFFFFF", relief="flat", command=lambda: self.nudge_selected(1, 0)).pack(side="left", padx=2)
        tk.Button(nudge_box, text="↑ 1px", width=5, bg="#3F3F46", fg="#FFFFFF", relief="flat", command=lambda: self.nudge_selected(0, -1)).pack(side="left", padx=2)
        tk.Button(nudge_box, text="↓ 1px", width=5, bg="#3F3F46", fg="#FFFFFF", relief="flat", command=lambda: self.nudge_selected(0, 1)).pack(side="left", padx=2)

        size_box = tk.Frame(panel, bg="#27272A")
        size_box.pack(fill="x", pady=2)

        tk.Button(size_box, text="W -1", width=5, bg="#3F3F46", fg="#FFFFFF", relief="flat", command=lambda: self.resize_selected(-1, 0)).pack(side="left", padx=2)
        tk.Button(size_box, text="W +1", width=5, bg="#3F3F46", fg="#FFFFFF", relief="flat", command=lambda: self.resize_selected(1, 0)).pack(side="left", padx=2)
        tk.Button(size_box, text="H -1", width=5, bg="#3F3F46", fg="#FFFFFF", relief="flat", command=lambda: self.resize_selected(0, -1)).pack(side="left", padx=2)
        tk.Button(size_box, text="H +1", width=5, bg="#3F3F46", fg="#FFFFFF", relief="flat", command=lambda: self.resize_selected(0, 1)).pack(side="left", padx=2)

        # Helpful Shortcuts Legend
        tk.Frame(panel, bg="#3F3F46", height=1).pack(fill="x", pady=8)
        legend = (
            "Multi-Selection & Shortcuts:\n"
            "• Drag empty canvas: Marquee box select\n"
            "• Shift / Ctrl + Drag: Add to selection\n"
            "• Ctrl + Click key: Toggle key in selection\n"
            "• Drag any selected key: Move all together\n"
            "• Arrow keys: Nudge group 1px (Shift: 5px)\n"
            "• Ctrl + Arrows: Resize group 1px\n"
            "• Ctrl + Z: Undo | Ctrl + Y: Redo\n"
            "• Ctrl + A: Select All | Esc: Deselect"
        )
        tk.Label(panel, text=legend, fg="#9CA3AF", bg="#27272A", justify="left", font=("Segoe UI", 8)).pack(anchor="w", pady=2)

    def _bind_keys(self):
        self.root.bind("<Control-s>", lambda e: self.save_coords())
        self.root.bind("<Control-z>", self._on_undo_key)
        self.root.bind("<Control-y>", self._on_redo_key)
        self.root.bind("<Control-Z>", self._on_redo_key)
        self.root.bind("<Control-a>", lambda e: self.select_all_keys())
        self.root.bind("<Escape>", lambda e: self.clear_selection())
        self.root.bind("<Left>", lambda e: self._on_arrow_key(-1, 0, e))
        self.root.bind("<Right>", lambda e: self._on_arrow_key(1, 0, e))
        self.root.bind("<Up>", lambda e: self._on_arrow_key(0, -1, e))
        self.root.bind("<Down>", lambda e: self._on_arrow_key(0, 1, e))
        self.root.bind("<Tab>", self._on_cycle_key)
        self.root.bind("<Shift-Tab>", lambda e: self._on_cycle_key(e, reverse=True))

    def _on_undo_key(self, event):
        widget = self.root.focus_get()
        if isinstance(widget, (tk.Entry, tk.Spinbox)):
            return
        self.undo()
        return "break"

    def _on_redo_key(self, event):
        widget = self.root.focus_get()
        if isinstance(widget, (tk.Entry, tk.Spinbox)):
            return
        self.redo()
        return "break"

    def _on_arrow_key(self, dx: int, dy: int, event):
        widget = self.root.focus_get()
        if isinstance(widget, (tk.Entry, tk.Spinbox)):
            return

        if not self.selected_keys:
            return

        is_shift = bool(event.state & 0x0001)
        is_ctrl = bool(event.state & 0x0004)
        multiplier = 5 if is_shift else 1

        if is_ctrl:
            self.resize_selected(dx * multiplier, dy * multiplier)
        else:
            self.nudge_selected(dx * multiplier, dy * multiplier)

    def _on_cycle_key(self, event, reverse=False):
        keys = list(self.coords.keys())
        if not keys:
            return
        single = self.primary_selected_key
        if not single or single not in keys:
            self.select_single_key(keys[0])
            return "break"
        idx = keys.index(single)
        new_idx = (idx - 1) if reverse else (idx + 1)
        new_idx %= len(keys)
        self.select_single_key(keys[new_idx])
        return "break"

    def select_all_keys(self):
        self.selected_keys = set(self.coords.keys())
        self.draw_all_keys()
        self.update_inspector()
        self.status_var.set(f"Selected all {len(self.selected_keys)} keys.")

    def clear_selection(self):
        self.selected_keys.clear()
        self.draw_all_keys()
        self.update_inspector()
        self.status_var.set("Cleared selection.")

    def _on_reload(self):
        self.push_history()
        self.load_coords()
        self.selected_keys.clear()
        self.draw_all_keys()
        self.update_inspector()
        self.status_var.set("Reloaded layout from file.")

    def draw_all_keys(self, skip_marquee_clear: bool = False):
        if not skip_marquee_clear:
            self.canvas.delete("all")
        else:
            self.canvas.delete("key", "resize_handle")

        if not self.coords:
            return

        max_x = max(d["x"] + d["w"] for d in self.coords.values()) + 100
        max_y = max(d["y"] + d["h"] for d in self.coords.values()) + 100
        self.canvas.configure(scrollregion=(0, 0, max(1200, max_x), max(600, max_y)))

        # 1. Draw non-selected keys
        for key_id, d in self.coords.items():
            if key_id not in self.selected_keys:
                self._draw_single_key(key_id, d, selected=False)

        # 2. Draw selected keys on top
        for key_id in self.selected_keys:
            if key_id in self.coords:
                self._draw_single_key(key_id, self.coords[key_id], selected=True)

    def _draw_single_key(self, key_id: str, d: dict, selected: bool):
        x, y, w, h = d["x"], d["y"], d["w"], d["h"]
        label = d.get("label", key_id)

        if selected:
            fill_bg = "#1E293B"
            outline_col = "#3B82F6"
            outline_w = 2
        else:
            if key_id.startswith("lightbar_"):
                fill_bg = "#182635"
                outline_col = "#0284C7"
            elif key_id == "fn":
                fill_bg = "#2E1065"
                outline_col = "#8B5CF6"
            else:
                fill_bg = "#27272A"
                outline_col = "#3F3F46"
            outline_w = 1

        tag = f"key_{key_id}"

        self.canvas.create_rectangle(
            x, y, x + w, y + h,
            fill=fill_bg, outline=outline_col, width=outline_w,
            tags=("key", tag)
        )

        font_size = 9 if w >= 40 and h >= 28 else 7
        self.canvas.create_text(
            x + w // 2, y + h // 2,
            text=label, fill="#FFFFFF",
            font=("Segoe UI", font_size, "bold" if selected else "normal"),
            tags=("key", tag)
        )

        # Draw resize handle ONLY if exactly one key is selected
        if selected and len(self.selected_keys) == 1:
            handle_size = 8
            hx2 = x + w
            hy2 = y + h
            hx1 = hx2 - handle_size
            hy1 = hy2 - handle_size
            self.canvas.create_rectangle(
                hx1, hy1, hx2, hy2,
                fill="#60A5FA", outline="#FFFFFF", width=1,
                tags=("resize_handle", tag)
            )

    def select_single_key(self, key_id: str | None):
        if key_id:
            self.selected_keys = {key_id}
        else:
            self.selected_keys.clear()
        self.draw_all_keys()
        self.update_inspector()

    def update_inspector(self):
        count = len(self.selected_keys)
        single = self.primary_selected_key

        # Update counter & title
        if count == 0:
            self.lbl_inspector_title.configure(text="KEY INSPECTOR")
            self.lbl_selection_count.configure(text="No keys selected", fg="#A1A1AA")
            self.lbl_key_id.configure(text="None")
            self.entry_label_var.set("")
            self.val_x.set(0)
            self.val_y.set(0)
            self.val_w.set(0)
            self.val_h.set(0)
            self.key_combo_var.set("")
            self._set_single_inputs_state("disabled")
            self._set_align_buttons_state("disabled")

        elif count == 1 and single in self.coords:
            d = self.coords[single]
            self.lbl_inspector_title.configure(text="KEY INSPECTOR (1)")
            self.lbl_selection_count.configure(text=f"Selected: '{single}'", fg="#34D399")
            self.lbl_key_id.configure(text=single)
            self.entry_label_var.set(d.get("label", single))
            self.val_x.set(d["x"])
            self.val_y.set(d["y"])
            self.val_w.set(d["w"])
            self.val_h.set(d["h"])
            self.key_combo_var.set(single)
            self._set_single_inputs_state("normal")
            self._set_align_buttons_state("disabled")

        else:
            self.lbl_inspector_title.configure(text=f"GROUP INSPECTOR ({count})")
            self.lbl_selection_count.configure(text=f"{count} keys selected in group", fg="#60A5FA")
            self.lbl_key_id.configure(text=f"[Group: {count} keys]")
            self.entry_label_var.set(f"[{count} keys]")
            # Display average or bounding min coords
            min_x = min(self.coords[k]["x"] for k in self.selected_keys if k in self.coords)
            min_y = min(self.coords[k]["y"] for k in self.selected_keys if k in self.coords)
            self.val_x.set(min_x)
            self.val_y.set(min_y)
            self.key_combo_var.set("")
            self._set_single_inputs_state("disabled")
            self._set_align_buttons_state("normal")

    def _set_single_inputs_state(self, state: str):
        self.entry_label.configure(state=state)
        self.sp_x.configure(state=state)
        self.sp_y.configure(state=state)
        self.sp_w.configure(state=state)
        self.sp_h.configure(state=state)

    def _set_align_buttons_state(self, state: str):
        self.btn_align_top.configure(state=state)
        self.btn_align_bottom.configure(state=state)
        self.btn_align_left.configure(state=state)
        self.btn_match_w.configure(state=state)
        self.btn_match_h.configure(state=state)

    def on_combo_select(self, event):
        chosen = self.key_combo_var.get()
        if chosen in self.coords:
            self.select_single_key(chosen)

    def apply_inspector_inputs(self):
        single = self.primary_selected_key
        if not single or single not in self.coords:
            return

        d = self.coords[single]
        new_label = self.entry_label_var.get()
        new_x = int(self.val_x.get())
        new_y = int(self.val_y.get())
        new_w = max(10, int(self.val_w.get()))
        new_h = max(10, int(self.val_h.get()))

        if (d.get("label") != new_label or d["x"] != new_x or
            d["y"] != new_y or d["w"] != new_w or d["h"] != new_h):
            self.push_history()
            d["label"] = new_label
            d["x"] = new_x
            d["y"] = new_y
            d["w"] = new_w
            d["h"] = new_h
            self.draw_all_keys()

    def nudge_selected(self, dx: int, dy: int):
        if not self.selected_keys:
            return
        self.push_history()
        for k in self.selected_keys:
            if k in self.coords:
                self.coords[k]["x"] += dx
                self.coords[k]["y"] += dy
        self.update_inspector()
        self.draw_all_keys()

    def resize_selected(self, dw: int, dh: int):
        if not self.selected_keys:
            return
        self.push_history()
        for k in self.selected_keys:
            if k in self.coords:
                self.coords[k]["w"] = max(10, self.coords[k]["w"] + dw)
                self.coords[k]["h"] = max(10, self.coords[k]["h"] + dh)
        self.update_inspector()
        self.draw_all_keys()

    # --- Batch Alignment Methods ---
    def align_top(self):
        if len(self.selected_keys) < 2:
            return
        self.push_history()
        min_y = min(self.coords[k]["y"] for k in self.selected_keys if k in self.coords)
        for k in self.selected_keys:
            if k in self.coords:
                self.coords[k]["y"] = min_y
        self.draw_all_keys()
        self.update_inspector()
        self.status_var.set(f"Aligned {len(self.selected_keys)} keys to Top (Y={min_y}).")

    def align_bottom(self):
        if len(self.selected_keys) < 2:
            return
        self.push_history()
        max_bottom = max(self.coords[k]["y"] + self.coords[k]["h"] for k in self.selected_keys if k in self.coords)
        for k in self.selected_keys:
            if k in self.coords:
                self.coords[k]["y"] = max_bottom - self.coords[k]["h"]
        self.draw_all_keys()
        self.update_inspector()
        self.status_var.set(f"Aligned {len(self.selected_keys)} keys to Bottom.")

    def align_left(self):
        if len(self.selected_keys) < 2:
            return
        self.push_history()
        min_x = min(self.coords[k]["x"] for k in self.selected_keys if k in self.coords)
        for k in self.selected_keys:
            if k in self.coords:
                self.coords[k]["x"] = min_x
        self.draw_all_keys()
        self.update_inspector()
        self.status_var.set(f"Aligned {len(self.selected_keys)} keys to Left (X={min_x}).")

    def match_width(self):
        if len(self.selected_keys) < 2:
            return
        self.push_history()
        first_key = next(iter(self.selected_keys))
        target_w = self.coords[first_key]["w"]
        for k in self.selected_keys:
            if k in self.coords:
                self.coords[k]["w"] = target_w
        self.draw_all_keys()
        self.update_inspector()
        self.status_var.set(f"Matched width of {len(self.selected_keys)} keys to {target_w}px.")

    def match_height(self):
        if len(self.selected_keys) < 2:
            return
        self.push_history()
        first_key = next(iter(self.selected_keys))
        target_h = self.coords[first_key]["h"]
        for k in self.selected_keys:
            if k in self.coords:
                self.coords[k]["h"] = target_h
        self.draw_all_keys()
        self.update_inspector()
        self.status_var.set(f"Matched height of {len(self.selected_keys)} keys to {target_h}px.")

    # --- Mouse Canvas Event Handlers ---
    def on_canvas_click(self, event):
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        self.is_dragging_committed = False

        is_shift = bool(event.state & 0x0001)
        is_ctrl = bool(event.state & 0x0004)

        # 1. Check if resize handle was clicked (only active when exactly 1 key is selected)
        if len(self.selected_keys) == 1:
            single = self.primary_selected_key
            if single and single in self.coords:
                d = self.coords[single]
                x, y, w, h = d["x"], d["y"], d["w"], d["h"]
                handle_size = 12
                if (x + w - handle_size <= cx <= x + w + 4) and (y + h - handle_size <= cy <= y + h + 4):
                    self.drag_mode = "resize"
                    self.drag_start_x = cx
                    self.drag_start_y = cy
                    self.initial_key_geom = dict(d)
                    return

        # 2. Check if a key was clicked
        clicked_key = None
        for key_id, d in reversed(list(self.coords.items())):
            x, y, w, h = d["x"], d["y"], d["w"], d["h"]
            if x <= cx <= x + w and y <= cy <= y + h:
                clicked_key = key_id
                break

        if clicked_key:
            if is_ctrl or is_shift:
                # Toggle key in/out of selection
                if clicked_key in self.selected_keys:
                    self.selected_keys.remove(clicked_key)
                else:
                    self.selected_keys.add(clicked_key)
            else:
                # If clicking a key that is NOT in the current selection, select only it
                if clicked_key not in self.selected_keys:
                    self.selected_keys = {clicked_key}
                # (If it was already in selected_keys, preserve multi-selection for dragging together)

            self.drag_mode = "move"
            self.drag_start_x = cx
            self.drag_start_y = cy
            self.initial_positions = {
                k: (self.coords[k]["x"], self.coords[k]["y"])
                for k in self.selected_keys if k in self.coords
            }
            self.draw_all_keys()
            self.update_inspector()

        else:
            # 3. Clicked empty canvas space -> Start Marquee Selection Box
            if not (is_ctrl or is_shift):
                self.selected_keys.clear()

            self.drag_mode = "marquee"
            self.marquee_start = (cx, cy)
            self.initial_selected_keys = set(self.selected_keys)
            self.draw_all_keys()
            self.update_inspector()

    def on_canvas_drag(self, event):
        if not self.drag_mode:
            return

        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        grid_step = max(1, self.grid_size_var.get()) if self.snap_grid_var.get() else 1

        if self.drag_mode == "marquee":
            x1 = min(self.marquee_start[0], cx)
            x2 = max(self.marquee_start[0], cx)
            y1 = min(self.marquee_start[1], cy)
            y2 = max(self.marquee_start[1], cy)

            # Draw visual marquee selection rectangle
            self.canvas.delete("marquee")
            self.canvas.create_rectangle(
                x1, y1, x2, y2,
                outline="#60A5FA", width=1.5, dash=(4, 2),
                fill="#3B82F6", stipple="gray25",
                tags="marquee"
            )

            # Find all keys overlapping the marquee box
            current_selected = set(self.initial_selected_keys)
            for key_id, d in self.coords.items():
                kx1, ky1 = d["x"], d["y"]
                kx2, ky2 = kx1 + d["w"], ky1 + d["h"]
                # Box intersection test
                if not (kx2 < x1 or kx1 > x2 or ky2 < y1 or ky1 > y2):
                    current_selected.add(key_id)

            if current_selected != self.selected_keys:
                self.selected_keys = current_selected
                self.draw_all_keys(skip_marquee_clear=True)
                self.update_inspector()

        elif self.drag_mode == "move" and self.selected_keys:
            if not self.is_dragging_committed:
                self.push_history()
                self.is_dragging_committed = True

            dx = cx - self.drag_start_x
            dy = cy - self.drag_start_y

            if self.snap_grid_var.get():
                dx = round(dx / grid_step) * grid_step
                dy = round(dy / grid_step) * grid_step

            # Move all keys in selection together by delta (dx, dy)
            for k, (init_x, init_y) in self.initial_positions.items():
                if k in self.coords:
                    self.coords[k]["x"] = int(init_x + dx)
                    self.coords[k]["y"] = int(init_y + dy)

            self.draw_all_keys()
            self.update_inspector()

        elif self.drag_mode == "resize" and len(self.selected_keys) == 1:
            if not self.is_dragging_committed:
                self.push_history()
                self.is_dragging_committed = True

            single = self.primary_selected_key
            if single and single in self.coords:
                dx = cx - self.drag_start_x
                dy = cy - self.drag_start_y
                target_w = self.initial_key_geom["w"] + dx
                target_h = self.initial_key_geom["h"] + dy
                if self.snap_grid_var.get():
                    target_w = round(target_w / grid_step) * grid_step
                    target_h = round(target_h / grid_step) * grid_step
                self.coords[single]["w"] = max(12, int(target_w))
                self.coords[single]["h"] = max(12, int(target_h))
                self.draw_all_keys()
                self.update_inspector()

    def on_canvas_release(self, event):
        self.is_dragging_committed = False
        if self.drag_mode == "marquee":
            self.canvas.delete("marquee")
            self.draw_all_keys()
            self.status_var.set(f"Selected {len(self.selected_keys)} keys.")
        elif self.drag_mode == "move":
            self.status_var.set(f"Moved {len(self.selected_keys)} keys.")
        self.drag_mode = None

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = LayoutEditorUI()
    app.run()
