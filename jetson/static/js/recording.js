// ======================================================
// RECORDING + SAVE CONFIRMATIONS (Phases C2 + C3)
//
// Dual-save: when the operator hits Start Recording, the existing handler
// in webrtc.js tells the Jetson to start its local recording, AND this module
// starts a MediaRecorder on the WebRTC stream so the same footage is written
// to the ground station's disk. Both stop together.
//
// Also: toast confirmations for the Download Telemetry CSV button and for
// the Stop Recording button (showing the local filename written).
// ======================================================

let gcsRecorder      = null;
let gcsChunks        = [];
let gcsRecordingName = null;

function videoElement() { return document.getElementById('webrtcVideo'); }

function streamFromVideo() {
    const v = videoElement();
    if (!v) return null;
    if (v.srcObject) return v.srcObject;                // direct MediaStream (WebRTC attaches this)
    if (typeof v.captureStream === 'function') return v.captureStream();
    return null;
}

function startGcsRecording() {
    if (gcsRecorder) return;  // already recording
    const stream = streamFromVideo();
    if (!stream) {
        if (window.aquaToast) window.aquaToast('GCS recording skipped — no video stream yet', 'warn');
        return;
    }
    // Let the browser pick the best supported mime; VP9 preferred.
    const mimes = ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm'];
    let mime = '';
    for (const m of mimes) { if (MediaRecorder.isTypeSupported(m)) { mime = m; break; } }
    try {
        gcsRecorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
    } catch (e) {
        console.warn('GCS recorder failed:', e);
        if (window.aquaToast) window.aquaToast('GCS recording failed to start', 'error');
        gcsRecorder = null;
        return;
    }
    gcsChunks = [];
    gcsRecorder.ondataavailable = e => { if (e.data && e.data.size) gcsChunks.push(e.data); };
    gcsRecorder.onerror = e => console.warn('GCS recorder error:', e);
    gcsRecorder.start(1000);  // fire ondataavailable every 1s so nothing's lost on crash
    const ts = new Date().toISOString().replace(/[:.]/g, '-');
    gcsRecordingName = `aquabot_gcs_${ts}.webm`;
    if (window.aquaToast) window.aquaToast('GCS recording started', null, gcsRecordingName);
}

function stopGcsRecording() {
    if (!gcsRecorder) return;
    const rec  = gcsRecorder;
    const name = gcsRecordingName;
    gcsRecorder = null;
    gcsRecordingName = null;
    rec.onstop = () => {
        const blob = new Blob(gcsChunks, { type: rec.mimeType || 'video/webm' });
        gcsChunks = [];
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = name;
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(url), 2000);
        if (window.aquaToast) window.aquaToast('GCS recording saved', null, name, 6000);
    };
    rec.stop();
}

// Attach alongside the existing webrtc.js handlers — multiple listeners both fire,
// so this doesn't need to know or modify what webrtc.js already does.
document.getElementById('startRecord')?.addEventListener('click', startGcsRecording);
document.getElementById('stopRecord')?.addEventListener('click', () => {
    stopGcsRecording();
    if (window.aquaToast) window.aquaToast('Stop recording sent to Jetson');
});

// Toast confirmation when the telemetry CSV download button fires (C3).
document.getElementById('btnDownloadTelemetry')?.addEventListener('click', () => {
    // The other listener on this button does the actual download; we just
    // confirm — empty-buffer case is handled there.
    setTimeout(() => {
        if (typeof telemetryBuf !== 'undefined' && telemetryBuf && telemetryBuf.length > 0) {
            if (window.aquaToast) window.aquaToast('Telemetry CSV saved to Downloads');
        }
    }, 50);
});
