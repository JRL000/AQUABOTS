// ======================================================
// ADVANCED MISSION PLANNING (Phases D1 + D2)
//
// - Geofence: draw polygon on map, upload to Pixhawk via FENCE_POINT,
//   enable/disable, clear. Client-side breach warning while waiting for
//   Pixhawk-side action.
// - Survey: draw polygon, auto-generate lawnmower waypoints at a given
//   line spacing (meters). Waypoints flow straight into the existing
//   waypoint list so the user can Upload like a normal mission.
// - Mission templates: save/load named waypoint sets from localStorage.
// ======================================================

// =====================
// EXCLUSIVE PLACING MODE
// =====================
// Only one placement mode is active at a time so map clicks don't get added
// to multiple lists. waypointMode is set by controls.js — we coordinate here.
let fencePolygon   = [];
let surveyPolygon  = [];
let fenceMarkers   = [];
let surveyMarkers  = [];
let fenceLeafletPoly   = null;
let surveyLeafletPoly  = null;
let fenceMode  = false;
let surveyMode = false;
let fenceBreached = false;

function log(...args) { console.log('[planning]', ...args); }

function _turnOffWaypoint() {
    if (typeof waypointMode !== 'undefined' && waypointMode) {
        // Ask controls.js to toggle waypoint mode off so its button state resets cleanly.
        if (typeof toggleWaypointMode === 'function') toggleWaypointMode();
    }
}

function setFenceMode(on) {
    fenceMode = !!on;
    const btn = document.getElementById('btnFenceDraw');
    const mapEl = document.getElementById('map');
    if (btn) btn.textContent = fenceMode ? 'Stop fence draw' : 'Draw fence';
    if (btn) btn.style.backgroundColor = fenceMode ? '#cc5500' : '';
    if (mapEl) mapEl.style.cursor = (fenceMode || surveyMode || (typeof waypointMode !== 'undefined' && waypointMode)) ? 'crosshair' : '';
    if (fenceMode) { surveyMode = false; _turnOffWaypoint(); updateSurveyBtn(); }
}
function setSurveyMode(on) {
    surveyMode = !!on;
    updateSurveyBtn();
    const mapEl = document.getElementById('map');
    if (mapEl) mapEl.style.cursor = (fenceMode || surveyMode || (typeof waypointMode !== 'undefined' && waypointMode)) ? 'crosshair' : '';
    if (surveyMode) { fenceMode = false; setFenceMode(false); _turnOffWaypoint(); }
}
function updateSurveyBtn() {
    const btn = document.getElementById('btnSurveyDraw');
    if (!btn) return;
    btn.textContent = surveyMode ? 'Stop area draw' : 'Draw area';
    btn.style.backgroundColor = surveyMode ? '#cc5500' : '';
}

// =====================
// MAP CLICK HANDLER
// =====================
function attachPlanningClicks() {
    if (typeof map === 'undefined' || !map) { setTimeout(attachPlanningClicks, 500); return; }
    map.on('click', e => {
        if (fenceMode)  addFenceVertex(e.latlng.lat, e.latlng.lng);
        if (surveyMode) addSurveyVertex(e.latlng.lat, e.latlng.lng);
    });
    // Double-click closes the active polygon.
    map.on('dblclick', () => {
        if (fenceMode)  { setFenceMode(false);  redrawFence();  }
        if (surveyMode) { setSurveyMode(false); redrawSurvey(); }
    });
}
attachPlanningClicks();

// =====================
// FENCE POLYGON
// =====================
function addFenceVertex(lat, lng) {
    const idx = fencePolygon.length + 1;
    const icon = L.divIcon({
        html: `<div style="background:#d4a300;color:#000;width:22px;height:22px;border-radius:4px;
                  display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:12px;
                  border:2px solid white;">${idx}</div>`,
        className: '', iconSize: [22, 22], iconAnchor: [11, 11],
    });
    const m = L.marker([lat, lng], { icon }).addTo(map);
    m.bindPopup(`Fence v${idx}: ${lat.toFixed(6)}, ${lng.toFixed(6)}`);
    fenceMarkers.push(m);
    fencePolygon.push([lat, lng]);
    redrawFence();
}
function redrawFence() {
    if (fenceLeafletPoly) { map.removeLayer(fenceLeafletPoly); fenceLeafletPoly = null; }
    if (fencePolygon.length >= 2) {
        fenceLeafletPoly = L.polygon(fencePolygon, {
            color: '#d4a300', weight: 2, fillColor: '#d4a300', fillOpacity: 0.08, dashArray: '6,4'
        }).addTo(map);
    }
}
function clearFence() {
    fenceMarkers.forEach(m => map.removeLayer(m));
    fenceMarkers = []; fencePolygon = [];
    if (fenceLeafletPoly) { map.removeLayer(fenceLeafletPoly); fenceLeafletPoly = null; }
    fenceBreached = false;
    if (window.aquaToast) window.aquaToast('Fence cleared');
}
function uploadFence() {
    if (fencePolygon.length < 3) {
        if (window.aquaToast) window.aquaToast('Need at least 3 fence vertices', 'error');
        return;
    }
    if (typeof missionWS === 'undefined' || !missionWS || missionWS.readyState !== WebSocket.OPEN) {
        if (window.aquaToast) window.aquaToast('Not connected to Jetson', 'error');
        return;
    }
    // Return point defaults to current vehicle position if known.
    const t = window.lastTelemetry;
    const rlat = t ? parseFloat(t.LAT) : fencePolygon[0][0];
    const rlon = t ? parseFloat(t.LON) : fencePolygon[0][1];
    missionWS.send(JSON.stringify({
        action: 'upload_fence',
        polygon: fencePolygon,
        return_lat: rlat,
        return_lon: rlon,
        fence_action: 'HOLD',
    }));
    if (window.aquaToast) window.aquaToast(`Uploading fence (${fencePolygon.length} vertices)...`);
}

let fenceEnabledLocal = false;
function toggleFenceEnable() {
    if (typeof missionWS === 'undefined' || !missionWS || missionWS.readyState !== WebSocket.OPEN) {
        if (window.aquaToast) window.aquaToast('Not connected to Jetson', 'error'); return;
    }
    fenceEnabledLocal = !fenceEnabledLocal;
    missionWS.send(JSON.stringify({ action: 'fence_enable', enabled: fenceEnabledLocal }));
    const btn = document.getElementById('btnFenceToggle');
    if (btn) btn.textContent = fenceEnabledLocal ? 'Disable fence' : 'Enable fence';
}

document.getElementById('btnFenceDraw')?.addEventListener('click',   () => setFenceMode(!fenceMode));
document.getElementById('btnFenceClear')?.addEventListener('click',  clearFence);
document.getElementById('btnFenceUpload')?.addEventListener('click', uploadFence);
document.getElementById('btnFenceToggle')?.addEventListener('click', toggleFenceEnable);

// =====================
// CLIENT-SIDE BREACH CHECK (extra belt)
// =====================
function pointInPoly(lat, lng, poly) {
    // Ray-cast; returns true if inside. Works on lat/lng as a flat plane —
    // fine for geofences at the scales this vehicle operates at (<1 km).
    let inside = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
        const xi = poly[i][1], yi = poly[i][0];
        const xj = poly[j][1], yj = poly[j][0];
        const intersect = ((yi > lat) !== (yj > lat)) &&
            (lng < (xj - xi) * (lat - yi) / ((yj - yi) || 1e-12) + xi);
        if (intersect) inside = !inside;
    }
    return inside;
}

function checkFenceBreach(t) {
    if (fencePolygon.length < 3) return;
    const lat = parseFloat(t.LAT), lon = parseFloat(t.LON);
    if (!lat || !lon) return;
    const inside = pointInPoly(lat, lon, fencePolygon);
    if (!inside && !fenceBreached) {
        fenceBreached = true;
        if (window.aquaToast) window.aquaToast('FENCE BREACH — vehicle outside fence', 'error');
        if (window.aquaBeep) window.aquaBeep('failsafe');
        // Backup client-side HOLD — Pixhawk fence action is primary.
        if (typeof missionWS !== 'undefined' && missionWS && missionWS.readyState === WebSocket.OPEN) {
            missionWS.send(JSON.stringify({ action: 'hold' }));
        }
    } else if (inside && fenceBreached) {
        fenceBreached = false;
        if (window.aquaToast) window.aquaToast('Back inside fence', 'warn');
    }
}

// =====================
// SURVEY POLYGON + LAWNMOWER
// =====================
function addSurveyVertex(lat, lng) {
    const idx = surveyPolygon.length + 1;
    const icon = L.divIcon({
        html: `<div style="background:#4499ff;color:white;width:22px;height:22px;border-radius:50%;
                  display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:12px;
                  border:2px solid white;">${idx}</div>`,
        className: '', iconSize: [22, 22], iconAnchor: [11, 11],
    });
    const m = L.marker([lat, lng], { icon }).addTo(map);
    surveyMarkers.push(m);
    surveyPolygon.push([lat, lng]);
    redrawSurvey();
}
function redrawSurvey() {
    if (surveyLeafletPoly) { map.removeLayer(surveyLeafletPoly); surveyLeafletPoly = null; }
    if (surveyPolygon.length >= 2) {
        surveyLeafletPoly = L.polygon(surveyPolygon, {
            color: '#4499ff', weight: 2, fillColor: '#4499ff', fillOpacity: 0.08
        }).addTo(map);
    }
}
function clearSurvey() {
    surveyMarkers.forEach(m => map.removeLayer(m));
    surveyMarkers = []; surveyPolygon = [];
    if (surveyLeafletPoly) { map.removeLayer(surveyLeafletPoly); surveyLeafletPoly = null; }
}

/**
 * Generate lawnmower waypoints for the current surveyPolygon.
 * Strategy: axis-aligned (east-west) tracks spaced `spacingM` meters apart,
 * clipped to the polygon via a latitude-sweep intersection test. Tracks
 * alternate direction (boustrophedon) so the vehicle doesn't fly back to
 * the start of each line.
 */
function generateLawnmower(polygon, spacingM) {
    if (polygon.length < 3) return [];
    const lats = polygon.map(p => p[0]);
    const lons = polygon.map(p => p[1]);
    const minLat = Math.min(...lats), maxLat = Math.max(...lats);
    // Convert meter spacing to degrees latitude (~111,320 m per deg lat).
    const dLat = spacingM / 111320;

    const tracks = [];
    let goingEast = true;
    for (let lat = minLat + dLat/2; lat < maxLat; lat += dLat) {
        // Find all edge intersections with the horizontal line y = lat.
        const xs = [];
        for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
            const [y1, x1] = polygon[i], [y2, x2] = polygon[j];
            if ((y1 > lat) !== (y2 > lat)) {
                const t = (lat - y1) / ((y2 - y1) || 1e-12);
                xs.push(x1 + t * (x2 - x1));
            }
        }
        xs.sort((a, b) => a - b);
        // Take pairs of intersections: [enter, exit] segments inside the polygon.
        for (let k = 0; k + 1 < xs.length; k += 2) {
            const a = [lat, xs[k]], b = [lat, xs[k+1]];
            tracks.push(goingEast ? [a, b] : [b, a]);
            goingEast = !goingEast;
        }
    }
    // Flatten tracks into a single waypoint list.
    const wps = [];
    tracks.forEach(seg => { wps.push(seg[0]); wps.push(seg[1]); });
    return wps;
}

function generateSurveyWaypoints() {
    if (surveyPolygon.length < 3) {
        if (window.aquaToast) window.aquaToast('Draw a survey area first (3+ points)', 'error');
        return;
    }
    const spacing = Math.max(2, parseInt(document.getElementById('surveySpacing').value, 10) || 8);
    const wps = generateLawnmower(surveyPolygon, spacing);
    if (wps.length === 0) {
        if (window.aquaToast) window.aquaToast('Could not generate waypoints — check area shape', 'error');
        return;
    }
    // Push into the main waypoints list (owned by controls.js) and redraw.
    if (typeof clearWaypoints === 'function') clearWaypoints();
    wps.forEach(w => { if (typeof addWaypoint === 'function') addWaypoint(w[0], w[1]); });
    if (window.aquaToast) window.aquaToast(`Generated ${wps.length} survey waypoints (${spacing} m spacing)`);
}

document.getElementById('btnSurveyDraw')?.addEventListener('click', () => setSurveyMode(!surveyMode));
document.getElementById('btnSurveyGen')?.addEventListener('click', generateSurveyWaypoints);

// =====================
// MISSION TEMPLATES
// =====================
const TMPL_KEY = 'aquabot_mission_templates';

function loadTemplates() {
    try { return JSON.parse(localStorage.getItem(TMPL_KEY) || '{}'); }
    catch { return {}; }
}
function saveTemplates(obj) {
    try { localStorage.setItem(TMPL_KEY, JSON.stringify(obj)); } catch {}
}
function refreshTmplList() {
    const sel = document.getElementById('tmplList');
    if (!sel) return;
    const t = loadTemplates();
    sel.innerHTML = '<option value="">(templates)</option>' +
        Object.keys(t).sort().map(k => `<option value="${k}">${k} (${t[k].length})</option>`).join('');
}
refreshTmplList();

document.getElementById('btnTmplSave')?.addEventListener('click', () => {
    if (typeof waypoints === 'undefined' || waypoints.length === 0) {
        if (window.aquaToast) window.aquaToast('Nothing to save — place waypoints first', 'error'); return;
    }
    const name = prompt('Template name:');
    if (!name) return;
    const t = loadTemplates();
    t[name] = JSON.parse(JSON.stringify(waypoints));
    saveTemplates(t);
    refreshTmplList();
    if (window.aquaToast) window.aquaToast(`Template "${name}" saved (${t[name].length} waypoints)`);
});

document.getElementById('btnTmplLoad')?.addEventListener('click', () => {
    const sel = document.getElementById('tmplList');
    const name = sel && sel.value;
    if (!name) return;
    const t = loadTemplates();
    const pts = t[name];
    if (!pts) return;
    if (typeof clearWaypoints === 'function') clearWaypoints();
    pts.forEach(p => { if (typeof addWaypoint === 'function') addWaypoint(p[0], p[1]); });
    if (window.aquaToast) window.aquaToast(`Loaded "${name}" (${pts.length} waypoints)`);
});

document.getElementById('btnTmplDelete')?.addEventListener('click', () => {
    const sel = document.getElementById('tmplList');
    const name = sel && sel.value;
    if (!name) return;
    if (!confirm(`Delete template "${name}"?`)) return;
    const t = loadTemplates();
    delete t[name];
    saveTemplates(t);
    refreshTmplList();
});

// =====================
// WIRE BREACH CHECK INTO TELEMETRY PIPELINE
// =====================
const _prev_planningUpdate = window.updateTelemetryUI;
window.updateTelemetryUI = function(t) {
    if (_prev_planningUpdate) _prev_planningUpdate(t);
    try { checkFenceBreach(t); } catch (e) { console.warn('fence check:', e); }
};
