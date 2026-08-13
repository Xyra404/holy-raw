# RAW Converter (PyQt6)

Desktop app to convert camera RAW files (.CR2, .NEF, .ARW, .DNG) into optimized JPEGs.

Requirements
- Python 3.10+
- System-level libraw (rawpy may require build tools on some platforms)

Install Python packages:

```bash
python -m pip install -r requirements.txt
```

Optional: none (pngquant/Png output removed — app outputs JPEG only)
Run the app:

```bash
python raw_converter.py
```

Usage
- Use "Add Files" or "Add Folder" (or drag-and-drop) to populate the queue.
- Choose output folder.
-- Select options (resize cap, JPEG quality) on the settings bar.
- Click "Start Batch Conversion". The UI remains responsive during conversion.