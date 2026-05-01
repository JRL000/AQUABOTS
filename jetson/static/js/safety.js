// ======================================================
// SAFETY LAYER
//
// - GCS heartbeat pings (Phase B1) so the Jetson knows we're alive
// - E-stop button wiring (B2)
// - Pre-arm checklist + admin bypass (B3)
// - Audible alerts on failsafe/low-battery/link-loss/E-stop (B4)
// - Toast notifications for save-confirm UX (shared with C3)
//
// Relies on the existing missionWS (controls.js) for control-plane messages
// and on updateTelemetryUI (webrtc.js + telemetry_tab.js) for state.
// ======================================================

// =====================
// SHARED STATE
// =====================
let adminToken    = sessionStorage.getItem('aquabot_admin_token') || null;
let alertsMuted   = false;
let lastFailsafeState = false;
let lastLowBatAlert   = 0;
let lastLinkLostAlert = 0;

// =====================
// TOASTS
// =====================
function toast(msg, kind, path, timeoutMs) {
    const region = document.getElementById('toastRegion');
    if (!region) { console.log('[toast]', msg); return; }
    const el = document.createElement('div');
    el.className = 'toast' + (kind ? ' ' + kind : '');
    el.innerHTML = '';
    const line = document.createElement('div');
    line.textContent = msg;
    el.appendChild(line);
    if (path) {
        const p = document.createElement('span');
        p.className = 'toast-path';
        p.textContent = path;
        el.appendChild(p);
    }
    region.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateX(20px)'; }, timeoutMs || 3500);
    setTimeout(() => el.remove(), (timeoutMs || 3500) + 250);
}
window.aquaToast = toast;  // exposed for controls.js / other modules

// =====================
// GCS HEARTBEAT (B1)
// =====================
function sendGcsHeartbeat() {
    // controls.js owns missionWS; re-using it avoids opening a fourth socket.
    if (typeof missionWS !== 'undefined' && missionWS && missionWS.readyState === WebSocket.OPEN) {
        try { missionWS.send(JSON.stringify({ action: 'gcs_heartbeat' })); } catch {}
    }
}
setInterval(sendGcsHeartbeat, 1000);

// =====================
// E-STOP (B2)
// =====================
function cmdEstop() {
    // No confirmation — this is an emergency button by design. Muscle memory.
    beep('estop');
    if (typeof missionWS !== 'undefined' && missionWS && missionWS.readyState === WebSocket.OPEN) {
        try { missionWS.send(JSON.stringify({ action: 'estop' })); } catch (e) { console.warn('estop send:', e); }
    }
    toast('E-STOP sent — vehicle disarming', 'error');
}
document.getElementById('btnEStop')?.addEventListener('click', cmdEstop);

// =====================
// MUTE TOGGLE (B4)
// =====================
function updateMuteBtn() {
    const b = document.getElementById('btnMute');
    if (b) b.textContent = alertsMuted ? '\uD83D\uDD07' : '\uD83D\uDD0A';
}
document.getElementById('btnMute')?.addEventListener('click', () => {
    alertsMuted = !alertsMuted;
    updateMuteBtn();
    toast('Alerts ' + (alertsMuted ? 'muted' : 'unmuted'));
});
updateMuteBtn();

// =====================
// ADMIN LOGIN (B3 / C1)
// =====================
function updateAdminBtn() {
    const b = document.getElementById('btnAdmin');
    if (!b) return;
    if (adminToken) {
        b.textContent = '\uD83D\uDD13 Admin';
        b.classList.add('admin-active');
        b.title = 'Admin session active — click to log out';
    } else {
        b.textContent = '\uD83D\uDC64 Admin';
        b.classList.remove('admin-active');
        b.title = 'Admin login';
    }
    // Bypass row is only useful when logged in.
    const bypassLabel = document.querySelector('.prearm-bypass');
    if (bypassLabel) bypassLabel.style.display = adminToken ? 'block' : 'none';
    // Manual tab hint — keep the lock icon consistent with actual state.
    const manualLock = document.querySelector('.tab-btn[data-tab="manual"] .tab-lock');
    if (manualLock) manualLock.textContent = adminToken ? '\uD83D\uDD13' : '\uD83D\uDD12';
}

function promptAdminLogin() {
    const pw = prompt('Admin password (leave blank to cancel):');
    if (!pw) return;
    if (typeof missionWS === 'undefined' || !missionWS || missionWS.readyState !== WebSocket.OPEN) {
        toast('Not connected to Jetson', 'error'); return;
    }
    // Stash a one-shot handler for the response so we don't steal replies from
    // the general mission-status path.
    const handler = (e) => {
        let d; try { d = JSON.parse(e.data); } catch { return; }
        if (d.token) {
            adminToken = d.token;
            sessionStorage.setItem('aquabot_admin_token', adminToken);
            toast('Admin login ok');
            updateAdminBtn();
            missionWS.removeEventListener('message', handler);
        } else if (d.status === 'error' && d.message && d.message.indexOf('admin') !== -1) {
            toast('Admin: ' + d.message, 'error');
            missionWS.removeEventListener('message', handler);
        }
    };
    missionWS.addEventListener('message', handler);
    missionWS.send(JSON.stringify({ action: 'admin_login', password: pw }));
    setTimeout(() => missionWS.removeEventListener('message', handler), 4000);
}

function adminLogout() {
    if (!adminToken) return;
    if (typeof missionWS !== 'undefined' && missionWS && missionWS.readyState === WebSocket.OPEN) {
        missionWS.send(JSON.stringify({ action: 'admin_logout', token: adminToken }));
    }
    adminToken = null;
    sessionStorage.removeItem('aquabot_admin_token');
    const bypass = document.getElementById('preArmBypass');
    if (bypass) bypass.checked = false;
    toast('Admin logged out');
    updateAdminBtn();
}

document.getElementById('btnAdmin')?.addEventListener('click', () => {
    if (adminToken) {
        if (confirm('Log out of admin?')) adminLogout();
    } else {
        promptAdminLogin();
    }
});
updateAdminBtn();

// Expose admin state so manual tab (Phase C1) can unlock itself later.
window.aquaAdminActive = () => !!adminToken;

// =====================
// FAILSAFE BANNER + ALERTS (B1/B4)
// =====================
function updateFailsafeBanner(t) {
    const banner = document.getElementById('failsafeBanner');
    if (!banner) return;
    const tripped = !!t.FAILSAFE_TRIPPED;
    if (tripped && !lastFailsafeState) beep('failsafe');
    lastFailsafeState = tripped;
    banner.style.display = tripped ? 'block' : 'none';
    const detail = document.getElementById('failsafeBannerDetail');
    if (detail) {
        detail.textContent = tripped
            ? `action=${t.WATCHDOG_ACTION}  timeout=${t.WATCHDOG_TIMEOUT}s  gcs_age=${t.GCS_AGE_MS}ms`
            : '';
    }
}

// =====================
// AUDIO ALERTS (B4)
// =====================
// WebAudio-only — no sound files to bundle. Each alert picks a short tone
// pattern so the operator can distinguish them by ear.
let _audioCtx = null;
function audioCtx() {
    if (!_audioCtx && typeof AudioContext !== 'undefined') _audioCtx = new AudioContext();
    return _audioCtx;
}
function tone(freq, durMs, type) {
    if (alertsMuted) return;
    const ctx = audioCtx(); if (!ctx) return;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type || 'sine';
    osc.frequency.value = freq;
    gain.gain.value = 0.12;
    osc.connect(gain); gain.connect(ctx.destination);
    osc.start();
    setTimeout(() => { osc.stop(); }, durMs);
}
function beep(kind) {
    if (alertsMuted) return;
    if (kind === 'failsafe') {
        tone(880, 200, 'square'); setTimeout(() => tone(660, 250, 'square'), 220);
        setTimeout(() => tone(880, 200, 'square'), 500);
    } else if (kind === 'lowbatt') {
        tone(440, 600, 'triangle');
    } else if (kind === 'linklost') {
        tone(330, 400, 'sawtooth'); setTimeout(() => tone(220, 400, 'sawtooth'), 420);
    } else if (kind === 'estop') {
        tone(1200, 120, 'square'); setTimeout(() => tone(900, 120, 'square'), 140);
    }
}
window.aquaBeep = beep;

// =====================
// PRE-ARM CHECKLIST (B3)
// =====================
const PREARM_RULES = {
    gcs:       { warn: 2500, fail: 6000 },    // GCS_AGE_MS thresholds
    pixhawk:   { warn: 1500, fail: 3000 },    // HB_AGE_MS
    // 6S LiPo: warn < 22.2 V (3.7 V/cell nominal), fail < 20.4 V (3.4 V/cell).
    battery:   { warnV: 22.2, failV: 20.4 },
};

function prearmClassify(t) {
    const state = {};
    const v = (k, cls, detail) => state[k] = { cls, detail };

    const gcsAge = t.GCS_AGE_MS ?? -1;
    v('gcs',
      gcsAge < 0 ? 'fail' : gcsAge > PREARM_RULES.gcs.fail ? 'fail' : gcsAge > PREARM_RULES.gcs.warn ? 'warn' : 'ok',
      gcsAge < 0 ? '--' : gcsAge + 'ms'
    );

    const hbAge = t.HB_AGE_MS ?? -1;
    v('pixhawk',
      hbAge < 0 ? 'fail' : hbAge > PREARM_RULES.pixhawk.fail ? 'fail' : hbAge > PREARM_RULES.pixhawk.warn ? 'warn' : 'ok',
      hbAge < 0 ? '--' : hbAge + 'ms'
    );

    const gpsFix = Number(t.GPS_FIX || 0);
    v('gps',
      gpsFix >= 3 ? 'ok' : gpsFix === 2 ? 'warn' : 'fail',
      `fix=${gpsFix} sats=${t.GPS_SATS ?? '--'}`
    );

    v('home',
      t.HOME_SET ? 'ok' : 'fail',
      t.HOME_SET ? 'yes' : 'waiting'
    );

    const cmpVar = Number(t.EKF_COMPASS_VAR || 0);
    v('compass',
      cmpVar <= 0.5 ? 'ok' : cmpVar <= 1.0 ? 'warn' : 'fail',
      `var=${cmpVar.toFixed(2)}`
    );

    const vbat = Number(t.BAT_V || 0);
    if (vbat < 0.1) {
        v('battery', 'warn', 'no reading');
    } else {
        v('battery',
          vbat >= PREARM_RULES.battery.warnV ? 'ok' : vbat >= PREARM_RULES.battery.failV ? 'warn' : 'fail',
          `${vbat.toFixed(2)} V`
        );
    }

    const wps = (typeof waypoints !== 'undefined' && Array.isArray(waypoints)) ? waypoints.length : 0;
    v('waypoints',
      wps > 0 ? 'ok' : 'fail',
      wps + ' placed'
    );

    return state;
}

function applyPrearmUI(state) {
    const list = document.querySelector('.prearm-list');
    if (!list) return;
    let worst = 'ok';
    list.querySelectorAll('li').forEach(li => {
        const k = li.dataset.key;
        const s = state[k];
        li.classList.remove('ok', 'warn', 'fail');
        if (s) {
            li.classList.add(s.cls);
            const det = li.querySelector('em[data-detail]');
            if (det) det.textContent = s.detail;
            if (s.cls === 'fail' || (s.cls === 'warn' && worst === 'ok')) worst = s.cls;
            if (s.cls === 'fail') worst = 'fail';
        }
    });
    const summary = document.getElementById('preArmSummary');
    if (summary) {
        summary.classList.remove('ok', 'warn', 'fail');
        summary.classList.add(worst === 'ok' ? 'ok' : worst === 'warn' ? 'warn' : 'fail');
        summary.textContent = worst === 'ok' ? 'READY' : worst === 'warn' ? 'WARNINGS' : 'NOT READY';
    }
    // Mirror to the status HUD pill at the top of the page.
    const hudVal = document.getElementById('hudPrearmVal');
    const hudPill = document.getElementById('hudPrearm');
    if (hudVal && hudPill) {
        hudVal.textContent = worst === 'ok' ? 'READY' : worst === 'warn' ? 'WARN' : 'NOT READY';
        hudPill.classList.toggle('hud-good', worst === 'ok');
        hudPill.classList.toggle('hud-warn', worst === 'warn');
        hudPill.classList.toggle('hud-bad',  worst === 'fail');
    }
    return worst;
}

function applyStartMissionGate(worst) {
    const btn = document.getElementById('btnStartMission');
    if (!btn) return;
    const bypass = document.getElementById('preArmBypass');
    const bypassActive = adminToken && bypass && bypass.checked;
    const block = (worst === 'fail') && !bypassActive;
    btn.disabled = block;
    btn.title = block
        ? 'Pre-arm checks are not satisfied. Admin bypass required to force start.'
        : bypassActive
            ? 'Admin bypass ACTIVE — pre-arm checks skipped.'
            : '';
}

// =====================
// LOW-BATTERY + LINK-LOST ALERT TRIGGERS (B4)
// =====================
function maybeTriggerAlerts(t) {
    const now = Date.now();
    const vbat = Number(t.BAT_V || 0);
    if (vbat > 0.1 && vbat < PREARM_RULES.battery.failV && now - lastLowBatAlert > 30000) {
        lastLowBatAlert = now;
        beep('lowbatt');
        toast(`Low battery: ${vbat.toFixed(2)} V`, 'warn');
    }
    const gcsAge = t.GCS_AGE_MS ?? -1;
    const hbAge  = t.HB_AGE_MS  ?? -1;
    const linkLost = (gcsAge > PREARM_RULES.gcs.fail) || (hbAge > PREARM_RULES.pixhawk.fail);
    if (linkLost && now - lastLinkLostAlert > 10000) {
        lastLinkLostAlert = now;
        beep('linklost');
    }
}

// =====================
// WIRE EVERYTHING INTO THE TELEMETRY PIPELINE
// =====================
const _prev_safetyUpdate = window.updateTelemetryUI;
window.updateTelemetryUI = function(t) {
    if (_prev_safetyUpdate) _prev_safetyUpdate(t);
    try { updateFailsafeBanner(t); } catch (e) { console.warn('failsafe banner:', e); }
    try {
        const state = prearmClassify(t);
        const worst = applyPrearmUI(state);
        applyStartMissionGate(worst);
    } catch (e) { console.warn('prearm:', e); }
    try { maybeTriggerAlerts(t); } catch (e) { console.warn('alerts:', e); }
};

// When the operator (un)checks the bypass, immediately reflect it on the
// START MISSION button without waiting for the next telemetry tick.
document.getElementById('preArmBypass')?.addEventListener('change', () => {
    if (typeof window.lastTelemetry !== 'undefined' && window.lastTelemetry) {
        const state = prearmClassify(window.lastTelemetry);
        const worst = applyPrearmUI(state);
        applyStartMissionGate(worst);
    }
});
