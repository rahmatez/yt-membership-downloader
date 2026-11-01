<div align="center">

# ▶ YouTube Membership Downloader

**Web UI lokal untuk mengunduh video YouTube — termasuk video *membership* / members-only yang kamu punya aksesnya — dengan [yt-dlp](https://github.com/yt-dlp/yt-dlp).**

Pilih kualitas video, ekstrak audio, unduh playlist, pakai cookie membership. Jalan sepenuhnya di komputermu (localhost), tampilan ala Apple.

</div>

> [!WARNING]
> Gunakan **hanya** untuk konten yang kamu punya hak aksesnya (mis. membership yang kamu bayar sendiri). Patuhi Terms of Service YouTube dan hukum yang berlaku. Proyek ini untuk keperluan pribadi/edukasi.

---

## ✨ Fitur

- 🔎 **Cek info video** — judul, thumbnail, durasi, dan daftar kualitas yang benar-benar tersedia.
- 🎬 **Pilih kualitas video** — Terbaik / 2160p (4K) / 1440p / 1080p / 720p / 480p / 360p.
- 🎵 **Audio saja** — MP3 / M4A / Opus / WAV.
- 📃 **Playlist** — deteksi otomatis, pilih item tertentu (mis. `1-5,8`) atau semua; hasil dikemas jadi satu `.zip`.
- 🍪 **Cookie membership** — upload `cookies.txt` (format Netscape) atau ambil langsung dari browser.
- 📊 **Progress real-time** + nama file otomatis **sesuai judul video**.
- 🧹 **Auto-bersih** — salinan di server dihapus otomatis setelah file selesai diunduh ke komputer (tanpa duplikat).
- 🌗 **UI modern** — frosted glass, mode gelap otomatis, responsif.

---

## 🧩 Prasyarat

| Kebutuhan | Untuk apa | Wajib? |
|---|---|---|
| **Python 3.9+** | menjalankan aplikasi | ✅ Wajib |
| **ffmpeg** | menggabungkan video+audio & konversi audio | ✅ Wajib |
| **Node.js** | menjalankan server PO Token (video membership/SABR) | ⚠️ Untuk membership |
| **deno** | memecahkan "nsig challenge" YouTube | ⚠️ Untuk membership |
| **Docker** | alternatif server PO Token (pengganti Node) | ⭕ Opsional |

**Install prasyarat (macOS / Homebrew):**
```bash
brew install python ffmpeg node deno
```
- Ubuntu/Debian: `sudo apt install python3 python3-venv ffmpeg nodejs` + [install deno](https://docs.deno.com/runtime/getting_started/installation/)
- Windows: install Python, ffmpeg, Node, deno dari situs resminya dan pastikan masuk PATH.

> Video **biasa (non-membership)** cukup butuh Python + ffmpeg. Node & deno hanya diperlukan untuk video membership yang kena proteksi SABR YouTube.

---

## 📦 Instalasi

```bash
cd yt-membership
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

> [!TIP]
> Jika shell-mu punya alias `python` (mis. dari ServBay/Homebrew), aktivasi `source venv/bin/activate` bisa "terbajak". **Paling aman jalankan pakai path langsung: `./venv/bin/python`** (lihat Troubleshooting).

---

## 🚀 Menjalankan

### A. Video biasa (non-membership) — cukup 1 terminal

```bash
cd yt-membership
./venv/bin/python app.py
```
Buka **http://127.0.0.1:5050**

### B. Video membership — butuh 2 terminal

**Terminal 1 — Server PO Token** (biarkan terbuka selama dipakai):
```bash
cd yt-membership/pot-provider/server
node build/main.js
```
Tunggu sampai muncul: `Started POT server (v2.0.2) on ... 127.0.0.1:4416`
➡ Jangan ditutup. Proses ini memang tidak kembali ke prompt — itu normal.

**Terminal 2 — Aplikasi Flask:**
```bash
cd yt-membership
./venv/bin/python app.py
```
Buka **http://127.0.0.1:5050**

> Port default **5050** (bukan 5000) karena di macOS modern port 5000 dipakai AirPlay Receiver. Ganti bila perlu: `PORT=8000 ./venv/bin/python app.py`

#### Setup server PO Token pertama kali (hanya sekali)
Folder `pot-provider/` tidak ikut di repo (pihak ketiga). Clone & build dulu:
```bash
cd yt-membership
git clone --depth 1 --branch 2.0.2 \
  https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git pot-provider
cd pot-provider/server
npm install
npx tsc
```
Lalu jalankan `node build/main.js` seperti di atas.

<details>
<summary>Alternatif: pakai Docker (pengganti Node)</summary>

```bash
open -a Docker   # tunggu Docker Desktop running
docker run --name bgutil-provider -d --restart unless-stopped -p 4416:4416 brainicism/bgutil-ytdlp-pot-provider
```
</details>

---

## 📖 Langkah pemakaian (di browser)

1. **Buka** http://127.0.0.1:5050

2. **(Khusus membership) Pasang cookie** — bagian **1 · Cookies**:
   - **Sumber cookie → File cookies.txt (upload)** → pilih file → klik **Simpan**.
   - Indikator berubah hijau: *"cookies.txt tersimpan"*.
   - Cara dapat `cookies.txt` → lihat bagian [Cookie membership](#-cookie-membership) di bawah.
   - Untuk video publik, biarkan **Tanpa cookie**.

3. **Masukkan URL** — bagian **2 · Video atau playlist**:
   - Tempel URL video atau playlist → klik **Cek**.
   - Muncul judul, thumbnail, durasi (atau daftar isi playlist).

4. **Pilih format** — bagian **3 · Format & kualitas**:
   - **🎬 Video + Audio** → pilih kualitas (mis. 1080p), atau
   - **🎵 Audio saja** → pilih format (MP3/M4A/Opus/WAV).
   - Untuk playlist: isi *Item playlist* (mis. `1-5,8`) atau kosongkan untuk semua.

5. **Download** — klik tombol **⬇ Download**, pantau progress bar.

6. **Simpan ke komputer** — setelah selesai, klik **⬇ Simpan file ke komputer**.
   - File tersimpan dengan nama sesuai judul video.
   - Salinan di server otomatis dihapus. **Klik sekali saja** (klik kedua akan 404 karena sudah dibersihkan).

---

## 🍪 Cookie membership

Video members-only butuh cookie dari akun yang punya membership.

### Cara A — Upload cookies.txt (paling andal)
1. Pasang ekstensi **"Get cookies.txt LOCALLY"** (Chrome/Firefox).
2. **Buka jendela Incognito/Private**, login YouTube dengan akun member, buka video membership-nya (pastikan bisa diputar).
3. Export `cookies.txt` lewat ekstensi **dari jendela incognito itu**.
4. **Langsung tutup** jendela incognito tanpa browsing lagi (biar cookie tidak dirotasi/kadaluarsa).
5. Di aplikasi: **Sumber cookie → File cookies.txt** → pilih file → **Simpan**.

> 💡 **Kenapa Incognito?** YouTube merotasi cookie sesi setiap dipakai. Export dari incognito lalu langsung ditutup membuat cookie lebih stabil dan tidak cepat basi.

### Cara B — Ambil langsung dari browser
Di aplikasi: **Sumber cookie → Ambil dari browser** → pilih browser kamu.
> Kalau muncul error `database is locked`, tutup dulu browsernya, atau pakai Cara A.

---

## 📁 Struktur folder

```
yt-membership/
├── app.py                  # Backend Flask (wrapper yt-dlp)
├── requirements.txt
├── templates/index.html    # Halaman utama (Jinja)
├── static/
│   ├── css/style.css       # Styling (Apple-style)
│   └── js/app.js           # Logika frontend
├── cookies/cookies.txt     # Cookie aktif (otomatis dibuat saat upload)
├── downloads/              # File sementara (dibersihkan setelah diunduh)
└── pot-provider/           # Server PO Token (bgutil) untuk video membership
```

---

## 🛠️ Troubleshooting

| Gejala | Penyebab & solusi |
|---|---|
| Halaman tampil polos, muncul teks `{{ ... }}` | Kamu membuka file HTML langsung (`file://`). **Harus lewat** http://127.0.0.1:5050 (server Flask). |
| `ModuleNotFoundError: No module named 'flask'` padahal venv aktif | Alias `python` membajak venv. Jalankan **`./venv/bin/python app.py`**, atau `unalias python` dulu. |
| `Address already in use` / port 5000 | Port 5000 dipakai AirPlay di macOS. App ini sudah default **5050**; ganti dengan `PORT=8000 ...`. |
| `This video is available to this channel's members...` | Cookie belum terpasang **atau sudah basi**. Export ulang cookie segar (Cara A, incognito). |
| `Only images are available` / `Requested format is not available` | Server PO Token mati. Pastikan Terminal 1 (`node build/main.js`) hidup di port **4416**. |
| Format video membership tidak muncul meski cookie benar | Butuh **deno** terpasang (untuk nsig solver) + server PO Token jalan. |
| yt-dlp usang / YouTube berubah | Update: `./venv/bin/pip install -U yt-dlp` (lakukan rutin). |

---

## 🔒 Keamanan & privasi

- Aplikasi **bind ke 127.0.0.1** saja — tidak bisa diakses dari luar komputermu.
- File `cookies.txt` setara sesi login akun Google-mu — **jangan dibagikan**. Sudah masuk `.gitignore`.
- `downloads/` dan `cookies/` tidak ikut ter-commit (lihat `.gitignore`).

---

## 🙏 Kredit

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — mesin pengunduh
- [bgutil-ytdlp-pot-provider](https://github.com/Brainicism/bgutil-ytdlp-pot-provider) — penyedia PO Token
- [Flask](https://flask.palletsprojects.com/) · [ffmpeg](https://ffmpeg.org/)
