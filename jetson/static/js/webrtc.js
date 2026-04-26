console.log("🚀 WebRTC JS Loaded");


// ======================================================
// SERVERS (MOVE THIS HERE)
// ======================================================
const host = window.location.hostname;

const SIGNALING_URL = `ws://${host}:8765`;
const TELEMETRY_URL = `ws://${host}:8766`;

// ======================================================
// THROTTLE SOCKET
// ======================================================
const THROTTLE_URL = `ws://${host}:8770`;
const throttleSocket = new WebSocket(THROTTLE_URL);

throttleSocket.onopen = () => {
    console.log("🚤 THROTTLE CONNECTED");
};

throttleSocket.onerror = (e) => {
    console.log("Throttle socket error:", e);
};

function setThrottle(val) {
    console.log("Throttle:", val);
    if (throttleSocket.readyState === WebSocket.OPEN) {
        throttleSocket.send(val.toString());
    } else {
        console.warn("Throttle socket not ready");
    }
}

// =======================
// CONTROL SOCKET (AUTO RECONNECT)
// =======================
let controlWS = null;

function connectControl() {
    controlWS = new WebSocket(`ws://${host}:8770`);

    controlWS.onopen = () => {
        console.log("🎮 Control connected");
    };

    controlWS.onclose = () => {
        console.log("❌ Control disconnected... reconnecting");
        setTimeout(connectControl, 2000);
    };

    controlWS.onerror = () => {
        controlWS.close();
    };
}

connectControl();


// =======================
// ARM / DISARM
// =======================
function sendArm() {
    console.log("ARM pressed");

    if (controlWS && controlWS.readyState === WebSocket.OPEN) {
        controlWS.send("ARM");
    } else {
        console.log("⚠️ Control not connected");
    }
}

function sendDisarm() {
    console.log("DISARM pressed");

    if (controlWS && controlWS.readyState === WebSocket.OPEN) {
        controlWS.send("DISARM");
    } else {
        console.log("⚠️ Control not connected");
    }
}


// =======================
// THROTTLE
// =======================
function setThrottle(val) {
    console.log("Throttle:", val);

    if (controlWS && controlWS.readyState === WebSocket.OPEN) {
        controlWS.send(String(val));
    } else {
        console.log("⚠️ Control not connected");
    }
}
// ======================================================
// SIGNALING
// ======================================================
const ws = new WebSocket(SIGNALING_URL);

// ======================================================
// TELEMETRY
// ======================================================
let telemetryWS = null;

function connectTelemetry() {
    console.log("Connecting to telemetry:", TELEMETRY_URL);

    telemetryWS = new WebSocket(TELEMETRY_URL);

    telemetryWS.onopen = () => {
        console.log("📡 TELEMETRY CONNECTED");
    };

    telemetryWS.onmessage = (msg) => {
        try {
            const data = JSON.parse(msg.data);
            updateTelemetryUI(data);
            if (typeof window.handleSwarmTelemetry === 'function') {
                window.handleSwarmTelemetry(data);
            }
        } catch (e) {
            console.log("Telemetry parse error:", e);
        }
    };

    telemetryWS.onclose = () => {
        console.log("Telemetry disconnected. Reconnecting...");
        setTimeout(connectTelemetry, 2000);
    };

    telemetryWS.onerror = (e) => {
        console.log("Telemetry socket error:", e);
        telemetryWS.close();
    };
}

connectTelemetry();
// ======================================================
// OVERLAY SYSTEM
// ======================================================
let activeOverlay = null;
let overlayLayer = null;
let overlayLegend = null;
let lastTelemetry = null;

// ======================================================
// WEBRTC VIDEO
// ======================================================
const pc = new RTCPeerConnection({
    iceServers: [{ urls: ["stun:stun.l.google.com:19302"] }]
});

pc.ontrack = (event) => {
    const video = document.getElementById("webrtcVideo");
    if (video) {
        console.log("📹 Attaching Jetson video stream");
        video.srcObject = event.streams[0];
        video.play().catch(e => console.log("Video play error:", e));
    }
};

ws.onopen = async () => {
    console.log("✅ SIGNALING CONNECTED");

    pc.addTransceiver("video", { direction: "recvonly" });

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    ws.send(JSON.stringify({ offer: offer }));
};

ws.onmessage = async (msg) => {
    const data = JSON.parse(msg.data);

    // ✅ FIXED: prevent duplicate answer
    if (data.answer) {
        if (pc.currentRemoteDescription) {
            console.warn("⚠️ Answer already set — skipping");
            return;
        }

        await pc.setRemoteDescription(
            new RTCSessionDescription(data.answer)
        );

        console.log("✅ Remote description set");
        return;
    }

    if (data.ice) {
        pc.addIceCandidate(data.ice).catch(console.error);
        return;
    }

    if (data.recording !== undefined) {
        const recordStatus = document.getElementById("recordStatus");
        const recordIndicator = document.getElementById("recordIndicator");
        const startBtn = document.getElementById("startRecord");

        if (data.recording) {
            if (recordStatus)
                recordStatus.style.backgroundColor = "limegreen";

            if (recordIndicator)
                recordIndicator.style.display = "block";

            if (startBtn) {
                startBtn.style.backgroundColor = "#00c853";
                startBtn.style.color = "white";
                startBtn.innerText = "Recording...";
            }

        } else {
            if (recordStatus)
                recordStatus.style.backgroundColor = "red";

            if (recordIndicator)
                recordIndicator.style.display = "none";

            if (startBtn) {
                startBtn.style.backgroundColor = "";
                startBtn.style.color = "";
                startBtn.innerText = "Start Recording";
            }
        }
    }
};
// ======================================================
// MAP SYSTEM
// ======================================================
let map = null;
let droneMarker = null;
let mapReady = false;

function initializeMap(lat, lon) {
    if (mapReady) return;

    // Base layers — satellite is the default since we operate on water where
    // street maps show nothing but a solid blue blob. Users can flip to the
    // other base layers using the control in the top-right of the map.
    const baseLayers = {
        "Satellite": L.tileLayer(
            'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            {
                maxZoom: 19,
                attribution: 'Tiles &copy; Esri — World Imagery'
            }
        ),
        "Street (OSM)": L.tileLayer(
            'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
            { maxZoom: 19, attribution: '&copy; OpenStreetMap contributors' }
        ),
        "Topographic": L.tileLayer(
            'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
            { maxZoom: 17, attribution: 'Map data &copy; OpenTopoMap (CC-BY-SA)' }
        ),
    };

    // Optional overlay: OpenSeaMap marine chart (buoys, depths, hazards).
    // Transparent — rides on top of whichever base layer is active.
    const overlays = {
        "Nautical (OpenSeaMap)": L.tileLayer(
            'https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png',
            { maxZoom: 18, attribution: '&copy; OpenSeaMap contributors' }
        ),
    };

    map = L.map('map', {
        layers: [baseLayers["Satellite"]],
        zoomControl: false,           // no built-in +/- (mouse wheel still works)
    }).setView([lat, lon], 17);
    L.control.layers(baseLayers, overlays,
                     { position: 'bottomright', collapsed: true }).addTo(map);

    // Live mouse-position readout in the top-right of the map panel header.
    // Useful when placing waypoints on a lake with no road reference.
    map.on('mousemove', e => {
        const el = document.getElementById('mapCoords');
        if (el) el.textContent = `${e.latlng.lat.toFixed(6)}, ${e.latlng.lng.toFixed(6)}  @ z${map.getZoom()}`;
    });

    const arrowIcon = L.divIcon({
        html: `<div id="droneArrow" style="
            width:0;
            height:0;
            border-left:12px solid transparent;
            border-right:12px solid transparent;
            border-bottom:45px solid red;
            transform-origin:50% 75%;
            filter: drop-shadow(0 0 4px rgba(0,0,0,0.8));
        "></div>`,
        className: '',
        iconSize: [40, 40]
    });

    droneMarker = L.marker([lat, lon], { icon: arrowIcon }).addTo(map);

    mapReady = true;
}

function updateMapPosition(lat, lon, heading) {
    if (!mapReady) {
        initializeMap(lat, lon);
    }

    droneMarker.setLatLng([lat, lon]);
    map.panTo([lat, lon]);

    const arrow = document.getElementById("droneArrow");
    if (arrow) {
        arrow.style.transform = `rotate(${heading}deg)`;
    }
}

// ======================================================
// TEMPERATURE OVERLAY
// ======================================================
function getTempColor(temp) {

    const min = 15;
    const max = 35;

    const ratio = Math.max(0, Math.min(1, (temp - min) / (max - min)));

    const r = Math.floor(255 * ratio);
    const g = Math.floor(255 * (1 - Math.abs(ratio - 0.5) * 2));
    const b = Math.floor(255 * (1 - ratio));

    return `rgb(${r},${g},${b})`;
}

function drawTempOverlay(t) {

    if (!map || !t.LAT || t.LAT === "0.000000") return;

    const lat = parseFloat(t.LAT);
    const lon = parseFloat(t.LON);
    const temp = parseFloat(t.TEMP || 0);

    if (overlayLayer) {
        overlayLayer.remove();
    }

    overlayLayer = L.circle([lat, lon], {
        radius: 25,   // <-- Larger demo radius
        color: getTempColor(temp),
        fillColor: getTempColor(temp),
        fillOpacity: 0.45
    }).addTo(map);
}

function addTempLegend() {

    if (overlayLegend) overlayLegend.remove();

    overlayLegend = L.control({ position: "bottomright" });

    overlayLegend.onAdd = function () {

        const div = L.DomUtil.create("div");

        div.style.background = "rgba(0,0,0,0.85)";
        div.style.padding = "10px";
        div.style.borderRadius = "8px";
        div.style.color = "white";
        div.style.fontSize = "12px";
        div.style.width = "170px";

        div.innerHTML = `
            <div style="margin-bottom:6px;"><b>Temperature (°C)</b></div>
            <div style="
                height:14px;
                background: linear-gradient(to right,
                    blue,
                    cyan,
                    green,
                    yellow,
                    red);
                border-radius:4px;
                margin-bottom:4px;
            "></div>
            <div style="display:flex; justify-content:space-between;">
                <span>15</span>
                <span>25</span>
                <span>35</span>
            </div>
        `;

        return div;
    };

   overlayLegend.addTo(map);
}

function clearOverlay() {
    activeOverlay = null;

    if (overlayLayer) {
        overlayLayer.remove();
        overlayLayer = null;
    }

    if (overlayLegend) {
        overlayLegend.remove();
        overlayLegend = null;
    }

    document.querySelectorAll(".overlay-active").forEach(btn => {
        btn.classList.remove("overlay-active");
    });
}

// ======================================================
// TELEMETRY UI UPDATE
// ======================================================
// ======================================================
// TELEMETRY UI UPDATE
// ======================================================
function updateTelemetryUI(t) {

    lastTelemetry = t;

    const hasFix = parseFloat(t.LAT) !== 0;

    const gpsFix = document.getElementById("gpsFix");
    if (gpsFix) {
        gpsFix.style.backgroundColor = hasFix ? "limegreen" : "red";
    }

    let spd = parseFloat(t.SPD || 0);
    if (spd < 0.2) spd = 0;

    const speed = document.getElementById("speedKnots");
    if (speed) speed.textContent = spd.toFixed(1);

    // 🗺️ Map update
    if (hasFix) {
        updateMapPosition(
            parseFloat(t.LAT),
            parseFloat(t.LON),
            parseFloat(t.HEAD || 0)
        );
    }

    // 🎯 Overlay handling (clean + safe)
    if (activeOverlay === "temp") {
        drawTempOverlay(t);
    } 
    else if (activeOverlay === "ph") {
        drawPHOverlay(t);
    } 
    else if (activeOverlay === "sal") {
        drawSalOverlay(t);
    }

    // 📊 Rolling telemetry log (now on the Telemetry tab).
    const table = document.getElementById("telemetryTableBody");

    if (table) {
        const row = document.createElement("tr");

        row.innerHTML = `
            <td>${t.TIME || "--"}</td>
            <td>${t.LAT  || "--"}</td>
            <td>${t.LON  || "--"}</td>
            <td>${t.HEAD !== undefined ? Number(t.HEAD).toFixed(1) + "°" : "--"}</td>
            <td>${t.SPD  !== undefined ? Number(t.SPD).toFixed(2) : "--"}</td>
            <td>${t.MODE || "--"}</td>
            <td>${t.BAT_V !== undefined ? t.BAT_V : "--"}</td>
            <td>${t.TEMP || "--"}</td>
            <td>${t.SAL  || "--"}</td>
            <td>${t.PH   || "--"}</td>
        `;

        table.prepend(row);

        while (table.rows.length > 10) {
            table.deleteRow(10);
        }
    }
}

// ======================================================
// GEOOVERLAY UI UPDATE
// ======================================================
function drawPHOverlay(t) {
    if (!map || !t.LAT || t.LAT === "0.000000") return;

    const lat = parseFloat(t.LAT);
    const lon = parseFloat(t.LON);
    const ph = parseFloat(t.PH || 0);

    if (overlayLayer) overlayLayer.remove();

    let color = "blue";
    if (ph > 8) color = "purple";
    else if (ph > 7) color = "green";
    else if (ph > 6) color = "yellow";
    else color = "red";

    overlayLayer = L.circle([lat, lon], {
        radius: 25,
        color: color,
        fillColor: color,
        fillOpacity: 0.45
    }).addTo(map);
}

function drawSalOverlay(t) {
    if (!map || !t.LAT || t.LAT === "0.000000") return;

    const lat = parseFloat(t.LAT);
    const lon = parseFloat(t.LON);
    const sal = parseFloat(t.SAL || 0);

    if (overlayLayer) overlayLayer.remove();

    let color = "blue";
    if (sal > 0.3) color = "red";
    else if (sal > 0.2) color = "orange";
    else if (sal > 0.1) color = "green";

    overlayLayer = L.circle([lat, lon], {
        radius: 25,
        color: color,
        fillColor: color,
        fillOpacity: 0.45
    }).addTo(map);
}


// ======================================================
// BUTTONS
// ======================================================
// ======================================================
// BUTTONS
// ======================================================

// 🌡️ TEMP
document.getElementById("toggleTemp")?.addEventListener("click", function () {

    if (activeOverlay === "temp") {
        clearOverlay();
        return;
    }

    clearOverlay();
    activeOverlay = "temp";
    this.classList.add("overlay-active");

    if (lastTelemetry) {
        drawTempOverlay(lastTelemetry);
        addTempLegend();
    }
});

// 🧪 pH
document.getElementById("togglePH")?.addEventListener("click", function () {

    if (activeOverlay === "ph") {
        clearOverlay();
        return;
    }

    clearOverlay();
    activeOverlay = "ph";
    this.classList.add("overlay-active");

    if (lastTelemetry) {
        drawPHOverlay(lastTelemetry);
    }
});

// 🌊 SALINITY
document.getElementById("toggleSal")?.addEventListener("click", function () {

    if (activeOverlay === "sal") {
        clearOverlay();
        return;
    }

    clearOverlay();
    activeOverlay = "sal";
    this.classList.add("overlay-active");

    if (lastTelemetry) {
        drawSalOverlay(lastTelemetry);
    }
});

// ❌ CLEAR
document.getElementById("clearOverlay")?.addEventListener("click", clearOverlay);

// ======================================================
// COMMANDS (RESTORED)
// ======================================================
function sendCommand(cmd) {
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ command: cmd }));
    }
}

document.getElementById("zoomIn")?.addEventListener("click", () => {
    sendCommand("zoom_in");
});

document.getElementById("zoomOut")?.addEventListener("click", () => {
    sendCommand("zoom_out");
});

const startBtn = document.getElementById("startRecord");
const stopBtn = document.getElementById("stopRecord");

startBtn?.addEventListener("click", () => {
    sendCommand("start_record");

    // Immediate UI change
    startBtn.style.backgroundColor = "#00c853";
    startBtn.style.color = "white";
    startBtn.innerText = "Recording...";

    const recordStatus = document.getElementById("recordStatus");
    if (recordStatus)
        recordStatus.style.backgroundColor = "limegreen";

    const recordIndicator = document.getElementById("recordIndicator");
    if (recordIndicator)
        recordIndicator.style.display = "block";
});

stopBtn?.addEventListener("click", () => {
    sendCommand("stop_record");

    startBtn.style.backgroundColor = "";
    startBtn.style.color = "";
    startBtn.innerText = "Start Recording";

    const recordStatus = document.getElementById("recordStatus");
    if (recordStatus)
        recordStatus.style.backgroundColor = "red";

    const recordIndicator = document.getElementById("recordIndicator");
    if (recordIndicator)
        recordIndicator.style.display = "none";
});

// ======================================================
// VIDEO LATENCY
// ======================================================
async function updateLatency() {
    const stats = await pc.getStats();

    stats.forEach(report => {
        if (report.type === "inbound-rtp" && report.kind === "video") {
            if (report.jitter) {
                const latency = document.getElementById("videoLatency");
                if (latency) {
                    latency.textContent =
                        (report.jitter * 1000).toFixed(0);
                }
            }
        }
    });
}

setInterval(updateLatency, 1000);
