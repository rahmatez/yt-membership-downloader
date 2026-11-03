/* YouTube Membership Downloader — frontend logic */

const $ = (id) => document.getElementById(id);
let mode = "video";
let isPlaylist = false;
let pollTimer = null;

const PRESET_HEIGHTS = [2160, 1440, 1080, 720, 480, 360];

/* ---------- helpers ---------- */
function fmtBytes(b) {
  if (!b) return "0 B";
  const u = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (b >= 1024 && i < u.length - 1) { b /= 1024; i++; }
  return b.toFixed(1) + " " + u[i];
}
function fmtDur(s) {
  if (!s) return "";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  return (h ? h + ":" : "") + String(m).padStart(h ? 2 : 1, "0") +
    ":" + String(sec).padStart(2, "0");
}
function msg(el, text, kind) {
  el.innerHTML = text ? `<div class="msg ${kind} reveal">${text}</div>` : "";
}
function presetLabel(h) {
  return h + "p" + (h >= 2160 ? " · 4K" : h >= 1440 ? " · 2K" : "");
}
function fillHeights(heights) {
  const sel = $("height");
  sel.innerHTML = '<option value="best">Terbaik yang tersedia</option>';
  (heights || []).forEach((h) => {
    const o = document.createElement("option");
    o.value = h;
    o.textContent = presetLabel(h);
    sel.appendChild(o);
  });
}

/* ---------- cookies ---------- */
$("cookieSource").addEventListener("change", (e) => {
  $("fileBlock").classList.toggle("hidden", e.target.value !== "file");
  $("browserBlock").classList.toggle("hidden", e.target.value !== "browser");
});
$("cookieSource").dispatchEvent(new Event("change"));

$("uploadBtn").addEventListener("click", async () => {
  const f = $("cookieFile").files[0];
  if (!f) { alert("Pilih file dulu"); return; }
  const fd = new FormData();
  fd.append("cookies", f);
  $("uploadBtn").disabled = true;
  try {
    const r = await fetch("/api/cookies", { method: "POST", body: fd });
    const j = await r.json();
    if (j.ok) {
      $("cookieDot").className = "dot on";
      $("cookieText").textContent = "cookies.txt tersimpan";
    } else {
      alert(j.error || "Gagal");
    }
  } finally {
    $("uploadBtn").disabled = false;
  }
});

function cookiePayload() {
  const src = $("cookieSource").value;
  return {
    cookie_source: src === "none" ? null : src,
    browser: $("browser") ? $("browser").value : null,
  };
}

/* ---------- provider status ---------- */
async function refreshProvider() {
  const el = $("providerStatus");
  if (!el) return;
  try {
    const r = await fetch("/api/provider");
    const j = await r.json();
    const dot = el.querySelector(".dot");
    const txt = el.querySelector("span:last-child");
    if (j.running) {
      dot.className = "dot on";
      txt.textContent = `Server PO Token aktif (port ${j.port})`;
    } else {
      dot.className = "dot warn";
      txt.textContent = `Server PO Token mati — perlu untuk video membership`;
    }
  } catch (e) { /* ignore */ }
}
refreshProvider();
setInterval(refreshProvider, 15000);

/* ---------- test cookie ---------- */
$("testCookieBtn").addEventListener("click", async () => {
  const btn = $("testCookieBtn");
  btn.disabled = true;
  msg($("cookieTestMsg"), '<span class="spinner"></span>Mengecek cookie…', "ok");
  try {
    const r = await fetch("/api/cookies/test");
    const j = await r.json();
    msg($("cookieTestMsg"), j.message, j.ok ? "ok" : "err");
  } catch (e) {
    msg($("cookieTestMsg"), "Gagal cek: " + e, "err");
  } finally {
    btn.disabled = false;
  }
});

/* ---------- subtitle toggle ---------- */
$("subsToggle").addEventListener("change", (e) => {
  $("subLangs").classList.toggle("hidden", !e.target.checked);
});

/* ---------- history ---------- */
function fmtDate(iso) {
  try { return new Date(iso).toLocaleString(); } catch (e) { return iso; }
}
async function loadHistory() {
  try {
    const r = await fetch("/api/history");
    const j = await r.json();
    const items = j.items || [];
    if (!items.length) { $("historyList").textContent = "Belum ada riwayat."; return; }
    $("historyList").innerHTML = items.map(it => `
      <div class="hist-item">
        <span class="h-title" title="${(it.title || '').replace(/"/g, '&quot;')}">${it.title || "(tanpa judul)"}</span>
        <span class="h-meta">${it.type || ""} · ${it.size ? fmtBytes(it.size) : "?"} · ${fmtDate(it.date)}</span>
      </div>`).join("");
  } catch (e) { $("historyList").textContent = "Gagal memuat riwayat."; }
}
$("clearHistoryBtn").addEventListener("click", async () => {
  if (!confirm("Hapus semua riwayat?")) return;
  await fetch("/api/history", { method: "DELETE" });
  loadHistory();
});
loadHistory();

/* ---------- fetch info ---------- */
$("fetchBtn").addEventListener("click", fetchInfo);
$("url").addEventListener("keydown", (e) => { if (e.key === "Enter") fetchInfo(); });

async function fetchInfo() {
  const url = $("url").value.trim();
  if (!url) { msg($("infoMsg"), "Masukkan URL dulu", "err"); return; }
  msg($("infoMsg"), '<span class="spinner"></span>Mengambil info…', "ok");
  $("meta").classList.add("hidden");
  $("fetchBtn").disabled = true;
  try {
    const r = await fetch("/api/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, ...cookiePayload() }),
    });
    const j = await r.json();
    if (!r.ok) { msg($("infoMsg"), j.error || "Gagal", "err"); return; }
    msg($("infoMsg"), "", "");

    isPlaylist = !!j.is_playlist;
    $("playlistOpts").classList.toggle("hidden", !isPlaylist);

    const meta = $("meta");
    meta.classList.remove("hidden");
    meta.classList.remove("reveal"); void meta.offsetWidth; meta.classList.add("reveal");

    if (isPlaylist) {
      const preview = (j.entries || []).slice(0, 8)
        .map((e, i) => `${i + 1}. ${e.title}`).join("<br>");
      const more = j.playlist_count > 8
        ? `<br>… +${j.playlist_count - 8} lagi` : "";
      meta.innerHTML = `
        <div>
          <div class="t">📃 ${j.title || "Playlist"}</div>
          <div class="u">${j.uploader || ""} · ${j.playlist_count} video</div>
          <div class="hint" style="margin-top:10px;">${preview}${more}</div>
        </div>`;
      fillHeights(PRESET_HEIGHTS);
    } else {
      meta.innerHTML = `
        ${j.thumbnail ? `<img src="${j.thumbnail}" alt="">` : ""}
        <div>
          <div class="t">${j.title || "(tanpa judul)"}</div>
          <div class="u">${j.uploader || ""} ${j.duration ? "· " + fmtDur(j.duration) : ""} ${j.is_live ? "· 🔴 LIVE" : ""}</div>
        </div>`;
      fillHeights(j.heights);
    }
  } catch (e) {
    msg($("infoMsg"), "Error: " + e, "err");
  } finally {
    $("fetchBtn").disabled = false;
  }
}

/* ---------- mode toggle ---------- */
$("modeSeg").addEventListener("click", (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  mode = btn.dataset.mode;
  [...$("modeSeg").children].forEach((b) => b.classList.toggle("active", b === btn));
  $("videoOpts").classList.toggle("hidden", mode !== "video");
  $("audioOpts").classList.toggle("hidden", mode !== "audio");
});

/* ---------- download ---------- */
$("downloadBtn").addEventListener("click", async () => {
  const url = $("url").value.trim();
  if (!url) { alert("Masukkan URL dulu"); return; }
  $("downloadBtn").disabled = true;
  $("progressBlock").classList.remove("hidden");
  $("result").innerHTML = "";
  $("progText").innerHTML = '<span class="spinner"></span>Memulai…';
  $("progFill").style.width = "0%";

  const body = {
    url,
    mode,
    height: mode === "video" ? $("height").value : null,
    audio_format: $("audioFormat").value,
    is_playlist: isPlaylist,
    playlist_items: isPlaylist ? $("playlistItems").value.trim() : null,
    subs: mode === "video" && $("subsToggle").checked,
    sub_langs: $("subLangs").value.trim(),
    ...cookiePayload(),
  };
  try {
    const r = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!r.ok) {
      $("progText").textContent = "";
      msg($("result"), j.error, "err");
      $("downloadBtn").disabled = false;
      return;
    }
    poll(j.job_id);
  } catch (e) {
    msg($("result"), "Error: " + e, "err");
    $("downloadBtn").disabled = false;
  }
});

function poll(jobId) {
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const r = await fetch("/api/progress/" + jobId);
      const j = await r.json();
      if (j.status === "downloading") {
        $("progFill").style.width = (j.percent || 0) + "%";
        const sp = j.speed ? fmtBytes(j.speed) + "/s" : "";
        const eta = j.eta ? " · ETA " + j.eta + "s" : "";
        const pl = (j.playlist_index && j.playlist_count)
          ? `Video ${j.playlist_index}/${j.playlist_count} · ` : "";
        $("progText").textContent =
          `${pl}Mengunduh ${j.percent || 0}% (${fmtBytes(j.downloaded_bytes)} / ${fmtBytes(j.total_bytes)}) ${sp}${eta}`;
      } else if (j.status === "processing") {
        $("progFill").style.width = "100%";
        $("progText").innerHTML = '<span class="spinner"></span>' +
          (isPlaylist ? "Mengemas playlist (zip)…" : "Memproses (merge/convert)…");
      } else if (j.status === "done") {
        clearInterval(pollTimer);
        $("progFill").style.width = "100%";
        $("progText").textContent = "Selesai ✓";
        const extra = j.file_count ? ` (${j.file_count} video, .zip)` : "";
        const label = isPlaylist ? "⬇ Simpan playlist (.zip)" : "⬇ Simpan file ke komputer";
        $("result").innerHTML =
          `<div class="msg ok reveal">Berhasil: ${j.title || ""}${extra}<br>
           <a class="dl" href="/api/file/${jobId}">${label}</a>
           <div class="hint" style="margin-top:6px;">Salinan di server otomatis dihapus setelah selesai diunduh (klik sekali).</div></div>`;
        $("downloadBtn").disabled = false;
        loadHistory();
      } else if (j.status === "error") {
        clearInterval(pollTimer);
        $("progText").textContent = "";
        msg($("result"), "Gagal: " + (j.error || ""), "err");
        $("downloadBtn").disabled = false;
      }
    } catch (e) {
      /* keep polling */
    }
  }, 800);
}
