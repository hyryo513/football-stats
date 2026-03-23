/**
 * Soccer Player Tracker — frontend/app.js
 * Vanilla JS, no frameworks. Communicates with FastAPI backend at same origin.
 */

"use strict";

// ── State ──────────────────────────────────────────────────────────────────
const state = {
  currentSessionId: null,
  videoSource: null,       // { type: "file"|"url", path: string }
  playerRef: null,         // { method: "jersey"|"bbox", jersey_number?, bbox? }
  position: null,
  videoMeta: null,         // { duration_s, width, height }
  bbox: null,              // { x, y, w, h } in canvas pixels (scaled to frame)
  bboxDrawing: false,
  bboxStart: null,
  activeTab: "jersey",
  eventSource: null,
  currentReport: null,
  bboxPreviewImage: null,
  bboxPreviewToken: 0,
  bboxVideoLoadedSrc: null,
  bboxCapturedTimestampMs: null,
};

// ── DOM refs ───────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

const els = {
  // Sidebar
  sessionsList:     $("sessions-list"),
  sessionsEmpty:    $("sessions-empty"),
  newSessionBtn:    $("new-session-btn"),
  clearUploadsBtn:  $("clear-uploads-btn"),

  // Alert
  alertBanner:      $("alert-banner"),
  alertMsg:         $("alert-msg"),
  alertClose:       $("alert-close"),

  // Steps
  steps:            [1, 2, 3, 4].map((n) => $(`step-${n}`)),

  // Panels
  panelVideo:       $("panel-video"),
  panelPlayer:      $("panel-player"),
  panelProgress:    $("panel-progress"),
  panelResults:     $("panel-results"),

  // Video panel
  fileInput:        $("file-input"),
  fileName:         $("file-name"),
  urlInput:         $("url-input"),
  loadUrlBtn:       $("load-url-btn"),
  youtubeStatus:    $("youtube-status"),
  youtubeConnectBtn:$("youtube-connect-btn"),
  videoMeta:        $("video-meta"),
  metaDuration:     $("meta-duration"),
  metaResolution:   $("meta-resolution"),
  nextToPlayerBtn:  $("next-to-player-btn"),
  uploadsSelect:    $("uploads-select"),
  loadUploadBtn:    $("load-upload-btn"),
  refreshUploadsBtn:$("refresh-uploads-btn"),

  // Player panel
  tabBtns:          document.querySelectorAll(".tab-btn"),
  tabJersey:        $("tab-jersey"),
  tabBbox:          $("tab-bbox"),
  jerseyInput:      $("jersey-input"),
  jerseyColorInput: $("jersey-color-input"),
  bboxContainer:    $("bbox-container"),
  bboxPlaceholder:  $("bbox-placeholder"),
  bboxVideoWrap:    $("bbox-video-wrap"),
  bboxVideo:        $("bbox-video"),
  bboxUseFrameBtn:  $("bbox-use-frame-btn"),
  bboxVideoStatus:  $("bbox-video-status"),
  bboxCapturedTs:   $("bbox-captured-ts"),
  bboxTimeRange:    $("bbox-time-range"),
  bboxTimeLabel:    $("bbox-time-label"),
  bboxLoadFrameBtn: $("bbox-load-frame-btn"),
  bboxCanvas:       $("bbox-canvas"),
  bboxHint:         $("bbox-hint"),
  bboxClear:        $("bbox-clear"),
  positionSelect:   $("position-select"),
  backToVideoBtn:   $("back-to-video-btn"),
  startAnalysisBtn: $("start-analysis-btn"),

  // Progress panel
  progressBar:      $("progress-bar"),
  progressPct:      $("progress-pct"),
  progressStatus:   $("progress-status"),
  cancelBtn:        $("cancel-btn"),

  // Results panel
  reportMeta:       $("report-meta"),
  coreStatsGrid:    $("core-stats-grid"),
  advancedStatsGrid:$("advanced-stats-grid"),
  advancedTitle:    $("advanced-stats-title"),
  exportJsonBtn:    $("export-json-btn"),
  exportPdfBtn:     $("export-pdf-btn"),
  newAnalysisBtn:   $("new-analysis-btn"),
  reliabilityCard:  $("reliability-card"),
  reliabilityBadge: $("reliability-badge"),
  reliabilityDetails:$("reliability-details"),
  clipsCard:        $("clips-card"),
  clipsContainer:   $("clips-container"),

  // Hidden download anchor
  downloadAnchor:   $("download-anchor"),
};

// ── Utility ────────────────────────────────────────────────────────────────

function showAlert(msg, type = "error") {
  els.alertMsg.textContent = msg;
  els.alertBanner.className = type === "warning" ? "warning visible" : "visible";
}

function hideAlert() {
  els.alertBanner.className = "";
}

function fmtDuration(seconds) {
  if (!seconds && seconds !== 0) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

function fmtDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function capitalize(str) {
  return str ? str.charAt(0).toUpperCase() + str.slice(1) : "";
}

function labelFromKey(key) {
  return key
    .replace(/_pct$/, " %")
    .replace(/_m$/, " (m)")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// ── Panel navigation ───────────────────────────────────────────────────────

function showPanel(name) {
  const panels = { video: 1, player: 2, progress: 3, results: 4 };
  const stepIdx = panels[name] || 1;

  els.panelVideo.style.display    = name === "video"    ? "" : "none";
  els.panelPlayer.style.display   = name === "player"   ? "" : "none";
  els.panelProgress.style.display = name === "progress" ? "" : "none";
  els.panelResults.style.display  = name === "results"  ? "" : "none";

  els.steps.forEach((el, i) => {
    el.className = i + 1 < stepIdx ? "step done" : i + 1 === stepIdx ? "step active" : "step";
  });
}

// ── Session history sidebar ────────────────────────────────────────────────

async function loadSessionHistory() {
  try {
    const res = await fetch("/sessions");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const sessions = await res.json();
    renderSessionList(sessions);
  } catch (err) {
    console.error("Failed to load sessions:", err);
  }
}

function renderSessionList(sessions) {
  if (!sessions || sessions.length === 0) {
    els.sessionsEmpty.style.display = "";
    // Remove any existing cards
    document.querySelectorAll(".session-card").forEach((el) => el.remove());
    return;
  }
  els.sessionsEmpty.style.display = "none";

  // Clear existing cards
  document.querySelectorAll(".session-card").forEach((el) => el.remove());

  sessions.forEach((s) => {
    const card = document.createElement("div");
    card.className = "session-card";
    card.dataset.sessionId = s.session_id;

    const src = s.video_source || "Unknown source";
    const shortSrc = src.length > 30 ? "…" + src.slice(-28) : src;
    const pos = capitalize(s.position || "");
    const date = fmtDate(s.created_at);

    card.innerHTML = `
      <div class="session-card-title" title="${src}">${shortSrc}</div>
      <div class="session-card-meta">
        <span>${pos}</span>
        <span>${date}</span>
      </div>
      <div class="session-card-actions">
        <button class="btn-sm load-btn" data-id="${s.session_id}">Load</button>
        <button class="btn-sm danger delete-btn" data-id="${s.session_id}">Delete</button>
      </div>
    `;

    card.querySelector(".load-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      loadSession(s.session_id);
    });
    card.querySelector(".delete-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      deleteSession(s.session_id);
    });

    els.sessionsList.appendChild(card);
  });
}

async function loadSession(sessionId) {
  try {
    const res = await fetch(`/sessions/${sessionId}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const report = await res.json();
    state.currentSessionId = sessionId;
    state.currentReport = report;
    renderReport(report);
    showPanel("results");
    // Mark active
    document.querySelectorAll(".session-card").forEach((el) => {
      el.classList.toggle("active", el.dataset.sessionId === sessionId);
    });
  } catch (err) {
    showAlert(`Failed to load session: ${err.message}`);
  }
}

async function deleteSession(sessionId) {
  if (!confirm("Delete this session? This cannot be undone.")) return;
  try {
    const res = await fetch(`/sessions/${sessionId}`, { method: "DELETE" });
    if (!res.ok && res.status !== 204) throw new Error(`HTTP ${res.status}`);
    // If we're viewing this session, go back to video panel
    if (state.currentSessionId === sessionId) {
      resetWorkflow();
    }
    await loadSessionHistory();
  } catch (err) {
    showAlert(`Failed to delete session: ${err.message}`);
  }
}

async function clearUploads() {
  if (!confirm("Delete all uploaded video files? This cannot be undone.")) return;
  try {
    const res = await fetch("/uploads", { method: "DELETE" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      showAlert(data.detail || `Failed to clear uploads (HTTP ${res.status})`);
      return;
    }
    const count = data.deleted ?? 0;
    if (count === 0) {
      showAlert("No files to delete.", "warning");
    } else {
      showAlert(`Cleared ${count} file(s) from uploads.`, "warning");
    }
    await loadUploadedVideos();
  } catch (err) {
    showAlert(`Failed to clear uploads: ${err.message}`);
  }
}

async function loadUploadedVideos() {
  if (!els.uploadsSelect) return;
  try {
    const res = await fetch("/uploads");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const uploads = await res.json();
    els.uploadsSelect.innerHTML = `<option value="">— Select uploaded video —</option>`;
    uploads.forEach((u) => {
      const opt = document.createElement("option");
      opt.value = u.path;
      opt.textContent = u.name;
      els.uploadsSelect.appendChild(opt);
    });
  } catch (err) {
    console.warn("Failed to load uploads list:", err);
  }
}

async function loadSelectedUpload() {
  const path = els.uploadsSelect?.value?.trim();
  if (!path) {
    showAlert("Please select an uploaded video first.");
    return;
  }
  hideAlert();
  state.videoSource = { type: "file", path };
  state.videoMeta = null;
  state.bboxPreviewImage = null;
  state.bboxVideoLoadedSrc = null;
  state.bboxCapturedTimestampMs = null;
  els.fileName.textContent = `Loaded: ${path.split("/").pop()}`;
  await fetchVideoMeta(path);
}

// ── Video input ────────────────────────────────────────────────────────────

els.fileInput.addEventListener("change", async () => {
  const file = els.fileInput.files[0];
  if (!file) return;

  const ext = file.name.split(".").pop().toLowerCase();
  const allowed = ["mp4", "mov", "avi", "mkv"];
  if (!allowed.includes(ext)) {
    showAlert(`Unsupported format ".${ext}". Accepted formats: ${allowed.join(", ")}.`);
    els.fileInput.value = "";
    return;
  }

  els.fileName.textContent = file.name;
  hideAlert();
  els.nextToPlayerBtn.disabled = true;
  els.videoMeta.className = "";

  // Show uploading state
  els.fileName.textContent = `${file.name} — uploading…`;

  try {
    const formData = new FormData();
    formData.append("file", file);

    const res = await fetch("/upload", { method: "POST", body: formData });
    const data = await res.json();

    if (!res.ok) {
      showAlert(data.detail || `Upload failed (HTTP ${res.status})`);
      els.fileName.textContent = "No file selected";
      return;
    }

    // Backend returns local_path + metadata fields
    state.videoSource = { type: "file", path: data.local_path };
    state.videoMeta = { duration_s: data.duration_s, width: data.width, height: data.height };

    els.fileName.textContent = file.name;
    els.metaDuration.textContent = fmtDuration(data.duration_s);
    els.metaResolution.textContent = `${data.width}×${data.height}`;
    els.videoMeta.className = "visible";
    els.nextToPlayerBtn.disabled = false;
    hideAlert();
  } catch (err) {
    showAlert(`Upload failed: ${err.message}`);
    els.fileName.textContent = "No file selected";
  }
});

els.loadUrlBtn.addEventListener("click", async () => {
  const url = els.urlInput.value.trim();
  if (!url) { showAlert("Please enter a URL."); return; }
  hideAlert();
  state.videoSource = { type: "url", path: url };
  state.videoMeta = null;
  await fetchVideoMeta(url);
});

els.urlInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") els.loadUrlBtn.click();
});

async function fetchVideoMeta(source) {
  els.loadUrlBtn.disabled = true;
  els.nextToPlayerBtn.disabled = true;
  els.videoMeta.className = "";

  try {
    const res = await fetch(`/video/metadata?source=${encodeURIComponent(source)}`);
    const data = await res.json();

    if (!res.ok) {
      showAlert(data.detail || `Failed to load video (HTTP ${res.status})`);
      return;
    }

    state.videoMeta = data;
    els.metaDuration.textContent = fmtDuration(data.duration_s);
    els.metaResolution.textContent = `${data.width}×${data.height}`;
    els.videoMeta.className = "visible";
    els.nextToPlayerBtn.disabled = false;
    hideAlert();
  } catch (err) {
    showAlert(`Could not reach server: ${err.message}`);
  } finally {
    els.loadUrlBtn.disabled = false;
  }
}

els.nextToPlayerBtn.addEventListener("click", () => {
  showPanel("player");
  // If bbox tab is active and we have meta, draw placeholder frame
  if (state.activeTab === "bbox") initBboxCanvas();
  updateStartBtn();
});

// ── Player identification tabs ─────────────────────────────────────────────

els.tabBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    els.tabBtns.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    state.activeTab = btn.dataset.tab;

    els.tabJersey.classList.toggle("active", state.activeTab === "jersey");
    els.tabBbox.classList.toggle("active", state.activeTab === "bbox");

    if (state.activeTab === "bbox") initBboxCanvas();
    updateStartBtn();
  });
});

els.jerseyInput.addEventListener("input", updateStartBtn);
els.positionSelect.addEventListener("change", updateStartBtn);

function updateStartBtn() {
  const hasPosition = !!els.positionSelect.value;
  let hasPlayer = false;

  if (state.activeTab === "jersey") {
    const n = parseInt(els.jerseyInput.value, 10);
    hasPlayer = !isNaN(n) && n >= 1 && n <= 99;
  } else {
    hasPlayer = !!state.bbox;
  }

  els.startAnalysisBtn.disabled = !(hasPosition && hasPlayer);
}

// ── BBox canvas ────────────────────────────────────────────────────────────

function drawBboxBackground(ctx, width, height) {
  if (state.bboxPreviewImage) {
    ctx.drawImage(state.bboxPreviewImage, 0, 0, width, height);
    return;
  }
  ctx.fillStyle = "#1a1a2e";
  ctx.fillRect(0, 0, width, height);
  ctx.fillStyle = "#30363d";
  ctx.font = "14px sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("Pause video and click 'Use Current Frame'", width / 2, height / 2);
}

function fmtSeconds(seconds) {
  const s = Math.max(0, Number(seconds) || 0);
  const m = Math.floor(s / 60);
  const rem = (s % 60).toFixed(2).padStart(5, "0");
  return `${m}:${rem}`;
}

function updateBboxTimeLabelFromRange() {
  if (!els.bboxTimeRange || !els.bboxTimeLabel) return;
  const ms = Math.max(0, parseInt(els.bboxTimeRange.value || "0", 10) || 0);
  els.bboxTimeLabel.textContent = fmtSeconds(ms / 1000);
}

async function captureFrameByTimestampForBbox() {
  if (!state.videoSource?.path) {
    showAlert("Load a video first.");
    return;
  }
  const tsMs = Math.max(0, parseInt(els.bboxTimeRange?.value || "0", 10) || 0);
  try {
    const res = await fetch(`/video/frame?source=${encodeURIComponent(state.videoSource.path)}&timestamp_ms=${tsMs}`);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `HTTP ${res.status}`);
    }
    const blob = await res.blob();
    const img = new Image();
    await new Promise((resolve, reject) => {
      img.onload = () => resolve();
      img.onerror = () => reject(new Error("Failed to decode frame image"));
      img.src = URL.createObjectURL(blob);
    });

    state.videoMeta = {
      ...(state.videoMeta || {}),
      width: img.naturalWidth,
      height: img.naturalHeight,
    };
    state.bboxCapturedTimestampMs = tsMs;

    const maxW = 560;
    const scale = Math.min(1, maxW / img.naturalWidth);
    const dispW = Math.max(320, Math.round(img.naturalWidth * scale));
    const dispH = Math.max(180, Math.round(img.naturalHeight * scale));
    const snapshot = document.createElement("canvas");
    snapshot.width = dispW;
    snapshot.height = dispH;
    const snapCtx = snapshot.getContext("2d");
    snapCtx.drawImage(img, 0, 0, dispW, dispH);
    state.bboxPreviewImage = snapshot;

    els.bboxCanvas.width = dispW;
    els.bboxCanvas.height = dispH;
    els.bboxCanvas.style.display = "block";
    els.bboxPlaceholder.style.display = "none";
    const ctx = els.bboxCanvas.getContext("2d");
    drawBboxBackground(ctx, dispW, dispH);
    if (state.bbox) drawBboxOnCanvas(ctx, state.bbox, dispW, dispH, scale);

    const captureLabel = fmtSeconds(tsMs / 1000);
    els.bboxVideoStatus.textContent = `Loaded frame at ${captureLabel}. Draw a box on the frame below.`;
    if (els.bboxCapturedTs) {
      els.bboxCapturedTs.textContent = `Frame: ${captureLabel}`;
      els.bboxCapturedTs.style.display = "";
    }
  } catch (err) {
    showAlert(`Failed to load frame: ${err.message}`);
  }
}

function getVideoPreviewSrc() {
  const srcPath = state.videoSource?.path;
  if (!srcPath) return null;
  // Prefer path-based endpoint for uploaded files (Safari-friendly).
  const marker = "/.soccer-tracker/uploads/";
  const idx = srcPath.indexOf(marker);
  if (idx >= 0) {
    const fileName = srcPath.slice(idx + marker.length);
    if (fileName && !fileName.includes("/")) {
      return `/uploads/stream/${encodeURIComponent(fileName)}`;
    }
  }
  return `/video/stream?source=${encodeURIComponent(srcPath)}`;
}

async function prepareBboxVideo() {
  if (!els.bboxVideo || !els.bboxVideoWrap) {
    return false;
  }

  els.bboxVideoWrap.style.display = "block";
  if (!state.videoSource?.path) {
    els.bboxVideoStatus.textContent = "Load a video first, then return to Visual Selection.";
    return false;
  }
  const src = getVideoPreviewSrc();
  if (!src) {
    els.bboxVideoStatus.textContent = "Load a video first, then return to Visual Selection.";
    return false;
  }
  if (state.bboxVideoLoadedSrc === src && els.bboxVideo.readyState >= 1) {
    return true;
  }

  // Safari-friendly inline playback flags for embedded <video>.
  els.bboxVideo.playsInline = true;
  els.bboxVideo.setAttribute("playsinline", "");
  els.bboxVideo.preload = "metadata";

  els.bboxVideoStatus.textContent = "Loading video preview…";
  state.bboxVideoLoadedSrc = src;

  try {
    await new Promise((resolve, reject) => {
      let settled = false;
      const finish = (ok, error) => {
        if (settled) return;
        settled = true;
        els.bboxVideo.removeEventListener("loadedmetadata", onLoaded);
        els.bboxVideo.removeEventListener("loadeddata", onLoaded);
        els.bboxVideo.removeEventListener("canplay", onLoaded);
        els.bboxVideo.removeEventListener("error", onError);
        clearTimeout(timer);
        if (ok) resolve(null);
        else reject(error || new Error("Failed to load video preview"));
      };
      const onLoaded = () => {
        finish(true);
      };
      const onError = () => {
        finish(false, new Error("Failed to load video preview"));
      };
      const timer = setTimeout(() => {
        // Fallback: Safari can miss early events; proceed if metadata is present.
        if (els.bboxVideo.readyState >= 1 && els.bboxVideo.videoWidth > 0) {
          finish(true);
        } else {
          finish(false, new Error("Timed out loading video preview"));
        }
      }, 7000);

      // Attach listeners before setting src to avoid event races.
      els.bboxVideo.addEventListener("loadedmetadata", onLoaded);
      els.bboxVideo.addEventListener("loadeddata", onLoaded);
      els.bboxVideo.addEventListener("canplay", onLoaded);
      els.bboxVideo.addEventListener("error", onError);

      if (els.bboxVideo.src !== src) {
        els.bboxVideo.src = src;
      }
      els.bboxVideo.load();

      // If already loaded from cache, resolve immediately.
      if (els.bboxVideo.readyState >= 1 && els.bboxVideo.videoWidth > 0) {
        finish(true);
      }
    });
    if (!state.videoMeta || !state.videoMeta.width || !state.videoMeta.height) {
      const vw = els.bboxVideo.videoWidth;
      const vh = els.bboxVideo.videoHeight;
      if (vw && vh) {
        state.videoMeta = {
          ...(state.videoMeta || {}),
          width: vw,
          height: vh,
          duration_s: state.videoMeta?.duration_s ?? els.bboxVideo.duration,
        };
      }
    }
    els.bboxVideoStatus.textContent = "Pause on the frame you want, then click 'Use Current Frame'.";
    return true;
  } catch (err) {
    els.bboxVideoStatus.textContent = "Video preview unavailable. Restart app server and retry this source.";
    console.warn("Failed to load bbox video preview:", err);
    return false;
  }
}

async function initBboxCanvas() {
  const canvas = els.bboxCanvas;
  const placeholder = els.bboxPlaceholder;
  if (els.bboxTimeRange) {
    const durationS = Number(state.videoMeta?.duration_s || 0);
    els.bboxTimeRange.max = durationS > 0 ? String(Math.round(durationS * 1000)) : "1000";
    if (Number(els.bboxTimeRange.value) > Number(els.bboxTimeRange.max)) {
      els.bboxTimeRange.value = els.bboxTimeRange.max;
    }
    updateBboxTimeLabelFromRange();
  }
  await prepareBboxVideo();

  if (!state.videoMeta || !state.videoMeta.width || !state.videoMeta.height) {
    placeholder.style.display = "flex";
    canvas.style.display = "none";
    if (!state.videoMeta) {
      placeholder.textContent = "Load a video to enable frame selection";
    } else {
      placeholder.textContent = "Video metadata unavailable. Re-upload video and try again.";
    }
    return;
  }

  const width = Math.max(1, Number(state.videoMeta.width));
  const height = Math.max(1, Number(state.videoMeta.height));
  const maxW = 560;
  const scale = Math.min(1, maxW / width);
  const dispW = Math.max(320, Math.round(width * scale));
  const dispH = Math.max(180, Math.round(height * scale));

  canvas.width = dispW;
  canvas.height = dispH;
  canvas.style.display = "block";
  placeholder.style.display = "none";

  const ctx = canvas.getContext("2d");
  drawBboxBackground(ctx, dispW, dispH);

  // Redraw existing bbox if any
  if (state.bbox) drawBboxOnCanvas(ctx, state.bbox, dispW, dispH, scale);
}

function captureCurrentVideoFrameForBbox() {
  if (!els.bboxVideo || els.bboxVideo.readyState < 2) {
    showAlert("Video preview not ready yet. Wait a moment and try again.");
    return;
  }
  const vw = els.bboxVideo.videoWidth;
  const vh = els.bboxVideo.videoHeight;
  if (!vw || !vh) {
    showAlert("Could not read frame from preview video.");
    return;
  }

  state.videoMeta = {
    ...(state.videoMeta || {}),
    width: vw,
    height: vh,
  };
  state.bboxCapturedTimestampMs = Math.max(0, Math.round(els.bboxVideo.currentTime * 1000));

  const maxW = 560;
  const scale = Math.min(1, maxW / vw);
  const dispW = Math.max(320, Math.round(vw * scale));
  const dispH = Math.max(180, Math.round(vh * scale));

  const snapshot = document.createElement("canvas");
  snapshot.width = dispW;
  snapshot.height = dispH;
  const snapCtx = snapshot.getContext("2d");
  snapCtx.drawImage(els.bboxVideo, 0, 0, dispW, dispH);
  state.bboxPreviewImage = snapshot;

  els.bboxCanvas.width = dispW;
  els.bboxCanvas.height = dispH;
  els.bboxCanvas.style.display = "block";
  els.bboxPlaceholder.style.display = "none";

  const ctx = els.bboxCanvas.getContext("2d");
  drawBboxBackground(ctx, dispW, dispH);
  if (state.bbox) drawBboxOnCanvas(ctx, state.bbox, dispW, dispH, scale);
  const captureLabel = fmtSeconds(els.bboxVideo.currentTime);
  els.bboxVideoStatus.textContent = `Captured frame at ${captureLabel}. Draw a box on the frame below.`;
  if (els.bboxCapturedTs) {
    els.bboxCapturedTs.textContent = `Frame: ${captureLabel}`;
    els.bboxCapturedTs.style.display = "";
  }
}

function drawBboxOnCanvas(ctx, bbox, dispW, dispH, scale) {
  ctx.strokeStyle = "#4a9eff";
  ctx.lineWidth = 2;
  ctx.strokeRect(bbox.x * scale, bbox.y * scale, bbox.w * scale, bbox.h * scale);
  ctx.fillStyle = "rgba(74,158,255,0.15)";
  ctx.fillRect(bbox.x * scale, bbox.y * scale, bbox.w * scale, bbox.h * scale);
}

// Canvas mouse events
els.bboxCanvas.addEventListener("mousedown", (e) => {
  const rect = els.bboxCanvas.getBoundingClientRect();
  state.bboxStart = { x: e.clientX - rect.left, y: e.clientY - rect.top };
  state.bboxDrawing = true;
  state.bbox = null;
  els.bboxClear.style.display = "none";
});

els.bboxCanvas.addEventListener("mousemove", (e) => {
  if (!state.bboxDrawing) return;
  const rect = els.bboxCanvas.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const y = e.clientY - rect.top;
  const ctx = els.bboxCanvas.getContext("2d");

  // Redraw background
  drawBboxBackground(ctx, els.bboxCanvas.width, els.bboxCanvas.height);

  // Draw current rect
  const rx = Math.min(state.bboxStart.x, x);
  const ry = Math.min(state.bboxStart.y, y);
  const rw = Math.abs(x - state.bboxStart.x);
  const rh = Math.abs(y - state.bboxStart.y);
  ctx.strokeStyle = "#4a9eff";
  ctx.lineWidth = 2;
  ctx.strokeRect(rx, ry, rw, rh);
  ctx.fillStyle = "rgba(74,158,255,0.15)";
  ctx.fillRect(rx, ry, rw, rh);
});

els.bboxCanvas.addEventListener("mouseup", (e) => {
  if (!state.bboxDrawing) return;
  state.bboxDrawing = false;

  const rect = els.bboxCanvas.getBoundingClientRect();
  const x2 = e.clientX - rect.left;
  const y2 = e.clientY - rect.top;

  const rx = Math.min(state.bboxStart.x, x2);
  const ry = Math.min(state.bboxStart.y, y2);
  const rw = Math.abs(x2 - state.bboxStart.x);
  const rh = Math.abs(y2 - state.bboxStart.y);

  if (rw < 5 || rh < 5) {
    state.bbox = null;
    updateStartBtn();
    return;
  }

  // Scale back to frame coordinates
  const scale = state.videoMeta
    ? Math.min(1, 560 / state.videoMeta.width)
    : 1;

  state.bbox = {
    x: Math.round(rx / scale),
    y: Math.round(ry / scale),
    w: Math.round(rw / scale),
    h: Math.round(rh / scale),
  };

  els.bboxClear.style.display = "";
  updateStartBtn();
});

els.bboxClear.addEventListener("click", () => {
  state.bbox = null;
  els.bboxClear.style.display = "none";
  state.bboxCapturedTimestampMs = null;
  if (els.bboxCapturedTs) {
    els.bboxCapturedTs.style.display = "none";
    els.bboxCapturedTs.textContent = "Frame: —";
  }
  initBboxCanvas();
  updateStartBtn();
});
if (els.bboxUseFrameBtn) {
  els.bboxUseFrameBtn.addEventListener("click", captureCurrentVideoFrameForBbox);
}
if (els.bboxTimeRange) els.bboxTimeRange.addEventListener("input", updateBboxTimeLabelFromRange);
if (els.bboxLoadFrameBtn) els.bboxLoadFrameBtn.addEventListener("click", captureFrameByTimestampForBbox);
if (els.loadUploadBtn) els.loadUploadBtn.addEventListener("click", loadSelectedUpload);
if (els.refreshUploadsBtn) els.refreshUploadsBtn.addEventListener("click", loadUploadedVideos);

// ── Navigation buttons ─────────────────────────────────────────────────────

els.backToVideoBtn.addEventListener("click", () => showPanel("video"));

els.newSessionBtn.addEventListener("click", resetWorkflow);
els.newAnalysisBtn.addEventListener("click", resetWorkflow);
if (els.clearUploadsBtn) els.clearUploadsBtn.addEventListener("click", clearUploads);

function resetWorkflow() {
  state.currentSessionId = null;
  state.videoSource = null;
  state.playerRef = null;
  state.position = null;
  state.videoMeta = null;
  state.bbox = null;
  state.currentReport = null;
  state.bboxPreviewImage = null;
  state.bboxPreviewToken = 0;
  state.bboxVideoLoadedSrc = null;
  state.bboxCapturedTimestampMs = null;

  if (state.eventSource) {
    state.eventSource.close();
    state.eventSource = null;
  }

  // Reset form fields
  els.fileInput.value = "";
  els.fileName.textContent = "No file selected";
  els.urlInput.value = "";
  els.videoMeta.className = "";
  els.jerseyInput.value = "";
  if (els.jerseyColorInput) els.jerseyColorInput.value = "";
  els.positionSelect.value = "";
  els.nextToPlayerBtn.disabled = true;
  els.startAnalysisBtn.disabled = true;
  els.bboxClear.style.display = "none";
  if (els.bboxVideo) {
    els.bboxVideo.pause();
    els.bboxVideo.removeAttribute("src");
    els.bboxVideo.load();
  }
  if (els.bboxVideoWrap) els.bboxVideoWrap.style.display = "none";
  if (els.bboxCapturedTs) {
    els.bboxCapturedTs.style.display = "none";
    els.bboxCapturedTs.textContent = "Frame: —";
  }

  // Reset progress
  els.progressBar.style.width = "0%";
  els.progressPct.textContent = "0%";
  els.progressStatus.textContent = "Starting…";

  document.querySelectorAll(".session-card").forEach((el) => el.classList.remove("active"));

  hideAlert();
  showPanel("video");
}

// ── Start analysis ─────────────────────────────────────────────────────────

els.startAnalysisBtn.addEventListener("click", startAnalysis);

async function startAnalysis() {
  hideAlert();

  // Build playerRef
  if (state.activeTab === "jersey") {
    const n = parseInt(els.jerseyInput.value, 10);
    const color = els.jerseyColorInput?.value?.trim();
    state.playerRef = {
      method: "jersey",
      jersey_number: n,
      ...(color && { jersey_color: color }),
    };
  } else {
    if (!state.bbox) { showAlert("Please draw a bounding box on the frame."); return; }
    state.playerRef = {
      method: "bbox",
      bbox: [state.bbox.x, state.bbox.y, state.bbox.w, state.bbox.h],
      ...(state.bboxCapturedTimestampMs !== null && { bbox_timestamp_ms: state.bboxCapturedTimestampMs }),
    };
  }

  state.position = els.positionSelect.value;

  const body = {
    video_source: state.videoSource,
    player_ref: state.playerRef,
    position: state.position,
  };

  try {
    const res = await fetch("/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();

    if (!res.ok) {
      showAlert(data.detail || `Failed to start analysis (HTTP ${res.status})`);
      return;
    }

    state.currentSessionId = data.session_id;
    showPanel("progress");
    connectProgressSSE(data.session_id);
  } catch (err) {
    showAlert(`Could not reach server: ${err.message}`);
  }
}

// ── SSE progress ───────────────────────────────────────────────────────────

function connectProgressSSE(sessionId) {
  if (state.eventSource) state.eventSource.close();

  const es = new EventSource(`/sessions/${sessionId}/progress`);
  state.eventSource = es;

  es.onmessage = (event) => {
    let data;
    try { data = JSON.parse(event.data); } catch { return; }

    const pct = data.progress || 0;
    els.progressBar.style.width = `${pct}%`;
    els.progressPct.textContent = `${pct}%`;

    const statusMap = {
      pending:   "Waiting to start…",
      running:   pct < 50 ? "Downloading video…" : "Analyzing frames…",
      completed: "Complete",
      cancelled: "Cancelled",
      failed:    "Failed",
    };
    els.progressStatus.textContent = statusMap[data.status] || data.status;

    if (data.status === "completed") {
      es.close();
      state.eventSource = null;
      loadSessionHistory();
      fetchAndShowReport(sessionId);
    } else if (data.status === "cancelled") {
      es.close();
      state.eventSource = null;
      showAlert("Analysis was cancelled.", "warning");
      showPanel("video");
    } else if (data.status === "failed") {
      es.close();
      state.eventSource = null;
      showAlert(data.error || "Analysis failed. Check server logs for details.");
      showPanel("player");
    }
  };

  es.onerror = () => {
    es.close();
    state.eventSource = null;
  };
}

async function fetchAndShowReport(sessionId) {
  try {
    const res = await fetch(`/sessions/${sessionId}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const report = await res.json();
    state.currentReport = report;
    renderReport(report);
    showPanel("results");
  } catch (err) {
    showAlert(`Analysis complete but failed to load report: ${err.message}`);
  }
}

// ── Cancel ─────────────────────────────────────────────────────────────────

els.cancelBtn.addEventListener("click", async () => {
  if (!state.currentSessionId) return;
  els.cancelBtn.disabled = true;
  try {
    await fetch(`/sessions/${state.currentSessionId}/cancel`, { method: "POST" });
  } catch (err) {
    console.error("Cancel request failed:", err);
  } finally {
    els.cancelBtn.disabled = false;
  }
});

// ── Render report ──────────────────────────────────────────────────────────

function renderReport(report) {
  // Meta
  const playerDesc = report.player_ref?.method === "jersey"
    ? `Jersey #${report.player_ref.jersey_number}`
    : `Visual selection${report.player_ref?.bbox_timestamp_ms != null ? ` @ ${fmtSeconds(report.player_ref.bbox_timestamp_ms / 1000)}` : ""}`;
  const dur = report.analysis_duration_s
    ? `${report.analysis_duration_s.toFixed(1)}s`
    : "—";

  els.reportMeta.innerHTML = `
    <strong>Video:</strong> ${report.video_source || "—"}<br>
    <strong>Player:</strong> ${playerDesc} &nbsp;|&nbsp;
    <strong>Position:</strong> ${capitalize(report.position || "")} &nbsp;|&nbsp;
    <strong>Analyzed:</strong> ${fmtDate(report.created_at)} &nbsp;|&nbsp;
    <strong>Duration:</strong> ${dur}
  `;

  // Core stats
  const core = report.core || {};
  const coreFields = [
    { key: "touch_count",          label: "Touches" },
    { key: "passes_attempted",     label: "Passes Attempted" },
    { key: "passes_successful",    label: "Passes Successful" },
    { key: "pass_completion_pct",  label: "Pass Completion %" },
    { key: "ball_losses",          label: "Ball Losses" },
    { key: "ball_retention_rate",  label: "Ball Retention %" },
  ];
  els.coreStatsGrid.innerHTML = coreFields.map(({ key, label }) => {
    const val = core[key];
    const display = val === null || val === undefined ? "N/A" : val;
    const cls = display === "N/A" ? "stat-value na" : "stat-value";
    return `<div class="stat-item"><div class="stat-label">${label}</div><div class="${cls}">${display}</div></div>`;
  }).join("");

  // Advanced stats
  const adv = report.advanced || {};
  const posLabel = capitalize(report.position || "");
  els.advancedTitle.textContent = `${posLabel} — Advanced Statistics`;

  const advKeys = Object.keys(adv).filter((k) => !k.startsWith("_"));
  if (advKeys.length === 0) {
    els.advancedStatsGrid.innerHTML = `<p style="color:var(--text-muted);font-size:13px;">No advanced stats available.</p>`;
  } else {
    els.advancedStatsGrid.innerHTML = advKeys.map((key) => {
      const val = adv[key];
      const display = val === null || val === undefined ? "N/A" : val;
      const cls = display === "N/A" ? "stat-value na" : "stat-value";
      return `<div class="stat-item"><div class="stat-label">${labelFromKey(key)}</div><div class="${cls}">${display}</div></div>`;
    }).join("");
  }

  renderReliability(report);
  renderClips(report);
}

function renderReliability(report) {
  const ts = report.tracking_summary;
  if (!ts || !els.reliabilityCard) {
    if (els.reliabilityCard) els.reliabilityCard.style.display = "none";
    return;
  }

  const pct = Number(ts.confident_frame_pct ?? 0);
  const reacq = Number(ts.total_reacquires ?? 0);
  const total = Number(ts.frames_total ?? 0);
  const uniqueIds = Array.isArray(ts.unique_track_ids_used) ? ts.unique_track_ids_used.length : 0;

  // Scoring: confident_frame_pct is dominant, penalize heavy reacquisition
  const reacqRate = total > 0 ? reacq / total : 0;
  let level, label, color, bg;
  if (pct >= 75 && reacqRate < 0.15) {
    level = "good"; label = "Good"; color = "var(--success)"; bg = "rgba(63,185,80,0.12)";
  } else if (pct >= 50 || reacqRate < 0.30) {
    level = "fair"; label = "Fair"; color = "var(--warning)"; bg = "rgba(210,153,34,0.12)";
  } else {
    level = "poor"; label = "Poor"; color = "var(--danger)"; bg = "rgba(248,81,73,0.12)";
  }

  const dot = `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${color};"></span>`;
  els.reliabilityBadge.innerHTML = `${dot} ${label}`;
  els.reliabilityBadge.style.background = bg;
  els.reliabilityBadge.style.color = color;
  els.reliabilityBadge.style.border = `1px solid ${color}`;

  const detailParts = [
    `<strong>Confident frames:</strong> ${pct.toFixed(1)}%`,
    `<strong>Reacquires:</strong> ${reacq.toLocaleString()}`,
    `<strong>Unique track IDs:</strong> ${uniqueIds}`,
    `<strong>Total frames:</strong> ${total.toLocaleString()}`,
  ];

  const diag = report.analyzer_diagnostics;
  if (diag) {
    if (diag.ball_detection_pct != null) detailParts.push(`<strong>Ball detected:</strong> ${Number(diag.ball_detection_pct).toFixed(1)}%`);
    if (diag.player_detection_pct != null) detailParts.push(`<strong>Player detected:</strong> ${Number(diag.player_detection_pct).toFixed(1)}%`);
    if (diag.both_detection_pct != null) detailParts.push(`<strong>Both detected:</strong> ${Number(diag.both_detection_pct).toFixed(1)}%`);
  }

  els.reliabilityDetails.innerHTML = detailParts.join(" &nbsp;|&nbsp; ");

  els.reliabilityCard.style.display = "";
}

function renderClips(report) {
  const clips = report.debug_clips;
  if (!clips || !els.clipsCard || !els.clipsContainer) {
    if (els.clipsCard) els.clipsCard.style.display = "none";
    return;
  }

  const sessionId = report.session_id || state.currentSessionId;
  const categories = Object.entries(clips).filter(([, paths]) => Array.isArray(paths) && paths.length > 0);
  if (categories.length === 0) {
    els.clipsCard.style.display = "none";
    return;
  }

  let html = "";
  for (const [category, paths] of categories) {
    const catLabel = labelFromKey(category);
    html += `<div style="margin-bottom:14px;">`;
    html += `<div style="font-weight:600; font-size:12px; color:var(--text-secondary); text-transform:uppercase; letter-spacing:0.04em; margin-bottom:6px;">${catLabel} (${paths.length})</div>`;
    html += `<div style="display:flex; flex-wrap:wrap; gap:6px;">`;
    for (const fullPath of paths) {
      const fileName = fullPath.split("/").pop();
      const downloadUrl = `/sessions/${sessionId}/clips/${encodeURIComponent(fileName)}`;
      const shortName = fileName.replace(/\.mp4$/i, "").replace(/_/g, " ");
      html += `<a href="${downloadUrl}" download="${fileName}" style="display:inline-flex;align-items:center;gap:4px;padding:4px 10px;background:var(--bg-input);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--accent);font-size:11px;text-decoration:none;transition:border-color 0.12s;" onmouseover="this.style.borderColor='var(--accent)'" onmouseout="this.style.borderColor='var(--border)'">${shortName}</a>`;
    }
    html += `</div></div>`;
  }

  els.clipsContainer.innerHTML = html;
  els.clipsCard.style.display = "";
}

// ── Export ─────────────────────────────────────────────────────────────────

els.exportJsonBtn.addEventListener("click", () => exportReport("json"));
els.exportPdfBtn.addEventListener("click", () => exportReport("pdf"));

async function exportReport(format) {
  if (!state.currentSessionId) return;
  const btn = format === "json" ? els.exportJsonBtn : els.exportPdfBtn;
  btn.disabled = true;

  try {
    const res = await fetch(`/sessions/${state.currentSessionId}/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ format }),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      showAlert(data.detail || `Export failed (HTTP ${res.status})`);
      return;
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const ext = format === "json" ? "json" : "pdf";
    const filename = `session_${state.currentSessionId}.${ext}`;

    els.downloadAnchor.href = url;
    els.downloadAnchor.download = filename;
    els.downloadAnchor.click();

    // Clean up blob URL after a short delay
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  } catch (err) {
    showAlert(`Export failed: ${err.message}`);
  } finally {
    btn.disabled = false;
  }
}

// ── Alert close ────────────────────────────────────────────────────────────

els.alertClose.addEventListener("click", hideAlert);

// ── YouTube auth ────────────────────────────────────────────────────────────

async function updateYouTubeStatus() {
  if (!els.youtubeStatus || !els.youtubeConnectBtn) return;
  try {
    const res = await fetch("/auth/youtube/status");
    const data = await res.json();
    const connected = data.connected === true;
    els.youtubeStatus.textContent = connected ? "YouTube: Connected" : "YouTube: Not connected";
    els.youtubeConnectBtn.textContent = connected ? "Disconnect" : "Connect YouTube";
    els.youtubeConnectBtn.dataset.connected = connected ? "1" : "0";
  } catch (err) {
    console.error("Failed to fetch YouTube status:", err);
  }
}

if (els.youtubeConnectBtn) {
  els.youtubeConnectBtn.addEventListener("click", async () => {
    if (els.youtubeConnectBtn.dataset.connected === "1") {
      try {
        await fetch("/auth/youtube", { method: "DELETE" });
        await updateYouTubeStatus();
      } catch (err) {
        showAlert(`Failed to disconnect: ${err.message}`);
      }
    } else {
      window.location.href = "/auth/youtube";
    }
  });
}

// ── Init ───────────────────────────────────────────────────────────────────

loadSessionHistory();
updateYouTubeStatus();
loadUploadedVideos();
showPanel("video");

// Handle OAuth callback redirect
const params = new URLSearchParams(window.location.search);
if (params.get("youtube") === "connected") {
  showAlert("YouTube account connected successfully.", "warning");
  window.history.replaceState({}, document.title, window.location.pathname);
}
