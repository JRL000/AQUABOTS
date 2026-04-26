// ======================================================
// SWARM OVERLAY + CONTROL PANEL
// ======================================================
// Renders on top of the existing Leaflet map (map). Reads the
// SWARM block from the 1 Hz telemetry broadcast and shows:
//   - leader crown marker at the formation center (leader GPS)
//   - ghost icon at THIS boat's assigned formation slot
//   - dashed line from this boat's real position to its assigned slot
// Plus a floating control panel for pattern + spacing + Start/Exit, and
// a bottom status strip with role / distance-to-station / link health.
//
// All Start/Exit and pattern changes go through the admin-gated control
// websocket (reuses the existing controlWS + admin token in window.adminToken).
// ======================================================

(function () {
    "use strict";

    let leaderMarker = null;
    let ghostMarker = null;
    let stationLine = null;
    let simBoatMarkers = [];   // markers for OTHER simulated boats in mock mode
    let lastSwarm = null;
    let lastTelemetry = null;
    let lastBoatLat = null, lastBoatLon = null;
    // After clicking a pattern button we "pin" the user's choice for a few
    // seconds so the still-stale telemetry tick doesn't visually un-press it.
    let pendingPattern = null;
    let pendingPatternUntil = 0;

    // ----- Leaflet icons --------------------------------------------------

    function leaderIcon() {
        return L.divIcon({
            html: `<div style="
                font-size:32px;
                line-height:32px;
                text-shadow: 0 0 4px #000, 0 0 4px #000;
                color:#ffd95a;
                user-select:none;
                ">&#9819;</div>`, // unicode chess king
            className: '',
            iconSize: [32, 32],
            iconAnchor: [16, 16],
        });
    }

    function ghostIcon() {
        return L.divIcon({
            html: `<div style="
                width:0;height:0;
                border-left:10px solid transparent;
                border-right:10px solid transparent;
                border-bottom:36px solid rgba(120, 200, 255, 0.45);
                filter: drop-shadow(0 0 3px rgba(0,0,0,0.6));
                "></div>`,
            className: '',
            iconSize: [22, 36],
            iconAnchor: [11, 27],
        });
    }

    // Smaller, dimmer arrow used for OTHER boats in a simulated swarm —
    // makes a 50-boat formation legible without flooding the view.
    function simBoatIcon() {
        return L.divIcon({
            html: `<div style="
                width:0;height:0;
                border-left:6px solid transparent;
                border-right:6px solid transparent;
                border-bottom:20px solid rgba(255, 255, 255, 0.32);
                filter: drop-shadow(0 0 2px rgba(0,0,0,0.6));
                "></div>`,
            className: '',
            iconSize: [12, 20],
            iconAnchor: [6, 15],
        });
    }

    // ----- Formation math (mirror of firmware/main/formation.c calculators
    //       and jetson/swarm_coordinator.py:offset_to_latlon) -------------

    function calcOffset(pattern, idx, total, spacing) {
        if (pattern === 'line')
            return [0, -idx * spacing, 0];
        if (pattern === 'wedge') {
            if (idx === 0) return [0, 0, 0];
            const row  = (idx + 1) >> 1;
            const left = (idx % 2 === 1);
            const x    = (row * spacing) >> 1;
            return [(left ? -x : x), -row * spacing, 0];
        }
        if (pattern === 'column') {
            const row = idx >> 1;
            const col = idx % 2;
            return [(col === 0 ? -spacing/2 : spacing/2), -row * spacing, 0];
        }
        if (pattern === 'circle') {
            if (total <= 1 || idx === 0) return [0, 0, 0];
            const onCircle = total - 1;
            const radius = Math.max(spacing, (onCircle * spacing) / 6);
            const a = (idx - 1) * 2 * Math.PI / onCircle;
            return [Math.round(radius * Math.sin(a)), Math.round(radius * Math.cos(a)),
                    Math.round(a * 180 / Math.PI)];
        }
        return [0, 0, 0];
    }

    function offsetToLatLon(lat0, lon0, headingDeg, xMm, yMm) {
        const h = headingDeg * Math.PI / 180;
        const northM = (yMm * Math.cos(h) - xMm * Math.sin(h)) / 1000;
        const eastM  = (yMm * Math.sin(h) + xMm * Math.cos(h)) / 1000;
        return [
            lat0 + northM / 111111,
            lon0 + eastM  / (111111 * Math.cos(lat0 * Math.PI / 180)),
        ];
    }

    // ----- Map overlay updates -------------------------------------------

    function ensureLayers() {
        if (typeof map === 'undefined' || !map) return false;
        return true;
    }

    function updateOverlay(swarm, telemetry) {
        if (!ensureLayers()) return;

        // Leader marker (crown at the formation center)
        const leaderGps = swarm.leader_gps;
        if (leaderGps) {
            const [lat, lon] = leaderGps;
            if (leaderMarker) leaderMarker.setLatLng([lat, lon]);
            else leaderMarker = L.marker([lat, lon], { icon: leaderIcon() }).addTo(map);
        } else if (leaderMarker) {
            map.removeLayer(leaderMarker); leaderMarker = null;
        }

        // Ghost (this boat's assigned slot, if follower)
        const tgt = swarm.target_latlon;
        if (tgt && swarm.role === 'follower') {
            const [lat, lon] = tgt;
            if (ghostMarker) ghostMarker.setLatLng([lat, lon]);
            else ghostMarker = L.marker([lat, lon], { icon: ghostIcon() }).addTo(map);
            if (lastBoatLat !== null && lastBoatLon !== null) {
                const pts = [[lastBoatLat, lastBoatLon], [lat, lon]];
                if (stationLine) stationLine.setLatLngs(pts);
                else stationLine = L.polyline(pts, {
                    color: '#7ad6ff', weight: 2, dashArray: '6,6', opacity: 0.85,
                }).addTo(map);
            }
        } else {
            if (ghostMarker) { map.removeLayer(ghostMarker); ghostMarker = null; }
            if (stationLine) { map.removeLayer(stationLine); stationLine = null; }
        }

        // Other simulated boats — only meaningful in mock mode where the
        // server tells us how many simulated boats exist. Render small
        // dimmer arrows at each one's assigned formation slot so a 50-boat
        // swarm visualisation looks like a swarm.
        const showSim = telemetry && telemetry.MOCK_MODE
                        && swarm.member_count > 1
                        && swarm.leader_gps
                        && swarm.pattern && swarm.pattern !== 'none'
                        && swarm.spacing_mm;
        if (showSim) {
            const [lat0, lon0, hLead] = swarm.leader_gps;
            const total = swarm.member_count;
            const myIdx = swarm.my_index;
            // Build the desired set first (so we can resize without flicker).
            for (let i = 0; i < total; i++) {
                if (i === 0 || i === myIdx) continue;  // leader has crown, mine has ghost
                const [x, y] = calcOffset(swarm.pattern, i, total, swarm.spacing_mm);
                const [lat, lon] = offsetToLatLon(lat0, lon0, hLead, x, y);
                if (simBoatMarkers[i]) {
                    simBoatMarkers[i].setLatLng([lat, lon]);
                } else {
                    simBoatMarkers[i] = L.marker([lat, lon], { icon: simBoatIcon() }).addTo(map);
                }
            }
            // Trim if size shrank
            for (let i = 0; i < simBoatMarkers.length; i++) {
                if (simBoatMarkers[i] && (i >= total || i === 0 || i === myIdx)) {
                    map.removeLayer(simBoatMarkers[i]);
                    simBoatMarkers[i] = null;
                }
            }
        } else {
            simBoatMarkers.forEach(m => { if (m) map.removeLayer(m); });
            simBoatMarkers = [];
        }
    }

    // ----- Distance helper -----------------------------------------------

    function haversineM(la1, lo1, la2, lo2) {
        const R = 6371000;
        const p1 = la1 * Math.PI / 180;
        const p2 = la2 * Math.PI / 180;
        const dp = (la2 - la1) * Math.PI / 180;
        const dl = (lo2 - lo1) * Math.PI / 180;
        const a = Math.sin(dp/2)**2 + Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)**2;
        return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
    }

    // ----- Floating control panel + status strip -------------------------

    function panelHTML() {
        return `
        <div id="swarmPanel" class="swarm-panel">
            <div class="swarm-panel-head">
                <span>Swarm</span>
                <button id="swarmCollapseBtn" title="Collapse">&minus;</button>
            </div>
            <div class="swarm-panel-body">
                <div class="swarm-row">
                    <label>Pattern</label>
                    <div class="swarm-pattern-grid">
                        <button data-pat="line"   class="swarm-pat-btn">Line</button>
                        <button data-pat="wedge"  class="swarm-pat-btn">Wedge</button>
                        <button data-pat="circle" class="swarm-pat-btn">Circle</button>
                        <button data-pat="column" class="swarm-pat-btn">Column</button>
                    </div>
                </div>
                <div class="swarm-row">
                    <label>Spacing <span id="swarmSpacingLabel">2.0</span> m</label>
                    <input id="swarmSpacing" type="range" min="500" max="10000" step="500" value="2000">
                </div>
                <div class="swarm-row swarm-status-row">
                    <span id="swarmRoleBadge" class="swarm-badge swarm-badge-unknown">unknown</span>
                    <span id="swarmMembers">members: 0</span>
                </div>
                <div class="swarm-row">
                    <button id="swarmStartBtn" class="swarm-bigbtn">Start Swarm Mode</button>
                </div>
                <div class="swarm-row swarm-event" id="swarmLastEvent">--</div>
                <div class="swarm-row swarm-dev-block" id="swarmDevBlock" style="display:none;">
                    <label>Mock scenario (dev)</label>
                    <select id="swarmMockSelect"></select>
                    <label style="margin-top:8px;">Simulated swarm size: <span id="swarmMockSizeLabel">3</span></label>
                    <input id="swarmMockSize" type="range" min="2" max="50" step="1" value="3">
                </div>
            </div>
        </div>
        <div id="swarmStrip" class="swarm-strip"></div>
        <button id="swarmRecenterBtn" class="swarm-recenter" title="Center map on leader">
            &#10687;
        </button>`;
    }

    function injectPanel() {
        const geo = document.querySelector('.geo-panel');
        if (!geo) { setTimeout(injectPanel, 500); return; }
        if (document.getElementById('swarmPanel')) return;
        const wrap = document.createElement('div');
        wrap.innerHTML = panelHTML();
        // append children to geo-panel so they layer on top of the map
        while (wrap.firstElementChild) geo.appendChild(wrap.firstElementChild);
        wireControls();
    }

    // Try-do-try wrapper: each event listener is independently registered so
    // a single missing element never breaks the entire panel.
    function safeOn(id, evt, fn) {
        const el = document.getElementById(id);
        if (el) el.addEventListener(evt, fn);
    }

    function wireControls() {
        // Spacing slider — live label AND debounced push to the server so the
        // formation actually re-spaces while you drag.
        let spacingDebounce = null;
        safeOn('swarmSpacing', 'input', (e) => {
            const lbl = document.getElementById('swarmSpacingLabel');
            if (lbl) lbl.textContent = (parseInt(e.target.value, 10) / 1000).toFixed(1);
            const spacing = parseInt(e.target.value, 10);
            const currentPattern = (lastSwarm && lastSwarm.pattern) || 'wedge';
            clearTimeout(spacingDebounce);
            spacingDebounce = setTimeout(() => {
                sendCtrl({
                    action: 'swarm_set_pattern',
                    pattern: currentPattern,
                    spacing_mm: spacing,
                });
            }, 250);
        });

        // Pattern buttons — pin the user's choice for 3 s so the still-stale
        // telemetry tick doesn't visually un-press it before the mock catches up.
        document.querySelectorAll('.swarm-pat-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const pat = btn.dataset.pat;
                const slider = document.getElementById('swarmSpacing');
                const spacing = slider ? parseInt(slider.value, 10) : 2000;
                pendingPattern = pat;
                pendingPatternUntil = Date.now() + 3000;
                sendCtrl({
                    action: 'swarm_set_pattern',
                    pattern: pat,
                    spacing_mm: spacing,
                });
                document.querySelectorAll('.swarm-pat-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
            });
        });

        // Start / Exit (admin-gated server-side; we add a friendly toast)
        safeOn('swarmStartBtn', 'click', () => {
            const startBtn = document.getElementById('swarmStartBtn');
            const turningOn = !startBtn.classList.contains('on');
            sendCtrl({
                action: 'swarm_enable',
                on: turningOn,
                token: (typeof adminToken !== 'undefined') ? adminToken : null,
            });
            toast(turningOn
                ? 'Requesting Start Swarm Mode (admin required)'
                : 'Exiting Swarm Mode');
        });

        // Collapse toggle
        safeOn('swarmCollapseBtn', 'click', () => {
            const head = document.querySelector('.swarm-panel-head');
            const body = document.querySelector('.swarm-panel-body');
            if (!head || !body) return;
            const hidden = body.style.display === 'none';
            body.style.display = hidden ? '' : 'none';
            const tog = head.querySelector('button');
            if (tog) tog.textContent = hidden ? '−' : '+';
        });

        // Mock-mode scenario picker (admin-only)
        safeOn('swarmMockSelect', 'change', (e) => {
            sendCtrl({
                action: 'mock_set_scenario',
                scenario: e.target.value,
                token: (typeof adminToken !== 'undefined') ? adminToken : null,
            });
            toast(`Switching mock scenario to ${e.target.value}`);
        });

        // Mock swarm-size slider
        let sizeDebounce = null;
        safeOn('swarmMockSize', 'input', (e) => {
            const sizeLabel = document.getElementById('swarmMockSizeLabel');
            if (sizeLabel) sizeLabel.textContent = e.target.value;
            clearTimeout(sizeDebounce);
            sizeDebounce = setTimeout(() => {
                sendCtrl({
                    action: 'mock_set_members',
                    members: parseInt(e.target.value, 10),
                    token: (typeof adminToken !== 'undefined') ? adminToken : null,
                });
                toast(`Simulating ${e.target.value}-boat swarm`);
            }, 300);
        });

        // Recenter button — fits the entire formation in view if multiple
        // boats exist (so a 50-boat swarm becomes visible at one click), else
        // just centers on the leader at zoom 18.
        safeOn('swarmRecenterBtn', 'click', () => {
            if (!lastSwarm || !lastSwarm.leader_gps || typeof map === 'undefined' || !map) {
                toast('No leader GPS yet');
                return;
            }
            const [lat0, lon0, hLead] = lastSwarm.leader_gps;
            const total = lastSwarm.member_count || 1;
            if (total > 1 && lastSwarm.pattern && lastSwarm.spacing_mm) {
                const pts = [];
                for (let i = 0; i < total; i++) {
                    const [x, y] = calcOffset(lastSwarm.pattern, i, total, lastSwarm.spacing_mm);
                    pts.push(offsetToLatLon(lat0, lon0, hLead, x, y));
                }
                if (lastBoatLat !== null && lastBoatLon !== null) {
                    pts.push([lastBoatLat, lastBoatLon]);
                }
                map.flyToBounds(L.latLngBounds(pts), {
                    padding: [60, 60], maxZoom: 19, duration: 0.6,
                });
            } else {
                map.flyTo([lat0, lon0], 18, { duration: 0.6 });
            }
        });
    }

    function sendCtrl(obj) {
        // Use missionWS (the WS that has an onmessage handler displaying the
        // server's status reply in the missionStatus card). controlWS goes to
        // the same port but its replies aren't read.
        if (typeof missionWS === 'undefined' || !missionWS || missionWS.readyState !== 1) {
            console.warn('[SWARM] missionWS not ready, dropping', obj);
            toast('Control link not ready');
            return;
        }
        missionWS.send(JSON.stringify(obj));
    }

    function toast(text) {
        // Reuse the existing toast region if present, else fall back to console.
        const region = document.getElementById('toastRegion');
        if (!region) { console.log('[SWARM] ' + text); return; }
        const el = document.createElement('div');
        el.className = 'toast';
        el.textContent = text;
        region.appendChild(el);
        setTimeout(() => el.remove(), 3500);
    }

    // ----- Render the panel + strip from a SWARM snapshot ----------------

    function renderPanelState(swarm) {
        const role = swarm.role || 'unknown';
        const badge = document.getElementById('swarmRoleBadge');
        if (badge) {
            badge.textContent = role + (role === 'follower' && swarm.my_index != null
                ? ` of ${swarm.leader_id}` : '');
            badge.className = 'swarm-badge swarm-badge-' + role;
        }

        const members = document.getElementById('swarmMembers');
        if (members) members.textContent = `members: ${swarm.member_count || 0}`;

        const startBtn = document.getElementById('swarmStartBtn');
        if (startBtn) {
            if (swarm.enabled) {
                startBtn.textContent = 'Exit Swarm Mode';
                startBtn.classList.add('on');
            } else {
                startBtn.textContent = 'Start Swarm Mode';
                startBtn.classList.remove('on');
            }
        }

        const evt = document.getElementById('swarmLastEvent');
        if (evt) {
            const events = swarm.events || [];
            const last = events.length ? events[events.length - 1][1] : '';
            evt.textContent = last ? '• ' + last : '';
        }

        // Highlight current pattern button — UNLESS the user just clicked
        // a different one and we're still waiting for the round-trip.
        const honorPending = pendingPattern && Date.now() < pendingPatternUntil;
        if (honorPending && swarm.pattern === pendingPattern) {
            // Server caught up — clear the pin.
            pendingPattern = null;
        }
        const showAs = honorPending ? pendingPattern : swarm.pattern;
        if (showAs) {
            document.querySelectorAll('.swarm-pat-btn').forEach(b => {
                b.classList.toggle('active', b.dataset.pat === showAs);
            });
        }
    }

    function renderStrip(swarm) {
        const strip = document.getElementById('swarmStrip');
        if (!strip) return;
        const rows = [];

        // Row 1: how far am I from my assigned formation slot?
        let distM = null;
        if (swarm.target_latlon && lastBoatLat !== null && lastBoatLon !== null) {
            const [tlat, tlon] = swarm.target_latlon;
            distM = haversineM(lastBoatLat, lastBoatLon, tlat, tlon);
        }
        const role = swarm.role || 'unknown';
        const onStation = (distM !== null && distM < 1.0);
        let distLabel;
        if (role === 'leader')           distLabel = 'You are the formation center';
        else if (distM === null)         distLabel = 'Waiting for assignment';
        else if (onStation)              distLabel = `On station (${distM.toFixed(1)} m off)`;
        else                             distLabel = `${distM.toFixed(1)} m to your assigned spot`;
        rows.push(`
            <div class="swarm-strip-row swarm-self ${onStation ? 'swarm-on-station' : ''}"
                 title="Distance from where this boat is now to where the formation says it should be.">
                <span class="swarm-strip-name">This boat</span>
                <span class="swarm-strip-dist">${distLabel}</span>
            </div>`);

        // Row 2: how recently did we hear from the leader?
        if (swarm.leader_id != null && role !== 'leader') {
            const age = swarm.leader_gps_age_s;
            const stale = (age == null || age > 5);
            const linkLabel = age == null
                ? 'No leader signal yet'
                : `Leader heard ${age.toFixed(1)} s ago`;
            rows.push(`
                <div class="swarm-strip-row swarm-leader ${stale ? 'swarm-link-bad' : ''}"
                     title="Time since the last radio packet from the swarm leader. Over 5 s triggers HOLD.">
                    <span class="swarm-strip-name">Leader link</span>
                    <span class="swarm-strip-dist">${linkLabel}</span>
                </div>`);
        }

        // Stop banner
        if (swarm.stopped) {
            rows.unshift(`
                <div class="swarm-strip-row swarm-stopped">
                    <span class="swarm-strip-name">SWARM STOP</span>
                    <span class="swarm-strip-dist">${swarm.stop_reason || ''}</span>
                </div>`);
        }

        strip.innerHTML = rows.join('');
    }

    // ----- Public hook called by webrtc.js telemetry dispatch ------------

    window.handleSwarmTelemetry = function (telemetry) {
        if (!telemetry) return;
        lastTelemetry = telemetry;
        const swarm = telemetry.SWARM;
        lastBoatLat = telemetry.LAT || null;
        lastBoatLon = telemetry.LON || null;
        if (!swarm) return;
        lastSwarm = swarm;
        if (!document.getElementById('swarmPanel')) injectPanel();
        updateOverlay(swarm, telemetry);
        renderPanelState(swarm);
        renderStrip(swarm);
        renderMockRow(telemetry);
    };

    function renderMockRow(telemetry) {
        const row = document.getElementById('swarmDevBlock');
        const sel = document.getElementById('swarmMockSelect');
        if (!row || !sel) return;
        // Only show the dev block when (a) we're in mock mode AND (b) the
        // operator has logged in as admin. Hides the developer affordance
        // from non-admin operators in the field.
        const isAdmin = (typeof adminToken !== 'undefined') && !!adminToken;
        if (!telemetry.MOCK_MODE || !isAdmin) {
            row.style.display = 'none';
            return;
        }
        row.style.display = '';
        const scenarios = telemetry.MOCK_SCENARIOS || [];
        if (sel.options.length !== scenarios.length) {
            sel.innerHTML = '';
            scenarios.forEach(s => {
                const opt = document.createElement('option');
                opt.value = s;
                opt.textContent = s;
                sel.appendChild(opt);
            });
        }
        if (telemetry.MOCK_SCENARIO && sel.value !== telemetry.MOCK_SCENARIO) {
            sel.value = telemetry.MOCK_SCENARIO;
        }
        if (telemetry.MOCK_MEMBERS) {
            const sizeSlider = document.getElementById('swarmMockSize');
            const sizeLabel  = document.getElementById('swarmMockSizeLabel');
            if (sizeSlider && document.activeElement !== sizeSlider) {
                sizeSlider.value = telemetry.MOCK_MEMBERS;
                if (sizeLabel) sizeLabel.textContent = telemetry.MOCK_MEMBERS;
            }
        }
    }

    // Inject as soon as the DOM is ready (panel may render with placeholder
    // values until the first telemetry packet arrives).
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', injectPanel);
    } else {
        injectPanel();
    }
})();
