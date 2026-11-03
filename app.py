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
import json
import time
import uuid
import shutil
import socket
import mimetypes
import threading
from typing import Any
from pathlib import Path
from datetime import datetime
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
HISTORY_FILE = BASE_DIR / "history.json"

# Port the bgutil PO Token provider listens on.
POT_PORT = int(os.environ.get("POT_PORT", 4416))

# Cookie names that indicate a logged-in YouTube/Google session.
LOGIN_COOKIE_NAMES = {
    "SID", "HSID", "SSID", "SAPISID", "LOGIN_INFO",
    "__Secure-1PSID", "__Secure-3PSID",
    "__Secure-1PSIDTS", "__Secure-3PSIDTS",
}

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


def provider_running():
    """True if the PO Token provider is reachable on localhost:POT_PORT."""
    try:
        with socket.create_connection(("127.0.0.1", POT_PORT), timeout=0.5):
            return True
    except OSError:
        return False


def inspect_cookies():
    """Offline sanity check of the stored cookies.txt (no network call)."""
    if not COOKIE_FILE.exists():
        return {"ok": False, "message": "Belum ada cookies.txt. Upload dulu."}
    try:
        txt = COOKIE_FILE.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"ok": False, "message": "Gagal membaca cookies.txt."}

    found, soonest = set(), None
    for line in txt.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, expiry, name = parts[0], parts[4], parts[5]
        if ("youtube.com" in domain or "google.com" in domain) and name in LOGIN_COOKIE_NAMES:
            found.add(name)
            try:
                exp = int(expiry)
                if exp > 0 and (soonest is None or exp < soonest):
                    soonest = exp
            except ValueError:
                pass

    if not found:
        return {"ok": False, "message": "Cookie tidak berisi sesi login YouTube "
                "(anonim). Login dulu lalu export ulang."}

    now = datetime.now().timestamp()
    if soonest and soonest < now:
        return {"ok": False, "message": "Cookie login ada tapi sudah kedaluwarsa. "
                "Export ulang cookie segar (mode Incognito)."}

    note = f"Cookie login terdeteksi ({len(found)} item)."
    if soonest:
        days = int((soonest - now) / 86400)
        note += f" Masa berlaku termuda ~{days} hari lagi." if days > 0 else \
                " Hampir kedaluwarsa — sebaiknya export ulang."
    return {"ok": True, "message": note + " Catatan: cek ini offline, "
            "validitas final tetap tergantung YouTube."}


def load_history():
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def add_history(entry):
    """Append a completed download to history.json (most recent kept, max 100)."""
    hist = load_history()
    hist.insert(0, entry)
    hist = hist[:100]
    try:
        HISTORY_FILE.write_text(json.dumps(hist, ensure_ascii=False, indent=2),
                                encoding="utf-8")
    except OSError:
        pass


def base_ydl_opts() -> dict[str, Any]:
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


def prune_jobs(max_age=3600):
    """Drop finished/errored jobs older than max_age seconds so JOBS doesn't grow.

    (Served downloads are already removed in get_file; this clears jobs that
    errored or were never saved.)
    """
    now = time.time()
    for jid in list(JOBS):
        j = JOBS.get(jid) or {}
        if j.get("status") in ("done", "error") and now - j.get("created", now) > max_age:
            JOBS.pop(jid, None)

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
    opts: dict[str, Any] = {}
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


@app.route("/api/cookies/test")
def test_cookies():
    """Quick offline check that the stored cookie holds a login session."""
    return jsonify(inspect_cookies())


@app.route("/api/provider")
def provider_status():
    """Report whether the PO Token provider is up (for membership videos)."""
    return jsonify({"running": provider_running(), "port": POT_PORT})


@app.route("/api/history")
def history():
    return jsonify({"items": load_history()})


@app.route("/api/history", methods=["DELETE"])
def clear_history():
    try:
        HISTORY_FILE.unlink(missing_ok=True)
    except OSError:
        pass
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
    is_playlist=False, playlist_items=None, subs=False, sub_langs="id,en",
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

    # Subtitles (video mode only) — download + embed into the mp4.
    if subs and mode == "video":
        langs = [s.strip() for s in (sub_langs or "").split(",") if s.strip()] or ["id", "en"]
        ydl_opts.update({
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": langs,
            # Video mode has no other postprocessors, so set directly.
            "postprocessors": [
                {"key": "FFmpegEmbedSubtitle", "already_have_subtitle": False}
            ],
        })

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
            # How many entries yt-dlp actually attempted (subset if items given).
            entries = list(meta.get("entries") or [])
            requested = len(entries) if entries else len(files)
            if not files:
                job.update({
                    "status": "error",
                    "error": f"Tidak ada video yang berhasil diunduh dari {requested} item. "
                             "Kemungkinan semua members-only (cookie basi) atau privat/dihapus.",
                })
                return
            # Bundle the whole playlist into a single zip for download.
            job.update({"status": "processing", "percent": 100})
            zip_base = DOWNLOAD_DIR / job_id
            shutil.make_archive(str(zip_base), "zip", str(folder))
            zip_size = (DOWNLOAD_DIR / f"{job_id}.zip").stat().st_size

            warning = None
            if requested and len(files) < requested:
                failed = requested - len(files)
                warning = (f"{len(files)} dari {requested} video berhasil. "
                           f"{failed} gagal/dilewati — kemungkinan members-only "
                           f"(cookie kedaluwarsa) atau video privat/dihapus.")
            job.update(
                {
                    "status": "done",
                    "percent": 100,
                    "filename": f"{job_id}.zip",
                    "download_name": safe_filename(meta.get("title"), "playlist") + ".zip",
                    "title": meta.get("title") or "Playlist",
                    "file_count": len(files),
                    "requested": requested,
                    "warning": warning,
                }
            )
            add_history({
                "title": meta.get("title") or "Playlist",
                "type": f"playlist ({len(files)}/{requested} video, .zip)",
                "size": zip_size,
                "date": datetime.now().isoformat(timespec="seconds"),
            })
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
        add_history({
            "title": meta.get("title") or "(tanpa judul)",
            "type": ("audio " + (audio_format or "mp3")) if mode == "audio"
                    else f"video {height}p" if height else "video",
            "size": final.stat().st_size if final.exists() else None,
            "date": datetime.now().isoformat(timespec="seconds"),
        })
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
    subs = bool(data.get("subs"))
    sub_langs = (data.get("sub_langs") or "id,en").strip() or "id,en"
    cookie_opts = build_cookie_opts(data.get("cookie_source"), data.get("browser"))

    if height in ("", "best", None):
        height = None
    else:
        try:
            height = int(height)
        except (TypeError, ValueError):
            height = None

    prune_jobs()
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {
        "status": "starting", "percent": 0,
        "is_playlist": is_playlist, "created": time.time(),
    }

    t = threading.Thread(
        target=_run_download,
        args=(job_id, url, mode, height, audio_format, cookie_opts),
        kwargs={
            "is_playlist": is_playlist,
            "playlist_items": playlist_items,
            "subs": subs,
            "sub_langs": sub_langs,
        },
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
