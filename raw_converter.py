#!/usr/bin/env python3
"""
RAW Converter Desktop App

Features:
- PyQt6 GUI with dark theme
- Drag-and-drop and Add Files / Add Folder
- Batch conversion using ThreadPoolExecutor
- JPEG output

Requirements: see requirements.txt
"""
from __future__ import annotations

import sys
import os
import subprocess
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any

import rawpy
from PIL import Image

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QProgressBar,
    QTextEdit,
    QRadioButton,
    QGroupBox,
    QCheckBox,
    QSlider,
    QSpinBox,
)

__version__ = "1.0.2"

class FileItemWidget(QWidget):
    def __init__(self, filename: str, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.name_label = QLabel(filename)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.status_label = QLabel("Pending")
        self.status_label.setFixedWidth(80)
        self.layout.addWidget(self.name_label)
        self.layout.addWidget(self.progress)
        self.layout.addWidget(self.status_label)

    def set_progress(self, v: int):
        self.progress.setValue(int(v))

    def set_status(self, text: str):
        self.status_label.setText(text)


class DropListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        files = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            files.append(path)
        # delegate to parent (main window)
        if self.parent() is not None:
            self.parent().add_paths(files)


class RawConverterApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RAW Converter")
        self.resize(900, 600)
        self.files: List[Dict[str, Any]] = []
        self.queue_updates: List[Dict[str, Any]] = []

        self.executor: ThreadPoolExecutor | None = None
        self.futures = []

        # settings file next to this script
        self._settings_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw_converter_settings.json")
        self.settings: Dict[str, Any] = {}
        self._load_settings()

        # png option removed; app only produces JPEGs

        self._build_ui()

        # Polling queue for worker messages
        self._timer = QTimer()
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._poll_updates)
        self._timer.start()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Top bar
        topbar = QHBoxLayout()
        add_files_btn = QPushButton("Add Files")
        add_files_btn.clicked.connect(self._on_add_files)
        add_folder_btn = QPushButton("Add Folder")
        add_folder_btn.clicked.connect(self._on_add_folder)
        select_out_btn = QPushButton("Select Output Folder")
        select_out_btn.clicked.connect(self._on_select_output)
        self.output_folder_label = QLabel("Output: (not selected)")

        topbar.addWidget(add_files_btn)
        topbar.addWidget(add_folder_btn)
        topbar.addWidget(select_out_btn)
        open_out_btn = QPushButton("Open Output Folder")
        open_out_btn.clicked.connect(self._on_open_output)
        topbar.addWidget(open_out_btn)
        topbar.addWidget(self.output_folder_label)
        layout.addLayout(topbar)

        # Settings panel
        settings = QGroupBox("Settings")
        s_layout = QHBoxLayout()

        self.jpeg_radio = QRadioButton("JPEG")
        self.jpeg_radio.setChecked(True)

        self.cap_checkbox = QCheckBox("Resize max dimension to 2048px (Recommended for Messaging)")
        self.cap_checkbox.setChecked(bool(self.settings.get("resize_cap", True)))
        self.cap_checkbox.toggled.connect(lambda v: self._save_settings())

        self.quality_slider = QSlider(Qt.Orientation.Horizontal)
        self.quality_slider.setRange(70, 100)
        self.quality_slider.setValue(int(self.settings.get("jpeg_quality", 92)))
        self.quality_label = QLabel(f"JPEG Quality: {self.quality_slider.value()}")
        def _on_quality(v):
            self.quality_label.setText(f"JPEG Quality: {v}")
            self._save_settings()
        self.quality_slider.valueChanged.connect(_on_quality)

        # Worker controls
        try:
            default_workers = int(self.settings.get("workers", max(1, (os.cpu_count() or 1))))
        except Exception:
            default_workers = 2
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 1024)
        self.workers_spin.setValue(default_workers)
        self.workers_label = QLabel(f"Workers:")
        self.use_max_workers_checkbox = QCheckBox("Use max available workers (CPU*4)")
        self.use_max_workers_checkbox.setChecked(bool(self.settings.get("use_max_workers", False)))
        self.use_max_workers_checkbox.toggled.connect(lambda v: self.workers_spin.setDisabled(v))
        self.use_max_workers_checkbox.toggled.connect(lambda v: self._save_settings())
        self.workers_spin.valueChanged.connect(lambda v: self._save_settings())

        s_layout.addWidget(self.jpeg_radio)
        s_layout.addWidget(self.cap_checkbox)
        s_layout.addWidget(self.quality_label)
        s_layout.addWidget(self.quality_slider)
        s_layout.addWidget(self.workers_label)
        s_layout.addWidget(self.workers_spin)
        s_layout.addWidget(self.use_max_workers_checkbox)

        settings.setLayout(s_layout)
        layout.addWidget(settings)

        # Center area - file list
        center_layout = QHBoxLayout()
        self.list_widget = DropListWidget(self)
        self.list_widget.setMinimumWidth(500)
        center_layout.addWidget(self.list_widget)

        # Right: item details / placeholder
        right_box = QVBoxLayout()
        right_box.addWidget(QLabel("Queue"))
        center_layout.addLayout(right_box)

        layout.addLayout(center_layout)

        # Bottom bar
        bottom = QHBoxLayout()
        self.overall_progress = QProgressBar()
        self.overall_progress.setValue(0)
        start_btn = QPushButton("Start Batch Conversion")
        start_btn.clicked.connect(self._on_start)
        bottom.addWidget(self.overall_progress)
        bottom.addWidget(start_btn)

        layout.addLayout(bottom)

        # Log console
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        layout.addWidget(self.log_console)

        # Version label bottom-right
        ver_layout = QHBoxLayout()
        ver_layout.addStretch()
        self.version_label = QLabel(f"v{__version__}")
        self.version_label.setStyleSheet("color: #BBBBBB; font-size: 10px;")
        ver_layout.addWidget(self.version_label)
        layout.addLayout(ver_layout)

    def log(self, msg: str):
        self.log_console.append(msg)

    def add_paths(self, paths: List[str]):
        raw_exts = {".cr2", ".nef", ".arw", ".dng"}
        added = 0
        for p in paths:
            if os.path.isdir(p):
                for root, _, files in os.walk(p):
                    for fn in files:
                        if os.path.splitext(fn)[1].lower() in raw_exts:
                            full = os.path.join(root, fn)
                            self._queue_file(full)
                            added += 1
            else:
                if os.path.splitext(p)[1].lower() in raw_exts:
                    self._queue_file(p)
                    added += 1
        self.log(f"Added {added} files to queue.")

    def _queue_file(self, path: str):
        if any(f["path"] == path for f in self.files):
            return
        item = {"path": path, "status": "Pending"}
        self.files.append(item)
        idx = len(self.files) - 1
        lw_item = QListWidgetItem()
        lw_item.setData(Qt.ItemDataRole.UserRole, idx)
        self.list_widget.addItem(lw_item)
        widget = FileItemWidget(os.path.basename(path))
        # ensure the item reserves space for the widget
        lw_item.setSizeHint(widget.sizeHint())
        self.list_widget.setItemWidget(lw_item, widget)
        # store widget ref for updates
        self.files[idx]["widget"] = widget
        # make sure the UI updates immediately
        try:
            self.list_widget.scrollToItem(lw_item)
            QApplication.processEvents()
        except Exception:
            pass

    def _on_add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select RAW files", os.getcwd(), "RAW Files (*.CR2 *.NEF *.ARW *.DNG)")
        if files:
            self.add_paths(files)

    def _on_add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder", os.getcwd())
        if folder:
            self.add_paths([folder])

    def _on_select_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", os.getcwd())
        if folder:
            self.output_folder = folder
            self.output_folder_label.setText(f"Output: {folder}")
            # persist chosen output folder
            try:
                self._save_settings()
            except Exception:
                pass

    def _on_open_output(self):
        folder = getattr(self, 'output_folder', None)
        if not folder:
            self.log("No output folder selected.")
            return
        if not os.path.exists(folder):
            self.log("Output folder does not exist.")
            return
        try:
            if sys.platform.startswith('win'):
                os.startfile(folder)
            elif sys.platform.startswith('darwin'):
                subprocess.run(['open', folder])
            else:
                subprocess.run(['xdg-open', folder])
        except Exception as e:
            self.log(f"Failed to open folder: {e}")

    def _load_settings(self):
        try:
            if os.path.exists(self._settings_path):
                import json
                with open(self._settings_path, 'r', encoding='utf-8') as f:
                    self.settings = json.load(f)
        except Exception:
            self.settings = {}

    def _save_settings(self):
        try:
            import json
            # gather settings from controls if present
            self.settings['workers'] = getattr(self, 'workers_spin', None).value() if getattr(self, 'workers_spin', None) else self.settings.get('workers', 1)
            self.settings['use_max_workers'] = bool(getattr(self, 'use_max_workers_checkbox', None) and self.use_max_workers_checkbox.isChecked())
            self.settings['jpeg_quality'] = int(getattr(self, 'quality_slider', None).value() if getattr(self, 'quality_slider', None) else self.settings.get('jpeg_quality', 92))
            self.settings['resize_cap'] = bool(getattr(self, 'cap_checkbox', None) and self.cap_checkbox.isChecked())
            self.settings['output_folder'] = getattr(self, 'output_folder', self.settings.get('output_folder'))
            with open(self._settings_path, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            # don't crash UI on save
            self.log(f"Failed to save settings: {e}")

    def _on_start(self):
        # ensure output folder exists; if not selected, create default 'imgout' next to the script
        if not hasattr(self, 'output_folder') or not self.output_folder:
            default_out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'imgout')
            try:
                os.makedirs(default_out, exist_ok=True)
                self.output_folder = default_out
                self.output_folder_label.setText(f"Output: {self.output_folder}")
                try:
                    self._save_settings()
                except Exception:
                    pass
                self.log(f"No output folder selected — using default: {self.output_folder}")
            except Exception as e:
                self.log(f"Please select an output folder first. (failed to create default: {e})")
                return
        pending = [f for f in self.files if f["status"] == "Pending"]
        if not pending:
            self.log("No pending files to convert.")
            return

        # Update statuses
        for i, f in enumerate(self.files):
            if f["status"] == "Pending":
                f["status"] = "Queued"
                self._update_list_item(i)

        if getattr(self, 'use_max_workers_checkbox', None) and self.use_max_workers_checkbox.isChecked():
            max_workers = max(1, (os.cpu_count() or 1) * 4)
        else:
            max_workers = getattr(self, 'workers_spin', None).value() if getattr(self, 'workers_spin', None) else max(1, (os.cpu_count() or 1))

        # Cap at a reasonable upper bound to avoid runaway thread counts
        max_workers = max(1, min(max_workers, 1024))
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.log(f"Starting conversion with {max_workers} workers...")

        tasks = []
        for i, f in enumerate(self.files):
            if f["status"] in ("Queued", "Pending"):
                fut = self.executor.submit(self._convert_worker, i, f["path"]) 
                tasks.append(fut)
                self.futures.append(fut)

    def _poll_updates(self):
        if self.queue_updates:
            while self.queue_updates:
                msg = self.queue_updates.pop(0)
                typ = msg.get("type")
                if typ == "status":
                    idx = msg["index"]
                    self.files[idx]["status"] = msg["status"]
                    # update widget status if present
                    w = self.files[idx].get("widget")
                    if w:
                        w.set_status(msg["status"])
                        if msg["status"] == "Done":
                            w.set_progress(100)
                        if msg["status"] == "Error":
                            w.set_progress(0)
                    else:
                        self._update_list_item(idx)
                elif typ == "log":
                    self.log(msg["text"])
                elif typ == "progress":
                    # per-file progress or overall
                    if "index" in msg:
                        idx = msg["index"]
                        w = self.files[idx].get("widget")
                        if w:
                            w.set_progress(msg.get("value", 0))
                    else:
                        self.overall_progress.setValue(msg["value"])

        # Check overall progress based on files statuses
        total = len(self.files)
        if total:
            done = sum(1 for f in self.files if f["status"] in ("Done", "Error"))
            percent = int(100 * done / total)
            self.overall_progress.setValue(percent)

    def _update_list_item(self, index: int):
        # find item with matching user role
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == index:
                p = self.files[index]["path"]
                status = self.files[index]["status"]
                try:
                    size = os.path.getsize(p)
                    display = f"{os.path.basename(p)} — {status} — {size//1024} KB"
                except Exception:
                    display = f"{os.path.basename(p)} — {status}"
                it.setText(display)
                break

    def _convert_worker(self, index: int, path: str):
        # Worker runs in threadpool
        try:
            self.queue_updates.append({"type": "status", "index": index, "status": "Converting"})

            # 1) Read RAW
            try:
                rr = rawpy.imread(path)
                self.queue_updates.append({"type": "progress", "index": index, "value": 20})
                rgb = rr.postprocess(use_camera_wb=True, output_bps=8)
                self.queue_updates.append({"type": "progress", "index": index, "value": 60})
            except Exception as e:
                tb = traceback.format_exc()
                self.queue_updates.append({"type": "log", "text": f"Error reading {path}: {e}\n{tb}"})
                self.queue_updates.append({"type": "status", "index": index, "status": "Error"})
                return

            img = Image.fromarray(rgb)

            # Prepare output path
            base = os.path.splitext(os.path.basename(path))[0]
            out_folder = getattr(self, 'output_folder', None)
            if not out_folder:
                default_out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'imgout')
                try:
                    os.makedirs(default_out, exist_ok=True)
                    out_folder = default_out
                    # persist the default output folder for next run
                    self.output_folder = out_folder
                    try:
                        self._save_settings()
                    except Exception:
                        pass
                except Exception as e:
                    # fallback to current working directory
                    self.queue_updates.append({"type": "log", "text": f"Could not create default output folder {default_out}: {e}. Using CWD."})
                    out_folder = os.getcwd()

            # Always produce WhatsApp-ready JPEG
            # Optional resize
            if self.cap_checkbox.isChecked():
                max_dim = 2048
                w, h = img.size
                if max(w, h) > max_dim:
                    ratio = max_dim / max(w, h)
                    new_size = (int(w * ratio), int(h * ratio))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                self.queue_updates.append({"type": "progress", "index": index, "value": 80})

            outpath = os.path.join(out_folder, base + ".jpg")
            quality = self.quality_slider.value()
            img.save(outpath, format="JPEG", quality=quality, optimize=True, progressive=True)
            # saved
            self.queue_updates.append({"type": "progress", "index": index, "value": 100})

            # Report sizes
            try:
                raw_size = os.path.getsize(path)
                out_size = os.path.getsize(outpath)
                saved = raw_size - out_size
                pct = 100.0 * (saved) / raw_size if raw_size > 0 else 0.0
                self.queue_updates.append({"type": "log", "text": f"Converted {os.path.basename(path)} -> {os.path.basename(outpath)} ({out_size//1024} KB), saved {int(pct)}%"})
            except Exception:
                pass

            self.queue_updates.append({"type": "status", "index": index, "status": "Done"})

        except Exception as e:
            tb = traceback.format_exc()
            self.queue_updates.append({"type": "log", "text": f"Unexpected error for {path}: {e}\n{tb}"})
            self.queue_updates.append({"type": "status", "index": index, "status": "Error"})


def main():
    app = QApplication(sys.argv)
    # Dark palette
    app.setStyle("Fusion")
    from PyQt6.QtGui import QPalette, QColor
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    app.setPalette(palette)

    w = RawConverterApp()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
