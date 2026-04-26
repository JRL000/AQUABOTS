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
    let lastSwarm = null;
    let lastBoatLat = null, lastBoatLon = null;

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

    // ----- Map overlay updates -------------------------------------------

    function ensureLayers() {
        if (typeof map === 'undefined' || !map) return false;
        return true;
    }

    function updateOverlay(swarm) {
        if (!ensureLayers()) return;

        // Leader marker
        const leaderGps = swarm.leader_gps;
        if (leaderGps) {
            const [lat, lon] = leaderGps;
            if (leaderMarker) {
                leaderMarker.setLatLng([lat, lon]);
            } else {
                leaderMarker = L.marker([lat, lon], { icon: leaderIcon() }).addTo(map);
            }
        } else if (leaderMarker) {
            map.removeLayer(leaderMarker);
            leaderMarker = null;
        }

        // Ghost (this boat's assigned slot, if follower)
        const tgt = swarm.target_latlon;
        if (tgt && swarm.role === 'follower') {
            const [lat, lon] = tgt;
            if (ghostMarker) {
                ghostMarker.setLatLng([lat, lon]);
            } else {
                ghostMarker = L.marker([lat, lon], { icon: ghostIcon() }).addTo(map);
            }

            // Dashed line from real boat to ghost slot
            if (lastBoatLat !== null && lastBoatLon !== null) {
                const pts = [[lastBoatLat, lastBoatLon], [lat, lon]];
                if (stationLine) {
                    stationLine.setLatLngs(pts);
                } else {
                    stationLine = L.polyline(pts, {
                        color: '#7ad6ff',
                        weight: 2,
                        dashArray: '6,6',
                        opacity: 0.85,
                    }).addTo(map);
                }
            }
        } else {
            if (ghostMarker) { map.removeLayer(ghostMarker); ghostMarker = null; }
            if (stationLine) { map.removeLayer(stationLine); stationLine = null; }
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
                <div class="swarm-row swarm-mock-row" id="swarmMockRow" style="display:none;">
                    <label>Mock scenario (dev)</label>
                    <select id="swarmMockSelect"></select>
                </div>
            </div>
        </div>
        <div id="swarmStrip" class="swarm-strip"></div>`;
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

    function wireControls() {
        // Spacing slider live label
        const slider = document.getElementById('swarmSpacing');
        const lbl = document.getElementById('swarmSpacingLabel');
        slider.addEventListener('input', () => {
            lbl.textContent = (parseInt(slider.value, 10) / 1000).toFixed(1);
        });

        // Pattern buttons
        document.querySelectorAll('.swarm-pat-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const pat = btn.dataset.pat;
                const spacing = parseInt(slider.value, 10);
                sendCtrl({
                    action: 'swarm_set_pattern',
                    pattern: pat,
                    spacing_mm: spacing,
                    token: (typeof adminToken !== 'undefined') ? adminToken : null,
                });
                document.querySelectorAll('.swarm-pat-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
            });
        });

        // Start / Exit
        const startBtn = document.getElementById('swarmStartBtn');
        startBtn.addEventListener('click', () => {
            const turningOn = !startBtn.classList.contains('on');
            sendCtrl({
                action: 'swarm_enable',
                on: turningOn,
                token: (typeof adminToken !== 'undefined') ? adminToken : null,
            });
        });

        // Collapse toggle
        const head = document.querySelector('.swarm-panel-head');
        const body = document.querySelector('.swarm-panel-body');
        document.getElementById('swarmCollapseBtn').addEventListener('click', () => {
            const hidden = body.style.display === 'none';
            body.style.display = hidden ? '' : 'none';
            head.querySelector('button').textContent = hidden ? '−' : '+';
        });

        // Mock-mode scenario picker (populated + shown when telemetry says so)
        document.getElementById('swarmMockSelect').addEventListener('change', (e) => {
            sendCtrl({
                action: 'mock_set_scenario',
                scenario: e.target.value,
                token: (typeof adminToken !== 'undefined') ? adminToken : null,
            });
            toast(`Switching mock scenario to ${e.target.value}`);
        });
    }

    function sendCtrl(obj) {
        if (typeof controlWS === 'undefined' || !controlWS || controlWS.readyState !== 1) {
            console.warn('[SWARM] controlWS not ready, dropping', obj);
            toast('Control link not ready');
            return;
        }
        controlWS.send(JSON.stringify(obj));
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

        // Highlight current pattern button
        if (swarm.pattern) {
            document.querySelectorAll('.swarm-pat-btn').forEach(b => {
                b.classList.toggle('active', b.dataset.pat === swarm.pattern);
            });
        }
    }

    function renderStrip(swarm) {
        const strip = document.getElementById('swarmStrip');
        if (!strip) return;
        const rows = [];

        // This boat row
        let dist = '--';
        if (swarm.target_latlon && lastBoatLat !== null && lastBoatLon !== null) {
            const [tlat, tlon] = swarm.target_latlon;
            dist = haversineM(lastBoatLat, lastBoatLon, tlat, tlon).toFixed(1) + ' m';
        }
        const role = swarm.role || 'unknown';
        const onStation = (dist !== '--' && parseFloat(dist) < 1.0);
        rows.push(`
            <div class="swarm-strip-row swarm-self ${onStation ? 'swarm-on-station' : ''}">
                <span class="swarm-strip-name">This boat</span>
                <span class="swarm-strip-role">${role}</span>
                <span class="swarm-strip-dist">${dist}${onStation ? ' (on station)' : ''}</span>
            </div>`);

        // Leader row (if not us)
        if (swarm.leader_id != null && role !== 'leader') {
            const age = swarm.leader_gps_age_s;
            const ageTxt = age == null ? 'no GPS' : age.toFixed(1) + 's old';
            const stale = (age == null || age > 5);
            rows.push(`
                <div class="swarm-strip-row swarm-leader ${stale ? 'swarm-link-bad' : ''}">
                    <span class="swarm-strip-name">Leader (node ${swarm.leader_id})</span>
                    <span class="swarm-strip-role">leader</span>
                    <span class="swarm-strip-dist">GPS ${ageTxt}</span>
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
        const swarm = telemetry.SWARM;
        lastBoatLat = telemetry.LAT || null;
        lastBoatLon = telemetry.LON || null;
        if (!swarm) return;
        lastSwarm = swarm;
        if (!document.getElementById('swarmPanel')) injectPanel();
        updateOverlay(swarm);
        renderPanelState(swarm);
        renderStrip(swarm);
        renderMockRow(telemetry);
    };

    function renderMockRow(telemetry) {
        const row = document.getElementById('swarmMockRow');
        const sel = document.getElementById('swarmMockSelect');
        if (!row || !sel) return;
        if (!telemetry.MOCK_MODE) {
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
    }

    // Inject as soon as the DOM is ready (panel may render with placeholder
    // values until the first telemetry packet arrives).
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', injectPanel);
    } else {
        injectPanel();
    }
})();
