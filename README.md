<div align="center">

# ▶ YouTube Membership Downloader

**A local web UI for downloading YouTube videos — including *membership* / members-only videos you have access to — powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp).**

Pick video quality, extract audio, download playlists, use membership cookies. Runs entirely on your own machine (localhost), with an Apple-style interface.

![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![Flask](https://img.shields.io/badge/Flask-3.1-000)
![powered by yt-dlp](https://img.shields.io/badge/powered%20by-yt--dlp-red)
![platform](https://img.shields.io/badge/platform-local%20%2F%20localhost-lightgrey)

**English** · [Bahasa Indonesia](README.id.md)

</div>

> [!WARNING]
> Use this **only** for content you have the right to access (e.g. a membership you pay for yourself). Follow YouTube's Terms of Service and applicable laws. This project is for personal/educational use.

---

## ✨ Features

- 🔎 **Inspect video info** — title, thumbnail, duration, and the list of actually-available qualities.
- 🎬 **Choose video quality** — Best / 2160p (4K) / 1440p / 1080p / 720p / 480p / 360p.
- 🎵 **Audio only** — MP3 / M4A / Opus / WAV.
- 📃 **Playlist** — auto-detected, pick specific items (e.g. `1-5,8`) or all; the result is bundled into a single `.zip`.
- 💬 **Subtitles** — optionally download manual + auto subtitles for chosen languages and embed them into the mp4.
- 🍪 **Membership cookies** — upload a `cookies.txt` (Netscape format) or read them straight from your browser, with a one-click **cookie test**.
- 🟢 **PO Token server status** — a live indicator shows whether the membership provider is up.
- 🗂️ **Download history** — a running list of what you've downloaded.
- 📊 **Real-time progress** + output filename **matches the video title**.
- 🧹 **Auto-cleanup** — the server copy is deleted automatically once the file finishes downloading to your computer (no duplicates).
- 🌗 **Modern UI** — frosted glass, automatic dark mode, responsive.

---

## 🧩 Requirements

| Requirement | Used for | Required? |
|---|---|---|
| **Python 3.9+** | running the app | ✅ Required |
| **ffmpeg** | merging video+audio & converting audio | ✅ Required |
| **Node.js** | running the PO Token server (membership/SABR videos) | ⚠️ For membership |
| **deno** | solving YouTube's "nsig challenge" | ⚠️ For membership |
| **Docker** | alternative PO Token server (instead of Node) | ⭕ Optional |

**Install prerequisites (macOS / Homebrew):**
```bash
brew install python ffmpeg node deno
```
- Ubuntu/Debian: `sudo apt install python3 python3-venv ffmpeg nodejs` + [install deno](https://docs.deno.com/runtime/getting_started/installation/)
- Windows: install Python, ffmpeg, Node, and deno from their official sites and make sure they're on your PATH.

> **Regular (non-membership) videos** only need Python + ffmpeg. Node & deno are required only for membership videos protected by YouTube's SABR streaming.

---

## 📦 Installation

```bash
cd yt-membership
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

> [!TIP]
> If your shell has a `python` alias (e.g. from ServBay/Homebrew), `source venv/bin/activate` can get "hijacked". **The safest option is to run with the explicit path: `./venv/bin/python`** (see Troubleshooting).

---

## 🚀 Running

> All commands below run **from inside the project folder**. Open a terminal and `cd` into it first, e.g. `cd ~/Developer/Project/Python/yt-membership`.

### ⚡ One-click (macOS/Linux)

```bash
./start.sh
```
Starts the PO Token server (if built) **and** the Flask app, and stops the provider on Ctrl+C. Then open **http://127.0.0.1:5050**. Prefer separate terminals? Use the manual steps below.

### A. Regular (non-membership) videos — just 1 terminal

```bash
./venv/bin/python app.py
```
Open **http://127.0.0.1:5050**

### B. Membership videos — needs 2 terminals

**Terminal 1 — PO Token server** (keep it open while in use):
```bash
cd pot-provider/server
node build/main.js
```
Wait until you see: `Started POT server (v2.0.2) on ... 127.0.0.1:4416`
➡ Don't close it. This process intentionally doesn't return to the prompt — that's normal.

**Terminal 2 — the Flask app** (a new terminal, from the project folder):
```bash
./venv/bin/python app.py
```
Open **http://127.0.0.1:5050**

> Default port is **5050** (not 5000) because modern macOS uses port 5000 for the AirPlay Receiver. Change it if needed: `PORT=8000 ./venv/bin/python app.py`
>
> The debugger/auto-reload is off by default. For development, enable it with `DEBUG=1 ./venv/bin/python app.py`. Leftover files in `downloads/` from previous runs are cleared automatically on startup.

#### First-time PO Token server setup (once)
The `pot-provider/` folder is **not** included in the repo (third-party). From the project folder, clone & build it:
```bash
git clone --depth 1 --branch 2.0.2 \
  https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git pot-provider
cd pot-provider/server
npm install
npx tsc
```
Then run `node build/main.js` as shown above.

<details>
<summary>Alternative: use Docker (instead of Node)</summary>

```bash
open -a Docker   # wait for Docker Desktop to be running
docker run --name bgutil-provider -d --restart unless-stopped -p 4416:4416 brainicism/bgutil-ytdlp-pot-provider
```
</details>

---

## 📖 How to use (in the browser)

1. **Open** http://127.0.0.1:5050

2. **(Membership only) Set up cookies** — section **1 · Cookies**:
   - **Cookie source → File cookies.txt (upload)** → pick the file → click **Simpan** (Save).
   - The indicator turns green: *"cookies.txt tersimpan"* (saved).
   - How to get `cookies.txt` → see [Membership cookies](#-membership-cookies) below.
   - For public videos, leave it on **Tanpa cookie** (no cookie).

3. **Enter the URL** — section **2 · Video atau playlist**:
   - Paste a video or playlist URL → click **Cek** (Check).
   - Title, thumbnail, and duration appear (or the playlist contents).

4. **Pick a format** — section **3 · Format & kualitas**:
   - **🎬 Video + Audio** → choose a quality (e.g. 1080p), or
   - **🎵 Audio saja** (audio only) → choose a format (MP3/M4A/Opus/WAV).
   - For playlists: fill in *Item playlist* (e.g. `1-5,8`) or leave empty for all.

5. **Download** — click the **⬇ Download** button and watch the progress bar.

6. **Save to computer** — when done, click **⬇ Simpan file ke komputer** (Save file to computer).
   - The file is saved with a name matching the video title.
   - The server copy is deleted automatically. **Click once only** (a second click returns 404 because it's already cleaned up).

---

## 🍪 Membership cookies

Members-only videos require cookies from an account that has the membership.

### Method A — Upload cookies.txt (most reliable)
1. Install the **"Get cookies.txt LOCALLY"** extension (Chrome/Firefox).
2. **Open an Incognito/Private window**, log into YouTube with the member account, and open the membership video (make sure it plays).
3. Export `cookies.txt` via the extension **from that incognito window**.
4. **Close the incognito window immediately** without browsing further (so the cookies aren't rotated/expired).
5. In the app: **Cookie source → File cookies.txt** → pick the file → **Simpan**.

> 💡 **Why Incognito?** YouTube rotates session cookies on every use. Exporting from incognito and closing it right away keeps the cookies stable and slower to expire.

### Method B — Read directly from the browser
In the app: **Cookie source → Ambil dari browser** (read from browser) → pick your browser.
> If you hit a `database is locked` error, close the browser first, or use Method A.

---

## 📁 Project structure

```
yt-membership/
├── app.py                  # Flask backend (yt-dlp wrapper)
├── requirements.txt
├── templates/index.html    # Main page (Jinja)
├── static/
│   ├── css/style.css       # Styling (Apple-style)
│   └── js/app.js           # Frontend logic
├── cookies/cookies.txt     # Active cookie (created on upload)
├── downloads/              # Temporary files (cleaned up after download)
└── pot-provider/           # PO Token server (bgutil) for membership videos
```

---

## 🛠️ Troubleshooting

| Symptom | Cause & fix |
|---|---|
| Page renders unstyled, shows raw `{{ ... }}` text | You opened the HTML file directly (`file://`). You **must** go through http://127.0.0.1:5050 (the Flask server). |
| `ModuleNotFoundError: No module named 'flask'` even though venv is active | A `python` alias is hijacking the venv. Run **`./venv/bin/python app.py`**, or `unalias python` first. |
| `Address already in use` / port 5000 | Port 5000 is used by AirPlay on macOS. This app defaults to **5050**; override with `PORT=8000 ...`. |
| `This video is available to this channel's members...` | Cookies aren't set up **or have expired**. Re-export fresh cookies (Method A, incognito). |
| `Only images are available` / `Requested format is not available` | The PO Token server is down. Make sure Terminal 1 (`node build/main.js`) is alive on port **4416**. |
| Membership formats don't appear even with correct cookies | You need **deno** installed (for the nsig solver) + the PO Token server running. |
| yt-dlp outdated / YouTube changed | Update: `./venv/bin/pip install -U yt-dlp` (do this regularly). |

---

## 🔒 Security & privacy

- The app **binds to 127.0.0.1** only — it can't be reached from outside your computer.
- `cookies.txt` is equivalent to your Google account login session — **never share it**. It's already in `.gitignore`.
- `downloads/` and `cookies/` are not committed (see `.gitignore`).

---

## 🙏 Credits

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — the download engine
- [bgutil-ytdlp-pot-provider](https://github.com/Brainicism/bgutil-ytdlp-pot-provider) — PO Token provider
- [Flask](https://flask.palletsprojects.com/) · [ffmpeg](https://ffmpeg.org/)

---

## 📄 License

[MIT](LICENSE) © rahmatez
