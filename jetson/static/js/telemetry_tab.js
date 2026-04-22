// ======================================================
// TELEMETRY TAB
//
// - Tab switching (Dashboard / Telemetry / Manual).
// - Populates the read-only grid from the existing telemetry stream
//   by wrapping updateTelemetryUI (same pattern controls.js already uses).
// - Drives the header link-quality strip from age fields.
// - Maintains a client-side ring buffer and exports it as CSV.
// ======================================================

// =====================
// TAB SWITCHING
// =====================
(function initTabs() {
    const btns = document.querySelectorAll('.tab-btn');
    btns.forEach(btn => {
        btn.addEventListener('click', () => {
            const target = btn.dataset.tab;
            if (btn.classList.contains('active')) return;

            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            const panel = document.getElementById('tab-' + target);
            if (panel) panel.classList.add('active');

            // Leaflet needs a nudge when its container becomes visible again,
            // otherwise tiles render at the wrong size until the next resize.
            if (target === 'dashboard' && typeof map !== 'undefined' && map) {
                setTimeout(() => map.invalidateSize(), 50);
            }
        });
    });
})();

// =====================
// LINK-QUALITY STRIP
// =====================
const LINK_THRESHOLDS = {
    // [warn_ms, stale_ms]. Below warn = green, between = yellow, above = red.
    gcs:   [2500, 6000],    // how long since a telemetry msg reached the browser
    pixh:  [1500, 3000],    // HB_AGE_MS from the server
    esp32: [6000, 15000],   // ESP32 emits @ 3s, so warn at 2x, stale at 5x
};

let _lastMsgAt = 0;  // browser timestamp of most recent telemetry msg

function applyLinkDot(dotEl, ageEl, ageMs, thresholds) {
    dotEl.classList.remove('ok', 'warn', 'stale');
    if (ageMs === null || ageMs === undefined || ageMs < 0) {
        dotEl.classList.add('stale');
        ageEl.textContent = '--';
        return;
    }
    const [warn, stale] = thresholds;
    if (ageMs > stale)      dotEl.classList.add('stale');
    else if (ageMs > warn)  dotEl.classList.add('warn');
    else                    dotEl.classList.add('ok');
    ageEl.textContent = ageMs >= 1000 ? (ageMs/1000).toFixed(1) + 's' : ageMs + 'ms';
}

function refreshLinkStrip() {
    const now = Date.now();

    // GCS link = browser → Jetson websocket. If the socket is dead, lastMsgAt
    // stops advancing and the age blows up, which is exactly the signal.
    const gcsAge = _lastMsgAt ? (now - _lastMsgAt) : -1;
    applyLinkDot(
        document.getElementById('linkGcs'),
        document.getElementById('linkGcsAge'),
        gcsAge, LINK_THRESHOLDS.gcs
    );

    const last = window.lastTelemetry;
    const hbAge   = last ? last.HB_AGE_MS    : -1;
    const espAge  = last ? last.ESP32_AGE_MS : -1;
    applyLinkDot(
        document.getElementById('linkPx'),
        document.getElementById('linkPxAge'),
        hbAge, LINK_THRESHOLDS.pixh
    );
    applyLinkDot(
        document.getElementById('linkEsp'),
        document.getElementById('linkEspAge'),
        espAge, LINK_THRESHOLDS.esp32
    );
}
setInterval(refreshLinkStrip, 500);

// =====================
// TELEMETRY BUFFER + CSV
// =====================
const TELEMETRY_BUF_MAX = 3600;   // 1 hour at 1 Hz
const telemetryBuf = [];

function pushToBuffer(t) {
    telemetryBuf.push({ ...t, _browserTime: Date.now() });
    if (telemetryBuf.length > TELEMETRY_BUF_MAX) telemetryBuf.shift();
    const count = document.getElementById('telemetryBufCount');
    if (count) count.textContent = telemetryBuf.length + ' rows buffered';
}

function downloadTelemetryCSV() {
    if (telemetryBuf.length === 0) {
        alert('Nothing to export — buffer is empty.');
        return;
    }
    const cols = Object.keys(telemetryBuf[0]);
    const header = cols.join(',');
    const rows = telemetryBuf.map(r =>
        cols.map(c => {
            const v = r[c];
            if (v === null || v === undefined) return '';
            const s = String(v);
            return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
        }).join(',')
    );
    const blob = new Blob([header + '\n' + rows.join('\n') + '\n'], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const ts = new Date().toISOString().replace(/[:.]/g, '-');
    const a = document.createElement('a');
    a.href = url;
    a.download = `aquabot_telemetry_${ts}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function clearTelemetryBuf() {
    telemetryBuf.length = 0;
    const count = document.getElementById('telemetryBufCount');
    if (count) count.textContent = '0 rows buffered';
}

document.getElementById('btnDownloadTelemetry')?.addEventListener('click', downloadTelemetryCSV);
document.getElementById('btnClearTelemetryBuf')?.addEventListener('click', clearTelemetryBuf);

// =====================
// GRID POPULATION
// =====================
function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = (val === null || val === undefined || val === '') ? '--' : val;
}

function fmtAge(ms) {
    if (ms === null || ms === undefined || ms < 0) return '--';
    return ms >= 1000 ? (ms/1000).toFixed(1) + ' s' : ms + ' ms';
}

function fmtFix(fixType) {
    // MAV GPS_FIX_TYPE
    return { 0: 'no fix', 1: 'no fix', 2: '2D', 3: '3D', 4: 'DGPS', 5: 'RTK-float', 6: 'RTK-fixed' }[fixType] ?? String(fixType);
}

function classifyAge(ms, warn, stale) {
    if (ms === null || ms === undefined || ms < 0) return 'stale';
    if (ms > stale) return 'stale';
    if (ms > warn)  return 'warn';
    return 'ok';
}

function setClass(id, cls) {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.remove('ok', 'warn', 'stale');
    if (cls) el.classList.add(cls);
}

function renderTelemetryTab(t) {
    setText('tMode',    t.MODE);
    setText('tArmed',   t.ARMED ? 'ARMED' : 'disarmed');
    setText('tHead',    t.HEAD !== undefined ? Number(t.HEAD).toFixed(1) + '°' : '--');
    setText('tSpd',     t.SPD  !== undefined ? Number(t.SPD).toFixed(2)  + ' m/s' : '--');
    setText('tThr',     t.THROTTLE_PCT !== undefined ? t.THROTTLE_PCT + ' %' : '--');
    setText('tSlow',    t.SLOW_MODE ? 'ON (30% cap)' : 'off');

    setText('tWP',      t.CURRENT_WP);
    setText('tWPTotal', t.WP_TOTAL);
    setText('tHome',    t.HOME_SET ? 'yes' : 'no');

    setText('tLat',     t.LAT);
    setText('tLon',     t.LON);
    setText('tGpsFix',  fmtFix(t.GPS_FIX));
    setText('tGpsSats', t.GPS_SATS);
    setText('tGpsHdop', t.GPS_HDOP);

    setText('tS1', t.SERVO1);
    setText('tS2', t.SERVO2);
    setText('tS3', t.SERVO3);
    setText('tS4', t.SERVO4);

    setText('tBatV',   t.BAT_V !== undefined ? t.BAT_V + ' V' : '--');
    setText('tBatA',   t.BAT_A !== undefined ? t.BAT_A + ' A' : '--');
    setText('tBatPct', (t.BAT_PCT !== undefined && t.BAT_PCT !== -1) ? t.BAT_PCT + ' %' : 'unknown');

    setText('tEkfCmp', t.EKF_COMPASS_VAR);
    setText('tEkfPos', t.EKF_POS_VAR);
    setText('tEkfVel', t.EKF_VEL_VAR);

    setText('tHBAge',  fmtAge(t.HB_AGE_MS));
    setText('tGpsAge', fmtAge(t.GPS_AGE_MS));
    setText('tEspAge', fmtAge(t.ESP32_AGE_MS));

    setClass('tHBAge',  classifyAge(t.HB_AGE_MS,    LINK_THRESHOLDS.pixh[0],  LINK_THRESHOLDS.pixh[1]));
    setClass('tGpsAge', classifyAge(t.GPS_AGE_MS,   3000, 10000));
    setClass('tEspAge', classifyAge(t.ESP32_AGE_MS, LINK_THRESHOLDS.esp32[0], LINK_THRESHOLDS.esp32[1]));

    setText('tTemp', t.TEMP);
    setText('tSal',  t.SAL);
    setText('tPh',   t.PH);

    const status = document.getElementById('tLastStatus');
    if (status && t.STATUS) {
        const sev = typeof t.STATUS_SEV === 'number' ? t.STATUS_SEV : 6;
        status.textContent = `Pixhawk [sev ${sev}]: ${t.STATUS}`;
        status.style.color = sev <= 3 ? '#ff6666' : sev <= 4 ? '#e6b800' : '#aaa';
    }
}

// =====================
// WIRE INTO EXISTING TELEMETRY PIPELINE
// =====================
// controls.js already wraps updateTelemetryUI. We chain ours on top so this
// file remains a self-contained add-on and doesn't tangle with existing logic.
const _prevUpdateTelemetryUI = window.updateTelemetryUI;
window.updateTelemetryUI = function(t) {
    if (_prevUpdateTelemetryUI) _prevUpdateTelemetryUI(t);
    _lastMsgAt = Date.now();
    try { renderTelemetryTab(t); } catch (e) { console.warn('telemetry tab render:', e); }
    try { pushToBuffer(t); }       catch (e) { console.warn('telemetry buffer:', e); }
};
