# RAW Converter (PyQt6)

Lightweight desktop app to batch-convert camera RAW files (.CR2, .NEF, .ARW, .DNG) into WhatsApp-ready JPEGs.

**Highlights**
- Dark-themed PyQt6 GUI with drag-and-drop and folder import
- Per-file progress bars, queue with statuses (Pending / Converting / Done / Error)
- Progressive, optimized, configurable quality
- Responsive batch conversion using a thread pool (user-selectable worker count or CPU*4)
- Persistent settings saved next to the script (`raw_converter_settings.json`)
- Default output folder created automatically (`imgout` next to the script) when none is selected

## Requirements
- Python 3.10+
- Pip packages (see `requirements.txt`)

System prerequisites:
- `rawpy` requires LibRaw. On many Linux distributions you may need build tools and libraw-dev / libraw packages installed. On Windows and macOS the `rawpy` wheel often bundles the required pieces but may still need a C compiler for some installs.

Install Python dependencies:

```bash
python -m pip install -r requirements.txt
```

Run the application (in the project directory):

```bash
python raw_converter.py
```

## Usage
- Add files or folders with the top-left buttons, or drag-and-drop RAW files into the queue area.
- If you don't select an output folder, the app will create and use `imgout` next to `raw_converter.py` and persist that path.
- Settings you can adjust in the Settings bar:
	- `JPEG Quality` slider (70–100)
	- `Resize max dimension to 2048px` (recommended for messaging)
	- `Workers` spinbox to choose number of worker threads
	- `Use max available workers (CPU*4)` toggle (overrides spinbox)
- Click `Start Batch Conversion` to begin. Each file shows an individual progress bar and status. The log console shows conversions and saved-size summaries.
- `Open Output Folder` opens the selected/default output folder in the OS file explorer.

## Settings file
- The app stores user settings in `raw_converter_settings.json` next to `raw_converter.py`.
- Persisted values include: `workers`, `use_max_workers`, `jpeg_quality`, `resize_cap`, and `output_folder`.

## Build / Packaging
- The repo includes a GitHub Actions workflow at `.github/workflows/build-release.yml` that builds executables with PyInstaller for Windows, macOS (x64 & arm64), and Linux when a pull request from `dev` into `main` is merged. Artifacts are uploaded as zip files.
- Locally you can create a single-file executable with PyInstaller:

```bash
python -m pip install pyinstaller
pyinstaller --noconfirm --onefile --name raw-converter raw_converter.py
```

## Troubleshooting
- If `rawpy` install fails, ensure system build tools and `libraw` development headers are available: e.g. `sudo apt install build-essential libraw-dev` on Debian/Ubuntu.
- If the UI seems unresponsive during a long single-file conversion, try increasing the worker count or running fewer concurrent conversions — CPU, memory, and disk I/O are limiting factors.

## Privacy & Safety
- The app reads RAW files and writes JPEGs to the output folder you choose (or the default `imgout`). No data is transmitted externally by the app.

## [License](LICENSE)