import { fetchMission, fetchSessions } from "./api.js";
import { initThemeEngine } from "./theme-engine.js";

const TELEMETRY_FEED_INTERVAL_MS = 500;
const TELEMETRY_MAX_QUEUE_SIZE = 100;
const TELEMETRY_MAX_LINES = 16;
const HUD_UPDATE_INTERVAL_MS = 700;
const HUD_DRIFT_CPU = 4;
const HUD_DRIFT_RAM = 3;
const HUD_DRIFT_CACHE = 6;
const HUD_MIN_CPU = 7;
const HUD_MIN_RAM = 9;
const HUD_MIN_CACHE = 5;
const HUD_MAX_CPU = 94;
const HUD_MAX_RAM = 95;
const HUD_MAX_CACHE = 92;
const LATENCY_TICK_INTERVAL_MS = 3000;
const LATENCY_MIN_MS = 9;
const LATENCY_JITTER_MS = 8;
const AUTO_REFRESH_INTERVAL_MS = 5000;

const state = {
    selectedSessionId: "",
    autoRefreshTimer: null,
    telemetryFeedTimer: null,
    telemetryRafHandle: null,
    telemetryQueue: [],
    hudRafHandle: null,
    hudLastTs: 0,
    hudValues: { cpu: 33, ram: 47, cache: 21 },
    latencyTimer: null
};

const ui = {
    modeSelect: document.getElementById("modeSelect"),
    refreshSessionsBtn: document.getElementById("btnRefreshSessions"),
    refreshMissionBtn: document.getElementById("btnRefreshMission"),
    sessionSelect: document.getElementById("sessionSelect"),
    autoRefresh: document.getElementById("autoRefresh"),
    content: document.getElementById("content"),
    cpuBar: document.getElementById("cpuBar"),
    ramBar: document.getElementById("ramBar"),
    cacheBar: document.getElementById("cacheBar"),
    latencyTicker: document.getElementById("latencyTicker"),
    fingerprint: document.getElementById("sessionFingerprint")
};

initThemeEngine(ui.modeSelect);

function normalizeResult(raw) {
    return String(raw || "").trim().toLowerCase().replace(/\s+/g, "");
}

function resultTag(raw) {
    const result = normalizeResult(raw);
    if (result === "success") {
        return '<span class="status-chip success">Success</span>';
    }
    if (result === "inprogress" || result === "in_progress") {
        return '<span class="status-chip inprogress">In Progress</span>';
    }
    if (result === "aborted") {
        return '<span class="status-chip aborted">Aborted</span>';
    }
    return `<span class="status-chip other">${escapeHtml(String(raw || "Unknown"))}</span>`;
}

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function formatUnixTime(unix) {
    if (!unix || unix === "0") {
        return "\u2014";
    }
    const date = new Date(Number.parseInt(unix, 10) * 1000);
    return Number.isNaN(date.getTime()) ? "\u2014" : date.toLocaleString();
}

function ringStroke(progressPercent) {
    const radius = 17;
    const circumference = 2 * Math.PI * radius;
    const clamped = Math.min(100, Math.max(0, progressPercent));
    const shown = (clamped / 100) * circumference;
    return `${shown.toFixed(2)} ${(circumference - shown).toFixed(2)}`;
}

function computeFingerprint(seedText) {
    let seed = 0;
    for (let i = 0; i < seedText.length; i += 1) {
        seed = (seed + seedText.charCodeAt(i) * (i + 1)) % 65536;
    }
    const blocks = [];
    for (let i = 0; i < 6; i += 1) {
        seed = (seed * 1103 + 17) % 65536;
        const value = ((seed >> 8) & 255).toString(16).toUpperCase().padStart(2, "0");
        blocks.push(value);
    }
    return `0x${blocks.join("-")}`;
}

function telemetryStepFromMission(mission, tick) {
    const { forward, left, right, reverse, total } = mission.moves;
    const x = (Math.sin(tick / 4) * 22 + (forward - reverse) * 0.7).toFixed(3);
    const y = (Math.cos(tick / 5) * 21 + (right - left) * 0.7).toFixed(3);
    const z = (Math.sin(tick / 7) * 11 + total * 0.03).toFixed(3);
    return `X:${x.padStart(8, " ")}  Y:${y.padStart(8, " ")}  Z:${z.padStart(8, " ")}`;
}

function stopTelemetryLoop() {
    if (state.telemetryFeedTimer) {
        clearInterval(state.telemetryFeedTimer);
        state.telemetryFeedTimer = null;
    }
    if (state.telemetryRafHandle) {
        cancelAnimationFrame(state.telemetryRafHandle);
        state.telemetryRafHandle = null;
    }
    state.telemetryQueue = [];
}

function startTelemetryLoop(mission) {
    const stream = document.getElementById("telemetryStream");
    if (!stream) {
        return;
    }
    stopTelemetryLoop();

    let tick = 0;
    state.telemetryFeedTimer = setInterval(() => {
        state.telemetryQueue.push(telemetryStepFromMission(mission, tick));
        if (state.telemetryQueue.length > TELEMETRY_MAX_QUEUE_SIZE) {
            state.telemetryQueue.shift();
        }
        tick += 1;
    }, TELEMETRY_FEED_INTERVAL_MS);

    const renderQueue = () => {
        if (state.telemetryQueue.length) {
            const lineText = state.telemetryQueue.shift();
            const line = document.createElement("div");
            line.className = "telemetry-line";
            line.textContent = lineText;
            stream.prepend(line);
            while (stream.children.length > TELEMETRY_MAX_LINES) {
                stream.removeChild(stream.lastChild);
            }
        }
        state.telemetryRafHandle = requestAnimationFrame(renderQueue);
    };

    state.telemetryRafHandle = requestAnimationFrame(renderQueue);
}

function updateHudBars(ts) {
    if (!state.hudLastTs || ts - state.hudLastTs > HUD_UPDATE_INTERVAL_MS) {
        const drift = (value, delta, min, max) => Math.max(min, Math.min(max, value + (Math.random() * delta * 2 - delta)));
        state.hudValues.cpu = drift(state.hudValues.cpu, HUD_DRIFT_CPU, HUD_MIN_CPU, HUD_MAX_CPU);
        state.hudValues.ram = drift(state.hudValues.ram, HUD_DRIFT_RAM, HUD_MIN_RAM, HUD_MAX_RAM);
        state.hudValues.cache = drift(state.hudValues.cache, HUD_DRIFT_CACHE, HUD_MIN_CACHE, HUD_MAX_CACHE);

        ui.cpuBar.style.width = `${state.hudValues.cpu.toFixed(1)}%`;
        ui.ramBar.style.width = `${state.hudValues.ram.toFixed(1)}%`;
        ui.cacheBar.style.width = `${state.hudValues.cache.toFixed(1)}%`;
        state.hudLastTs = ts;
    }
    state.hudRafHandle = requestAnimationFrame(updateHudBars);
}

function startHudLoop() {
    if (!state.hudRafHandle) {
        state.hudRafHandle = requestAnimationFrame(updateHudBars);
    }
}

function startLatencyTicker() {
    if (state.latencyTimer) {
        clearInterval(state.latencyTimer);
    }
    state.latencyTimer = setInterval(() => {
        const latency = (LATENCY_MIN_MS + Math.random() * LATENCY_JITTER_MS).toFixed(0);
        ui.latencyTicker.textContent = `Server: Redis-v4.2 | Latency: ${latency}ms | Handshake: SECURE.`;
    }, LATENCY_TICK_INTERVAL_MS);
}

function renderMission(mission) {
    const total = mission.moves.total;
    const duration = mission.durationSeconds;
    const distance = mission.distanceMeters.toFixed(2);
    const speed = duration > 0 ? (mission.distanceMeters / duration).toFixed(3) : "\u2014";
    const durationProgress = Math.min(100, (duration / 300) * 100);
    const distanceProgress = Math.min(100, (mission.distanceMeters / 40) * 100);

    ui.content.innerHTML = `
    <div class="stats">
      <div class="stat-card">
        <div class="stat-label">Total Moves</div>
        <div class="stat-value">${total}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Duration</div>
        <div class="stat-value">${duration}<span style="font-size:0.95rem;color:var(--muted)">s</span></div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Distance</div>
        <div class="stat-value">${distance}<span style="font-size:0.95rem;color:var(--muted)">m</span></div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Status</div>
        <div class="stat-value" style="font-size:1.05rem">${resultTag(mission.missionResult)}</div>
      </div>
    </div>

    <div class="detail-grid">
      <div class="detail-card">
        <h3>Mission Identity</h3>
        <div class="kv"><span class="k">Session ID</span><span class="v">${escapeHtml(mission.sessionId || "\u2014")}</span></div>
        <div class="kv"><span class="k">Robot ID</span><span class="v">${escapeHtml(mission.robotId || "\u2014")}</span></div>
        <div class="kv"><span class="k">Mission Type</span><span class="v">${escapeHtml(mission.missionType || "\u2014")}</span></div>
        <div class="kv"><span class="k">Result</span><span class="v">${resultTag(mission.missionResult)}</span></div>
        ${mission.abortReason ? `<div class="kv"><span class="k">Abort Reason</span><span class="v">${escapeHtml(mission.abortReason)}</span></div>` : ""}
      </div>
      <div class="detail-card">
        <h3>Timing</h3>
        <div class="kv"><span class="k">Start Time</span><span class="v">${formatUnixTime(mission.startTime)}</span></div>
        <div class="kv"><span class="k">End Time</span><span class="v">${formatUnixTime(mission.endTime)}</span></div>
        <div class="kv"><span class="k">Duration</span><span class="v">${duration} sec</span></div>
        <div class="kv"><span class="k">Avg Speed</span><span class="v">${speed} m/s</span></div>
      </div>
    </div>

    <div class="detail-grid">
      <div class="detail-card">
        <h3>Movement Breakdown</h3>
        <div class="movement-wrap">
          <div id="movementMatrix" class="movement-matrix">
            <div class="mv-cell"></div>
            <div class="mv-cell"><span class="mv-value ${mission.moves.forward > 0 ? "active" : "idle"}">${mission.moves.forward}</span></div>
            <div class="mv-cell"></div>
            <div class="mv-cell"><span class="mv-value ${mission.moves.left > 0 ? "active" : "idle"}">${mission.moves.left}</span></div>
            <div class="mv-cell center">${total}</div>
            <div class="mv-cell"><span class="mv-value ${mission.moves.right > 0 ? "active" : "idle"}">${mission.moves.right}</span></div>
            <div class="mv-cell"></div>
            <div class="mv-cell"><span class="mv-value ${mission.moves.reverse > 0 ? "active" : "idle"}">${mission.moves.reverse}</span></div>
            <div class="mv-cell"></div>
          </div>
          <div class="telemetry">
            <div class="telemetry-title">Telemetry Stream</div>
            <div id="telemetryStream"></div>
          </div>
        </div>
      </div>
      <div class="detail-card">
        <h3>Distance &amp; Totals</h3>
        <div class="gauge-grid">
          <div class="gauge-card">
            <svg class="ring" viewBox="0 0 40 40" aria-hidden="true">
              <circle class="track" cx="20" cy="20" r="17"></circle>
              <circle class="fill" cx="20" cy="20" r="17" stroke-dasharray="${ringStroke(durationProgress)}"></circle>
            </svg>
            <div class="gauge-meta">
              <div class="g-label">Chrono Gauge / Duration</div>
              <div class="g-value">${duration}s</div>
            </div>
          </div>
          <div class="gauge-card">
            <svg class="ring" viewBox="0 0 40 40" aria-hidden="true">
              <circle class="track" cx="20" cy="20" r="17"></circle>
              <circle class="fill" cx="20" cy="20" r="17" stroke-dasharray="${ringStroke(distanceProgress)}"></circle>
            </svg>
            <div class="gauge-meta">
              <div class="g-label">Chrono Gauge / Distance</div>
              <div class="g-value">${distance}m</div>
            </div>
          </div>
        </div>
        <div class="kv"><span class="k">Total Moves</span><span class="v">${total}</span></div>
        <div class="kv"><span class="k">Distance Traveled</span><span class="v">${distance} m</span></div>
        <div class="kv"><span class="k">Directional Ratio</span><span class="v">${mission.moves.forward}:${mission.moves.right}:${mission.moves.reverse}:${mission.moves.left}</span></div>
      </div>
    </div>
  `;

    const matrix = document.getElementById("movementMatrix");
    matrix.addEventListener("mouseenter", () => matrix.classList.add("engaged"));
    matrix.addEventListener("mouseleave", () => matrix.classList.remove("engaged"));
    matrix.addEventListener("click", () => matrix.classList.toggle("engaged"));

    ui.fingerprint.textContent = computeFingerprint(`${mission.sessionId}-${mission.moves.total}-${Date.now() % 10000}`);
    startTelemetryLoop(mission);
}

function showError(error) {
    ui.content.innerHTML = `<div class="error-msg">${escapeHtml(error.message || "Unknown error")}</div>`;
}

function setMissionButtonState() {
    ui.refreshMissionBtn.disabled = !state.selectedSessionId;
}

async function loadSessions() {
    try {
        const sessions = await fetchSessions();
        const previous = state.selectedSessionId;
        ui.sessionSelect.innerHTML = '<option value="">-- select session --</option>';

        sessions.forEach((session) => {
            const option = document.createElement("option");
            option.value = session.sessionId;
            const result = normalizeResult(session.missionResult);
            const badge = result === "success" ? " [OK]" : result === "inprogress" ? " [...]" : result === "aborted" ? " [ABT]" : "";
            option.textContent = `${session.sessionId}${badge} (${session.movesTotal} moves)`;
            ui.sessionSelect.appendChild(option);
        });

        if (previous && sessions.some((s) => s.sessionId === previous)) {
            ui.sessionSelect.value = previous;
            state.selectedSessionId = previous;
        } else if (!sessions.length) {
            state.selectedSessionId = "";
        }
        setMissionButtonState();
    } catch (error) {
        showError(error);
    }
}

async function loadMission() {
    if (!state.selectedSessionId) {
        return;
    }
    try {
        const mission = await fetchMission(state.selectedSessionId);
        renderMission(mission);
    } catch (error) {
        showError(error);
    }
}

function toggleAutoRefresh() {
    if (ui.autoRefresh.checked) {
        state.autoRefreshTimer = setInterval(() => {
            if (state.selectedSessionId) {
                loadMission();
            }
        }, AUTO_REFRESH_INTERVAL_MS);
    } else if (state.autoRefreshTimer) {
        clearInterval(state.autoRefreshTimer);
        state.autoRefreshTimer = null;
    }
}

ui.refreshSessionsBtn.addEventListener("click", () => {
    loadSessions();
});

ui.refreshMissionBtn.addEventListener("click", () => {
    loadMission();
});

ui.sessionSelect.addEventListener("change", () => {
    state.selectedSessionId = ui.sessionSelect.value;
    setMissionButtonState();
    if (state.selectedSessionId) {
        loadMission();
    } else {
        stopTelemetryLoop();
    }
});

ui.autoRefresh.addEventListener("change", toggleAutoRefresh);

startHudLoop();
startLatencyTicker();
loadSessions();
