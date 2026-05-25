# Photo Organizer

This tool scans a Google Photos backup, clusters images that are likely from
the same event (based on EXIF timestamp and GPS), and asks a local LLaVA model
(via Ollama) to suggest a short album title for each cluster.

Quick start

1. Ensure Ollama is installed and running locally and you have pulled a multimodal LLaVA model (e.g. `llava`).

```bash
# Example (adjust model name if different)
ollama pull llava
```

2. Install Python deps:

```bash
pip install -r requirements.txt
```

3. Run the organizer on your backup folder:

```bash
python organize_photos.py --dir ./my_google_photos --time-hours 3 --dist-meters 1000 --max-samples 3
```

Notes
- The script uses EXIF `DateTimeOriginal` (or `DateTime*`) to order photos.
- If GPS is present, clusters require both time and a short geographic distance.
- The script copies files into `Organized_Albums/YYYY-MM-DD - Title/` (preserves originals).
- If the Ollama Python client isn't available, the script falls back to an HTTP request to the local Ollama API (if `requests` is installed).

If you want, I can run a small smoke test or adjust thresholds for your dataset.
