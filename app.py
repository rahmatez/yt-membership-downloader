"""
YouTube Membership Downloader — local web UI around yt-dlp.

Run:  python app.py   then open http://127.0.0.1:5050

Features:
  - Fetch available video qualities for a URL
  - Download video+audio at a chosen quality, or extract audio only (mp3/m4a)
  - Provide cookies (upload a cookies.txt, or read them from an installed browser)
    so membership / members-only videos you have access to can be downloaded.
"""

import os
import re
import uuid
import shutil
import mimetypes
import threading
from pathlib import Path
from urllib.parse import quote

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    Response,
    abort,
)
import yt_dlp

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
COOKIE_DIR = BASE_DIR / "cookies"
DOWNLOAD_DIR.mkdir(exist_ok=True)
COOKIE_DIR.mkdir(exist_ok=True)

COOKIE_FILE = COOKIE_DIR / "cookies.txt"

# YouTube now forces an "nsig" JS challenge; yt-dlp must run a challenge solver
# (EJS, fetched from GitHub and executed via a JS runtime like deno/node) or most
# formats are dropped and only storyboards remain. Fetched once, then cached.
REMOTE_COMPONENTS = ["ejs:github"]


def safe_filename(name, fallback="download"):
    """Make a title safe to use as a filename for the browser download."""
    name = (name or "").strip()
    # Drop characters that are illegal/awkward in filenames across OSes.
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name)
    name = name.strip(". ")
    return name[:180] or fallback


# Map noisy yt-dlp errors to short, actionable hints for the UI.
_ERROR_HINTS = [
    (("members on level", "members-only", "members only", "join this channel"),
     "Video khusus member. Cookie belum terpasang atau sudah kedaluwarsa — "
     "export ulang cookie segar (mode Incognito) lalu Simpan."),
    (("only images are available", "requested format is not available", "forcing sabr"),
     "Format video tidak tersedia. Server PO Token kemungkinan mati — pastikan "
     "'node build/main.js' jalan di port 4416, lalu coba lagi."),
    (("sign in to confirm", "not a bot", "confirm you're not a bot"),
     "YouTube minta verifikasi login. Pasang cookie segar dari akunmu (mode Incognito)."),
    (("nsig", "n challenge", "challenge solving", "ejs", "javascript runtime"),
     "Butuh runtime JS 'deno' untuk memecahkan proteksi YouTube. Install deno lalu ulangi."),
    (("http error 429", "too many requests"),
     "Terlalu banyak permintaan (rate limit YouTube). Tunggu beberapa menit lalu coba lagi."),
    (("private video",),
     "Video ini privat — tidak bisa diunduh."),
    (("video unavailable", "this video is unavailable", "has been removed"),
     "Video tidak tersedia atau sudah dihapus."),
    (("is not a valid url", "unsupported url"),
     "URL tidak valid. Pastikan ini tautan YouTube yang benar."),
]


def friendly_error(raw):
    """Translate a raw yt-dlp error into a short, human-friendly message."""
    msg = str(raw or "")
    low = msg.lower()
    for keys, hint in _ERROR_HINTS:
        if any(k in low for k in keys):
            return hint
    cleaned = re.sub(r"^ERROR:\s*", "", msg).strip()
    return cleaned[:300] or "Terjadi kesalahan tak terduga."


def cleanup_downloads():
    """Remove leftover files/folders from previous runs.

    Served files are deleted on download; anything left in downloads/ at startup
    is an orphan (a download that was never saved, now unreachable because its
    in-memory job is gone), so it is safe to clear.
    """
    removed = 0
    for p in DOWNLOAD_DIR.iterdir():
        try:
            shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def base_ydl_opts():
    """Common yt-dlp options shared by info and download calls."""
    return {
        "quiet": True,
        "no_warnings": True,
        "remote_components": REMOTE_COMPONENTS,
    }

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB cap for cookie uploads

# job_id -> progress dict
JOBS = {}

# Browsers yt-dlp can read cookies from directly.
SUPPORTED_BROWSERS = [
    "chrome",
    "chromium",
    "brave",
    "edge",
    "firefox",
    "opera",
    "safari",
    "vivaldi",
]


def build_cookie_opts(cookie_source, browser):
    """Return yt-dlp options for cookies based on the chosen source."""
    opts = {}
    if cookie_source == "file" and COOKIE_FILE.exists():
        opts["cookiefile"] = str(COOKIE_FILE)
    elif cookie_source == "browser" and browser in SUPPORTED_BROWSERS:
        # (browser, profile, keyring, container)
        opts["cookiesfrombrowser"] = (browser, None, None, None)
    return opts


@app.route("/")
def index():
    return render_template(
        "index.html",
        has_cookie_file=COOKIE_FILE.exists(),
        browsers=SUPPORTED_BROWSERS,
    )


@app.route("/api/cookies", methods=["POST"])
def upload_cookies():
    """Accept a Netscape-format cookies.txt upload and store it."""
    if "cookies" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["cookies"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400
    content = f.read().decode("utf-8", errors="replace")
    if "# Netscape HTTP Cookie File" not in content and "\t" not in content:
        return jsonify(
            {"error": "This does not look like a Netscape cookies.txt file."}
        ), 400
    COOKIE_FILE.write_text(content, encoding="utf-8")
    return jsonify({"ok": True})


@app.route("/api/cookies", methods=["DELETE"])
def delete_cookies():
    if COOKIE_FILE.exists():
        COOKIE_FILE.unlink()
    return jsonify({"ok": True})


@app.route("/api/info", methods=["POST"])
def info():
    """Return metadata for a single video, or the entry list for a playlist."""
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400

    cookie_opts = build_cookie_opts(data.get("cookie_source"), data.get("browser"))

    # Step 1: a flat extract — fast, and tells us playlist vs single video
    # without resolving every entry in a playlist.
    flat_opts = base_ydl_opts()
    flat_opts.update({
        "skip_download": True,
        "extract_flat": "in_playlist",
    })
    flat_opts.update(cookie_opts)

    try:
        with yt_dlp.YoutubeDL(flat_opts) as ydl:
            flat = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        return jsonify({"error": friendly_error(e)}), 400
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": friendly_error(e)}), 500

    is_playlist = flat.get("_type") == "playlist" or bool(flat.get("entries"))

    if is_playlist:
        entries = []
        for e in flat.get("entries") or []:
            if not e:
                continue
            entries.append(
                {
                    "title": e.get("title") or e.get("id"),
                    "duration": e.get("duration"),
                }
            )
        return jsonify(
            {
                "is_playlist": True,
                "title": flat.get("title") or "Playlist",
                "uploader": flat.get("uploader") or flat.get("channel"),
                "playlist_count": len(entries),
                "entries": entries,
            }
        )

    # Step 2: single video — full extract to list the real available heights.
    full_opts = base_ydl_opts()
    full_opts.update({"skip_download": True})
    full_opts.update(cookie_opts)

    try:
        with yt_dlp.YoutubeDL(full_opts) as ydl:
            meta = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        return jsonify({"error": friendly_error(e)}), 400
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": friendly_error(e)}), 500

    heights = set()
    has_audio = False
    for fmt in meta.get("formats", []):
        if fmt.get("vcodec") not in (None, "none") and fmt.get("height"):
            heights.add(int(fmt["height"]))
        if fmt.get("acodec") not in (None, "none"):
            has_audio = True

    return jsonify(
        {
            "is_playlist": False,
            "title": meta.get("title"),
            "uploader": meta.get("uploader"),
            "thumbnail": meta.get("thumbnail"),
            "duration": meta.get("duration"),
            "is_live": meta.get("is_live", False),
            "heights": sorted(heights, reverse=True),
            "has_audio": has_audio,
        }
    )


def _progress_hook(job_id):
    def hook(d):
        job = JOBS.get(job_id)
        if job is None:
            return
        status = d.get("status")
        # For playlists, surface which entry we're on.
        info_dict = d.get("info_dict") or {}
        pl_index = info_dict.get("playlist_index")
        pl_count = info_dict.get("n_entries") or info_dict.get("playlist_count")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes") or 0
            pct = (downloaded / total * 100) if total else 0
            job.update(
                {
                    "status": "downloading",
                    "percent": round(pct, 1),
                    "speed": d.get("speed"),
                    "eta": d.get("eta"),
                    "downloaded_bytes": downloaded,
                    "total_bytes": total,
                    "playlist_index": pl_index,
                    "playlist_count": pl_count,
                }
            )
        elif status == "finished":
            # Download of one stream done; post-processing (merge/convert) may follow.
            job.update({"status": "processing", "percent": 100})

    return hook


def _run_download(
    job_id, url, mode, height, audio_format, cookie_opts,
    is_playlist=False, playlist_items=None,
):
    job = JOBS[job_id]

    ydl_opts = base_ydl_opts()
    ydl_opts.update({
        "noprogress": True,
        "progress_hooks": [_progress_hook(job_id)],
        "restrictfilenames": False,
        "windowsfilenames": True,
        "ignoreerrors": is_playlist,  # keep going if one entry fails
    })
    ydl_opts.update(cookie_opts)

    if is_playlist:
        # Each playlist goes into its own folder, later zipped for download.
        folder = DOWNLOAD_DIR / job_id
        folder.mkdir(exist_ok=True)
        ydl_opts["outtmpl"] = str(
            folder / "%(playlist_index)s - %(title).120s.%(ext)s"
        )
        ydl_opts["noplaylist"] = False
        if playlist_items:
            ydl_opts["playlist_items"] = playlist_items
    else:
        ydl_opts["outtmpl"] = str(DOWNLOAD_DIR / f"{job_id}__%(title).150s.%(ext)s")
        ydl_opts["noplaylist"] = True  # don't grab a whole list from a watch URL

    if mode == "audio":
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_format or "mp3",
                "preferredquality": "0",  # best
            }
        ]
    else:  # video
        if height:
            ydl_opts["format"] = (
                f"bestvideo[height<={height}]+bestaudio/"
                f"best[height<={height}]/best"
            )
        else:
            ydl_opts["format"] = "bestvideo+bestaudio/best"
        ydl_opts["merge_output_format"] = "mp4"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            meta = ydl.extract_info(url, download=True)

        if is_playlist:
            folder = DOWNLOAD_DIR / job_id
            files = [p for p in folder.glob("*") if p.is_file()]
            if not files:
                job.update(
                    {"status": "error", "error": "No files were downloaded."}
                )
                return
            # Bundle the whole playlist into a single zip for download.
            job.update({"status": "processing", "percent": 100})
            zip_base = DOWNLOAD_DIR / job_id
            shutil.make_archive(str(zip_base), "zip", str(folder))
            job.update(
                {
                    "status": "done",
                    "percent": 100,
                    "filename": f"{job_id}.zip",
                    "download_name": safe_filename(meta.get("title"), "playlist") + ".zip",
                    "title": meta.get("title") or "Playlist",
                    "file_count": len(files),
                }
            )
            return

        # Single video: resolve the final filename (after any postprocessing).
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            filename = ydl.prepare_filename(meta)
        final = Path(filename)
        if mode == "audio":
            final = final.with_suffix("." + (audio_format or "mp3"))
        elif not final.exists():
            final = final.with_suffix(".mp4")

        if not final.exists():
            # Fall back to whatever file starts with this job id.
            matches = list(DOWNLOAD_DIR.glob(f"{job_id}__*"))
            if matches:
                final = matches[0]

        job.update(
            {
                "status": "done",
                "percent": 100,
                "filename": final.name,
                "download_name": safe_filename(meta.get("title")) + final.suffix,
                "title": meta.get("title"),
            }
        )
    except yt_dlp.utils.DownloadError as e:
        job.update({"status": "error", "error": friendly_error(e)})
    except Exception as e:  # noqa: BLE001
        job.update({"status": "error", "error": friendly_error(e)})


@app.route("/api/download", methods=["POST"])
def download():
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400

    mode = data.get("mode", "video")  # "video" | "audio"
    height = data.get("height")  # int or None
    audio_format = data.get("audio_format", "mp3")
    is_playlist = bool(data.get("is_playlist"))
    playlist_items = (data.get("playlist_items") or "").strip() or None
    cookie_opts = build_cookie_opts(data.get("cookie_source"), data.get("browser"))

    if height in ("", "best", None):
        height = None
    else:
        try:
            height = int(height)
        except (TypeError, ValueError):
            height = None

    job_id = uuid.uuid4().hex
    JOBS[job_id] = {"status": "starting", "percent": 0, "is_playlist": is_playlist}

    t = threading.Thread(
        target=_run_download,
        args=(job_id, url, mode, height, audio_format, cookie_opts),
        kwargs={"is_playlist": is_playlist, "playlist_items": playlist_items},
        daemon=True,
    )
    t.start()

    return jsonify({"job_id": job_id})


@app.route("/api/progress/<job_id>")
def progress(job_id):
    job = JOBS.get(job_id)
    if job is None:
        return jsonify({"error": "Unknown job"}), 404
    return jsonify(job)


@app.route("/api/file/<job_id>")
def get_file(job_id):
    job = JOBS.get(job_id)
    if not job or job.get("status") != "done":
        abort(404)
    filename = job.get("filename")
    if not filename:
        abort(404)

    file_path = DOWNLOAD_DIR / filename
    if not file_path.exists():
        abort(404)
    playlist_folder = DOWNLOAD_DIR / job_id  # only exists for playlists
    download_name = job.get("download_name") or filename
    size = file_path.stat().st_size

    def generate():
        # Stream the file in chunks; the finally block runs once the transfer
        # finishes (or the client disconnects), deleting the local copy so we
        # don't keep duplicates. This is more reliable than Response.call_on_close
        # on the Werkzeug dev server.
        try:
            with open(file_path, "rb") as fh:
                while True:
                    chunk = fh.read(256 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            try:
                if file_path.exists():
                    file_path.unlink()
                if playlist_folder.is_dir():
                    shutil.rmtree(playlist_folder, ignore_errors=True)
            except OSError:
                pass
            JOBS.pop(job_id, None)

    mime = mimetypes.guess_type(download_name)[0] or "application/octet-stream"
    ascii_name = download_name.encode("ascii", "ignore").decode() or "download"
    headers = {
        "Content-Length": str(size),
        "Content-Disposition": (
            f'attachment; filename="{ascii_name}"; '
            f"filename*=UTF-8''{quote(download_name)}"
        ),
    }
    return Response(generate(), mimetype=mime, headers=headers)


if __name__ == "__main__":
    # Local use only — bind to localhost.
    # Port 5000 is taken by AirPlay Receiver on modern macOS, so default to 5050.
    port = int(os.environ.get("PORT", 5050))
    # Debugger/reloader off by default (safer); enable with DEBUG=1 for development.
    debug = os.environ.get("DEBUG", "0") == "1"

    # Clear orphan files from previous runs (only once, not in the reloader child).
    if not debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        n = cleanup_downloads()
        if n:
            print(f"[cleanup] {n} file/folder sisa dibersihkan dari downloads/")

    print(f" * YouTube Membership Downloader → http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=debug)
