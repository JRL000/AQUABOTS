// ======================================================
// MISSION CONTROL — State Machine
//
// Phases: idle → uploaded → running ⇄ paused
//                         → returning ⇄ rth_paused
//         any active → complete (vehicle disarms)
//         any        → idle     (ABORT)
// ======================================================

let waypointMode      = false;
let waypoints         = [];
let waypointMarkers   = [];
let missionWS         = null;
let mapClickAttached  = false;
let waypointsRestored = false;
let _lastDroneLat     = null;
let _lastDroneLon     = null;
let modeUpdateSuppressUntil = 0;
let missionPhase      = 'idle';
let lastKnownMode     = '';

// =====================
// MISSION WEBSOCKET
// =====================
function connectMissionWS() {
    const host = window.location.hostname;
    missionWS = new WebSocket(`ws://${host}:8770`);
    missionWS.onopen  = () => setMissionStatus('Connected to Jetson.');
    missionWS.onclose = () => { setMissionStatus('Disconnected — reconnecting...', true); setTimeout(connectMissionWS, 2000); };
    missionWS.onerror = () => missionWS.close();
    missionWS.onmessage = (e) => {
        try {
            const d = JSON.parse(e.data);
            if (d.status === undefined) return;
            setMissionStatus(d.message, d.status !== 'ok');
            if (d.status === 'ok' && d.message && /uploaded/.test(d.message)) {
                setMissionPhase('uploaded');
            }
        } catch {}
    };
}
connectMissionWS();

// =====================
// STATUS DISPLAY
// =====================
function setMissionStatus(msg, isError) {
    const el = document.getElementById('missionStatus');
    if (!el) return;
    el.textContent           = msg;
    el.style.color           = isError ? '#ff6666' : '#66ff88';
    el.style.borderLeftColor = isError ? '#ff6666' : '#66ff88';
}

// =====================
// PHASE STATE MACHINE
// =====================
const PHASE_UI = {
    idle:       { label: 'IDLE',                   bg: '#1a1a1a', color: '#888888' },
    uploaded:   { label: 'READY TO LAUNCH',        bg: '#001a33', color: '#4499ff' },
    running:    { label: '\u25B6  MISSION RUNNING', bg: '#001a00', color: '#00ee55' },
    paused:     { label: '\u23F8  MISSION PAUSED',  bg: '#1a1100', color: '#ffaa00' },
    returning:  { label: '\u21A9  RETURNING HOME',  bg: '#1a0500', color: '#ff7744' },
    rth_paused: { label: '\u23F8  RTH PAUSED',      bg: '#1a1100', color: '#ffaa00' },
    complete:   { label: '\u2713  COMPLETE',         bg: '#001a00', color: '#00ee55' },
};

function setMissionPhase(phase) {
    if (missionPhase === phase) return;
    console.log('Phase: ' + missionPhase + ' -> ' + phase);
    missionPhase = phase;
    renderMissionUI();
}

function renderMissionUI() {
    const cfg = PHASE_UI[missionPhase] || PHASE_UI.idle;
    const badge = document.getElementById('missionPhaseBadge');
    if (badge) {
        badge.style.background  = cfg.bg;
        badge.style.color       = cfg.color;
        badge.style.borderColor = cfg.color;
    }
    const phaseLabel = document.getElementById('missionPhaseLabel');
    if (phaseLabel) phaseLabel.textContent = cfg.label;
    const show = id => { const e = document.getElementById(id); if (e) e.style.display = 'block'; };
    const hide = id => { const e = document.getElementById(id); if (e) e.style.display = 'none';  };
    ['btnStartMission','btnResumeMission','btnHoldMission','btnRTH','btnAbortMission'].forEach(hide);
    switch (missionPhase) {
        case 'uploaded':
            show('btnStartMission');
            break;
        case 'running':
            show('btnHoldMission');
            show('btnRTH');
            break;
        case 'paused': {
            const rb = document.getElementById('btnResumeMission');
            if (rb) rb.textContent = 'RESUME MISSION';
            show('btnResumeMission'); show('btnRTH'); show('btnAbortMission');
            break;
        }
        case 'returning':
            show('btnHoldMission'); show('btnAbortMission');
            break;
        case 'rth_paused': {
            const rb = document.getElementById('btnResumeMission');
            if (rb) rb.textContent = 'CONTINUE RETURN HOME';
            show('btnResumeMission'); show('btnAbortMission');
            break;
        }
        // idle, complete: no action buttons
    }
}

// =====================
// ACTIONS
// =====================
function wsReady() {
    if (missionWS && missionWS.readyState === WebSocket.OPEN) return true;
    setMissionStatus('Not connected to Jetson.', true);
    return false;
}

function cmdStartMission() {
    if (!wsReady()) return;
    const n = waypoints.length;
    if (!confirm(
        'START AUTONOMOUS MISSION\n\n' +
        n + ' waypoint' + (n !== 1 ? 's' : '') + ', then Return to Home\n\n' +
        'Vehicle will ARM and navigate automatically.\n' +
        'Confirm the area is clear before proceeding.'
    )) return;
    missionWS.send(JSON.stringify({ action: 'go' }));
    setMissionStatus('Arming and starting mission...');
    modeUpdateSuppressUntil = Date.now() + 6000;
    setMissionPhase('running');
    setTimeout(() => {
        if (missionPhase === 'running' && lastKnownMode !== 'AUTO') {
            setMissionStatus('Mode did not switch to AUTO — check Pixhawk status above.', true);
            setMissionPhase('uploaded');
        }
    }, 8000);
}

function cmdHold() {
    if (!wsReady()) return;
    missionWS.send(JSON.stringify({ action: 'hold' }));
    setMissionStatus('HOLD sent.');
    modeUpdateSuppressUntil = Date.now() + 3000;
    setMissionPhase(missionPhase === 'returning' ? 'rth_paused' : 'paused');
}

function cmdResume() {
    if (!wsReady()) return;
    if (missionPhase === 'rth_paused') {
        if (!confirm('Resume return to home?')) return;
        missionWS.send(JSON.stringify({ action: 'rth' }));
        setMissionStatus('Resuming return to home...');
        setMissionPhase('returning');
    } else {
        if (!confirm('Resume mission from current position?')) return;
        missionWS.send(JSON.stringify({ action: 'resume' }));
        setMissionStatus('Resuming mission...');
        setMissionPhase('running');
    }
    modeUpdateSuppressUntil = Date.now() + 5000;
}

function cmdRTH() {
    if (!wsReady()) return;
    missionWS.send(JSON.stringify({ action: 'rth' }));
    setMissionStatus('Returning to home...');
    modeUpdateSuppressUntil = Date.now() + 5000;
    setMissionPhase('returning');
}

function cmdAbort() {
    if (!wsReady()) return;
    if (!confirm('ABORT MISSION?\n\nVehicle will DISARM immediately.\nMotor will stop.')) return;
    missionWS.send(JSON.stringify({ action: 'abort' }));
    setMissionStatus('ABORTED — disarming.', true);
    modeUpdateSuppressUntil = Date.now() + 3000;
    setMissionPhase('idle');
}

function uploadMission() {
    if (!wsReady()) return;
    if (waypoints.length === 0) { setMissionStatus('No waypoints placed.', true); return; }
    if (['running','paused','returning','rth_paused'].includes(missionPhase)) {
        if (!confirm(
            'A mission is currently active.\n\n' +
            'Upload will not affect the running mission.\n' +
            'You must end the current mission first, then press START MISSION.\n\nContinue?'
        )) return;
    }
    setMissionStatus('Uploading ' + waypoints.length + ' waypoints...');
    missionWS.send(JSON.stringify({ action: 'upload_mission', waypoints }));
}

// =====================
// MAP POSITION OVERRIDE
// Filters GPS jitter (<3 m) and glitches (>100 m).
// Suppresses auto-pan during waypoint placement.
// =====================
function haversineMeters(lat1, lon1, lat2, lon2) {
    const R = 6371000;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat/2)**2 + Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*Math.sin(dLon/2)**2;
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}

const _origUpdateMapPos = window.updateMapPosition;
window.updateMapPosition = function(lat, lon, hdg) {
    if (typeof mapReady !== 'undefined' && !mapReady) {
        if (_origUpdateMapPos) _origUpdateMapPos(lat, lon, hdg);
        _lastDroneLat = lat; _lastDroneLon = lon;
        if (typeof mapReady !== 'undefined' && mapReady) restoreWaypointsFromStorage();
        return;
    }
    if (typeof droneMarker !== 'undefined' && droneMarker) droneMarker.setLatLng([lat, lon]);
    const arrow = document.getElementById('droneArrow');
    if (arrow) arrow.style.transform = 'rotate(' + hdg + 'deg)';
    if (!waypointMode && typeof map !== 'undefined' && map) {
        if (_lastDroneLat === null) {
            map.panTo([lat, lon]);
        } else {
            const dist = haversineMeters(_lastDroneLat, _lastDroneLon, lat, lon);
            if (dist > 3 && dist < 100) map.panTo([lat, lon]);
        }
    }
    _lastDroneLat = lat; _lastDroneLon = lon;
};

// =====================
// WAYPOINT PERSISTENCE
// =====================
function saveWaypointsToStorage() {
    try { localStorage.setItem('aquabot_waypoints', JSON.stringify(waypoints)); } catch {}
}

function restoreWaypointsFromStorage() {
    if (waypointsRestored) return;
    waypointsRestored = true;
    try {
        const saved = localStorage.getItem('aquabot_waypoints');
        if (!saved) return;
        const pts = JSON.parse(saved);
        if (!Array.isArray(pts) || pts.length === 0) return;
        pts.forEach(pt => addWaypoint(pt[0], pt[1]));
        setMissionStatus(pts.length + ' waypoint(s) restored.');
    } catch {}
}

function ensureMapReady() {
    if (typeof map !== 'undefined' && map !== null) return;
    let initLat = 32.2319, initLon = -110.9501;
    if (typeof lastTelemetry !== 'undefined' && lastTelemetry && parseFloat(lastTelemetry.LAT) !== 0) {
        initLat = parseFloat(lastTelemetry.LAT);
        initLon = parseFloat(lastTelemetry.LON);
    }
    if (typeof initializeMap === 'function') initializeMap(initLat, initLon);
}

function ensureClickHandler() {
    if (mapClickAttached) return;
    if (typeof map === 'undefined' || map === null) return;
    map.on('click', e => { if (waypointMode) addWaypoint(e.latlng.lat, e.latlng.lng); });
    mapClickAttached = true;
}

function waitForMapInit() {
    if (typeof map !== 'undefined' && map !== null) { ensureClickHandler(); restoreWaypointsFromStorage(); }
    else setTimeout(waitForMapInit, 500);
}
waitForMapInit();

// =====================
// WAYPOINT PLACEMENT
// =====================
function toggleWaypointMode() {
    if (!waypointMode && ['running','paused','returning','rth_paused'].includes(missionPhase)) {
        if (!confirm(
            'A mission is active.\n\nEditing waypoints does not affect the running mission.\n' +
            'You would need to re-upload and restart to use new waypoints.\n\nContinue?'
        )) return;
    }
    waypointMode = !waypointMode;
    const btn   = document.getElementById('btnPlaceWaypoints');
    const mapEl = document.getElementById('map');
    if (waypointMode) {
        ensureMapReady(); ensureClickHandler();
        if (btn)   { btn.textContent = 'Stop Placing'; btn.style.backgroundColor = '#cc5500'; }
        if (mapEl) mapEl.style.cursor = 'crosshair';
        setMissionStatus('Click map to place waypoints.');
    } else {
        if (btn)   { btn.textContent = 'Place Waypoints'; btn.style.backgroundColor = ''; }
        if (mapEl) mapEl.style.cursor = '';
        setMissionStatus(waypoints.length + ' waypoint(s) ready.');
    }
}

function clearWaypoints() {
    waypointMarkers.forEach(m => { if (typeof map !== 'undefined' && map) map.removeLayer(m); });
    waypointMarkers = []; waypoints = [];
    saveWaypointsToStorage();
    if (missionPhase === 'uploaded' || missionPhase === 'idle') setMissionPhase('idle');
    setMissionStatus('Waypoints cleared.');
}

function addWaypoint(lat, lng) {
    const idx = waypoints.length + 1;
    const icon = L.divIcon({
        html: '<div style="background:#ff6600;color:white;width:26px;height:26px;border-radius:50%;' +
              'display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:13px;' +
              'border:2px solid white;box-shadow:0 2px 6px rgba(0,0,0,0.6);">' + idx + '</div>',
        className: '', iconSize: [26, 26], iconAnchor: [13, 13]
    });
    const marker = L.marker([lat, lng], { icon }).addTo(map);
    marker.bindPopup('WP' + idx + ': ' + lat.toFixed(6) + ', ' + lng.toFixed(6));
    waypointMarkers.push(marker);
    waypoints.push([lat, lng]);
    saveWaypointsToStorage();
    setMissionStatus(waypoints.length + ' waypoint(s) placed.');
}

// =====================
// ARM / DISARM
// =====================
let lastArmedState = false;

function toggleArmDisarm() {
    if (!lastArmedState) {
        if (typeof sendArm === 'function') sendArm();
        setMissionStatus('ARM command sent...');
    } else {
        if (typeof sendDisarm === 'function') sendDisarm();
        setMissionStatus('DISARM command sent...');
    }
}

function updateArmButton(armed) {
    const btn = document.getElementById('btnArmDisarm');
    if (!btn) return;
    lastArmedState  = armed;
    btn.textContent = armed ? 'DISARM' : 'ARM';
    btn.classList.toggle('armed', armed);
    btn.style.backgroundColor = '';  // let CSS take over
}

// =====================
// SLOW MODE
// Caps Pixhawk MOT_THR_MAX at 30% (server-side). Button reflects telemetry.
// =====================
let slowModeState = false;

function toggleSlowMode() {
    if (!wsReady()) return;
    const next = !slowModeState;
    missionWS.send(JSON.stringify({ action: 'slow_mode', enabled: next }));
    setMissionStatus(next ? 'Enabling slow mode (30% cap)...' : 'Disabling slow mode...');
}

function updateSlowModeButton(enabled) {
    const btn = document.getElementById('btnSlowMode');
    if (!btn) return;
    slowModeState   = enabled;
    btn.textContent = enabled ? 'SLOW MODE: ON (30%)' : 'SLOW MODE: OFF';
    btn.classList.toggle('on', enabled);
    btn.style.backgroundColor = '';
}

// =====================
// TELEMETRY PATCH
// Drives ARM button, mode display, WP progress, Pixhawk alerts,
// and the phase state machine from live vehicle telemetry.
// =====================
const _origUpdateTelemetryUI = window.updateTelemetryUI;
window.updateTelemetryUI = function(t) {
    if (_origUpdateTelemetryUI) _origUpdateTelemetryUI(t);

    updateArmButton(!!t.ARMED);
    if (typeof t.SLOW_MODE === 'boolean') updateSlowModeButton(t.SLOW_MODE);

    const modeEl = document.getElementById('currentMode');
    if (modeEl && t.MODE) modeEl.textContent = t.MODE;
    if (t.MODE) lastKnownMode = t.MODE;

    // Waypoint progress label
    if (typeof t.CURRENT_WP === 'number') {
        const wpEl = document.getElementById('missionWPProgress');
        if (wpEl) {
            const total = waypoints.length;
            const active = ['running','paused'].includes(missionPhase);
            wpEl.textContent = (active && total > 0)
                ? 'Waypoint ' + (t.CURRENT_WP + 1) + ' of ' + total
                : '';
        }
    }

    // Show Pixhawk WARNING/ERROR messages (severity <= 4; INFO/DEBUG filtered)
    if (t.STATUS && typeof t.STATUS_SEV === 'number' && t.STATUS_SEV <= 4) {
        setMissionStatus('Pixhawk: ' + t.STATUS, t.STATUS_SEV <= 3);
    }

    // Phase state machine — suppressed briefly after each button press to prevent flicker.
    // Disarmed is terminal: if the vehicle isn't armed, no mission is active, regardless
    // of what mode Pixhawk reports. This prevents the GUI from latching into 'returning'
    // when the boat finishes RTL but Pixhawk leaves the mode at RTL.
    if (t.MODE && Date.now() > modeUpdateSuppressUntil) {
        const m     = t.MODE;
        const armed = !!t.ARMED;
        if (!armed) {
            if (['running','paused','returning','rth_paused'].includes(missionPhase)) {
                setMissionPhase('complete');
                setMissionStatus('Mission complete. Vehicle disarmed.');
            }
        } else if (m === 'AUTO') {
            if (missionPhase !== 'running') setMissionPhase('running');
        } else if (m === 'HOLD' || m === 'LOITER') {
            if      (missionPhase === 'running')   setMissionPhase('paused');
            else if (missionPhase === 'returning') setMissionPhase('rth_paused');
        } else if (m === 'RTL' || m === 'SMART_RTL') {
            if (missionPhase !== 'returning') setMissionPhase('returning');
        }
    }
};

// =====================
// BUTTON WIRING
// =====================
document.getElementById('btnPlaceWaypoints') ?.addEventListener('click', toggleWaypointMode);
document.getElementById('btnClearWaypoints') ?.addEventListener('click', clearWaypoints);
document.getElementById('btnUploadMission')  ?.addEventListener('click', uploadMission);
document.getElementById('btnStartMission')   ?.addEventListener('click', cmdStartMission);
document.getElementById('btnResumeMission')  ?.addEventListener('click', cmdResume);
document.getElementById('btnHoldMission')    ?.addEventListener('click', cmdHold);
document.getElementById('btnRTH')            ?.addEventListener('click', cmdRTH);
document.getElementById('btnAbortMission')   ?.addEventListener('click', cmdAbort);
