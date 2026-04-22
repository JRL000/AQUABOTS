// ======================================================
// MANUAL TAB (Phase C1)
//
// - Shows a locked placeholder until aquaAdminActive() returns true.
// - Once unlocked: ARM/DISARM buttons, mode switcher, virtual sliders,
//   optional USB gamepad via the Gamepad API.
// - Sends {"action":"manual_rc", ch1, ch3, token} while override is engaged.
//   Stops sending and releases when the operator disengages or leaves the tab.
// ======================================================

const MANUAL_SEND_HZ = 20;
const MANUAL_NEUTRAL = 1500;
const MANUAL_MIN     = 1100;
const MANUAL_MAX     = 1900;

let manualActive = false;
let manualSendTimer = null;
let gamepadIndex = null;

function mEl(id) { return document.getElementById(id); }

function manualSyncVisibility() {
    const adminActive = typeof window.aquaAdminActive === 'function' && window.aquaAdminActive();
    const locked = mEl('manualLocked');
    const wrap   = mEl('manualWrap');
    if (locked) locked.style.display = adminActive ? 'none'  : 'block';
    if (wrap)   wrap.style.display   = adminActive ? 'block' : 'none';
    if (!adminActive && manualActive) disengage();
}
setInterval(manualSyncVisibility, 500);
manualSyncVisibility();

mEl('btnManualLoginPrompt')?.addEventListener('click', () => {
    // Reuse the existing admin button's flow rather than duplicating the prompt.
    mEl('btnAdmin')?.click();
});

// =====================
// STATUS UPDATER
// =====================
function renderManualStatus(t) {
    if (!t) return;
    mEl('mMode').textContent     = t.MODE || '--';
    mEl('mArmed').textContent    = t.ARMED ? 'ARMED' : 'disarmed';
    mEl('mOverride').textContent = manualActive ? 'ENGAGED' : 'inactive';
    mEl('mOverride').style.color = manualActive ? '#ff6666' : '#66ff88';
}

const _prev_manualUpdate = window.updateTelemetryUI;
window.updateTelemetryUI = function(t) {
    if (_prev_manualUpdate) _prev_manualUpdate(t);
    try { renderManualStatus(t); } catch (e) { console.warn('manual status:', e); }
};

// =====================
// BUTTON WIRING
// =====================
function sendJson(o) {
    if (typeof missionWS === 'undefined' || !missionWS || missionWS.readyState !== WebSocket.OPEN) {
        if (window.aquaToast) window.aquaToast('Not connected to Jetson', 'error');
        return false;
    }
    try { missionWS.send(JSON.stringify(o)); return true; } catch (e) { console.warn('send:', e); return false; }
}

function adminTokenOr(fail) {
    const tok = sessionStorage.getItem('aquabot_admin_token');
    if (!tok) {
        if (window.aquaToast) window.aquaToast('Admin session expired', 'error');
        fail?.();
        return null;
    }
    return tok;
}

mEl('btnManualMode')?.addEventListener('click', () => {
    const tok = adminTokenOr();
    if (!tok) return;
    sendJson({ action: 'set_mode', mode: 'MANUAL', token: tok });
    if (window.aquaToast) window.aquaToast('Switching to MANUAL...');
});

mEl('btnManualArm')?.addEventListener('click', () => {
    if (typeof controlWS !== 'undefined' && controlWS && controlWS.readyState === WebSocket.OPEN) {
        controlWS.send('ARM');
    }
    if (window.aquaToast) window.aquaToast('ARM sent');
});

mEl('btnManualDisarm')?.addEventListener('click', () => {
    if (typeof controlWS !== 'undefined' && controlWS && controlWS.readyState === WebSocket.OPEN) {
        controlWS.send('DISARM');
    }
    if (window.aquaToast) window.aquaToast('DISARM sent');
});

mEl('btnManualEngage')?.addEventListener('click', engage);
mEl('btnManualRelease')?.addEventListener('click', disengage);

// =====================
// SLIDER + GAMEPAD POLLING
// =====================
function clamp(v) { return Math.max(MANUAL_MIN, Math.min(MANUAL_MAX, v | 0)); }
function readStick() {
    const gp = (gamepadIndex !== null) ? navigator.getGamepads?.()[gamepadIndex] : null;
    let steerPwm = parseInt(mEl('mSteer').value, 10);
    let throtPwm = parseInt(mEl('mThrot').value, 10);
    if (gp && gp.connected) {
        // Left stick X (axis 0) → steering; right stick Y (axis 3, inverted) → throttle.
        const x = gp.axes[0] ?? 0;
        const y = -1 * (gp.axes[3] ?? 0);
        steerPwm = clamp(MANUAL_NEUTRAL + x * 400);
        throtPwm = clamp(MANUAL_NEUTRAL + y * 400);
        mEl('mSteer').value = steerPwm;
        mEl('mThrot').value = throtPwm;
    }
    mEl('mSteerVal').textContent = steerPwm;
    mEl('mThrotVal').textContent = throtPwm;
    return { ch1: steerPwm, ch3: throtPwm };
}

function springToCenter() {
    // Sliders spring back when released (mouse up / touch end).
    mEl('mThrot').value = MANUAL_NEUTRAL;
    mEl('mThrotVal').textContent = MANUAL_NEUTRAL;
}
mEl('mThrot')?.addEventListener('mouseup',  springToCenter);
mEl('mThrot')?.addEventListener('touchend', springToCenter);

window.addEventListener('gamepadconnected',    e => { gamepadIndex = e.gamepad.index; mEl('mGamepad').textContent = e.gamepad.id; });
window.addEventListener('gamepaddisconnected', e => { if (gamepadIndex === e.gamepad.index) { gamepadIndex = null; mEl('mGamepad').textContent = 'not detected'; } });

// =====================
// ENGAGE / DISENGAGE
// =====================
function engage() {
    const tok = adminTokenOr(() => manualSyncVisibility());
    if (!tok) return;
    if (manualActive) return;
    manualActive = true;
    mEl('mOverride').textContent = 'ENGAGED';
    mEl('mOverride').style.color = '#ff6666';
    if (window.aquaToast) window.aquaToast('Manual override engaged — keep both hands on controls');
    manualSendTimer = setInterval(() => {
        const { ch1, ch3 } = readStick();
        sendJson({ action: 'manual_rc', token: tok, ch1, ch3 });
    }, 1000 / MANUAL_SEND_HZ);
}

function disengage() {
    if (!manualActive && manualSendTimer === null) return;
    manualActive = false;
    if (manualSendTimer !== null) { clearInterval(manualSendTimer); manualSendTimer = null; }
    const tok = sessionStorage.getItem('aquabot_admin_token');
    if (tok) sendJson({ action: 'manual_release', token: tok });
    mEl('mOverride').textContent = 'inactive';
    mEl('mOverride').style.color = '#66ff88';
    if (window.aquaToast) window.aquaToast('Manual override released');
}

// Safety: if the operator navigates away from the Manual tab, release the
// override automatically so the boat doesn't keep taking stale inputs.
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        if (btn.dataset.tab !== 'manual' && manualActive) disengage();
    });
});
window.addEventListener('beforeunload', () => { if (manualActive) disengage(); });
