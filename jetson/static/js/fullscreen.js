// ======================================================
// FULL-SCREEN TOGGLES — map + camera
// ======================================================
// Adds an "expand" button to the top-right corner of each .geo-panel and
// .video-panel. Click → that one panel fills the entire viewport. Click
// again or press Esc → returns to the dashboard layout. Independent for
// the two widgets.
// ======================================================

(function () {
    "use strict";

    const FS_CLASS = 'aqua-fullscreen';
    let activeFullscreen = null;  // the currently-fullscreened element

    function injectButtons() {
        // Inject one fullscreen button into each .media-col's header bar
        // (next to the title + meta), so it sits OUTSIDE the leaflet/video
        // surface and never collides with the layer-picker or other map
        // controls.
        document.querySelectorAll('.media-col').forEach(col => {
            if (col.querySelector('.fs-btn')) return;
            const head = col.querySelector('.media-head');
            const panel = col.querySelector('.geo-panel, .video-panel');
            if (!head || !panel) return;
            const btn = document.createElement('button');
            btn.className = 'fs-btn';
            btn.title = 'Full screen (Esc to exit)';
            btn.setAttribute('aria-label', 'Toggle full screen');
            btn.innerHTML = '&#x26F6;';  // four-corners glyph
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                toggleFullscreen(panel);
            });
            head.appendChild(btn);
        });
    }

    function toggleFullscreen(panel) {
        if (panel.classList.contains(FS_CLASS)) {
            exitFullscreen(panel);
        } else {
            enterFullscreen(panel);
        }
    }

    function enterFullscreen(panel) {
        // Exit any other fullscreen first
        if (activeFullscreen && activeFullscreen !== panel) {
            exitFullscreen(activeFullscreen);
        }
        panel.classList.add(FS_CLASS);
        document.body.classList.add('aqua-fullscreen-active');
        activeFullscreen = panel;
        // Leaflet needs a kick when its container resizes; otherwise tiles
        // don't repaint and the map looks frozen.
        if (panel.classList.contains('geo-panel') && typeof map !== 'undefined' && map) {
            setTimeout(() => map.invalidateSize(), 100);
        }
    }

    function exitFullscreen(panel) {
        panel.classList.remove(FS_CLASS);
        document.body.classList.remove('aqua-fullscreen-active');
        activeFullscreen = null;
        if (panel.classList.contains('geo-panel') && typeof map !== 'undefined' && map) {
            setTimeout(() => map.invalidateSize(), 100);
        }
    }

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && activeFullscreen) {
            exitFullscreen(activeFullscreen);
        }
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', injectButtons);
    } else {
        injectButtons();
    }
})();
