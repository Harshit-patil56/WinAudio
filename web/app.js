// WinAudio Mobile Web Client — Low-Latency TCP WebSocket PCM Receiver with AudioWorklet

let isStreaming = false;
let audioCtx = null;
let gainNode = null;
let analyserNode = null;
let workletNode = null;
let websocket = null;
let currentMode = 'usb';
let targetBufferMs = 35;

// DOM Elements
const toggleBtn = document.getElementById('toggleBtn');
const btnIcon = document.getElementById('btnIcon');
const btnText = document.getElementById('btnText');
const statusDot = document.getElementById('statusDot');
const statusTitle = document.getElementById('statusTitle');
const statusSub = document.getElementById('statusSub');
const transportBadge = document.getElementById('transportBadge');
const volumeSlider = document.getElementById('volumeSlider');
const volumeVal      = document.getElementById('volumeVal');
const latencyVal     = document.getElementById('latencyVal');
const bufferVal      = document.getElementById('bufferVal');
const sampleRateVal  = document.getElementById('sampleRateVal');
const fidelityPill   = document.querySelector('.fidelity-pill');

// ── 20-Bar Apple Voice Memos Leftward Scrolling Visualizer ──────────────────
const barVisualizerContainer = document.getElementById('barVisualizer');
const BAR_COUNT = 20;
const MIN_HEIGHT = 15;
const MAX_HEIGHT = 90;
const barElements = [];
const currentHeights = new Float32Array(BAR_COUNT).fill(MIN_HEIGHT);
const targetHeights = new Float32Array(BAR_COUNT).fill(MIN_HEIGHT);

if (barVisualizerContainer) {
    barVisualizerContainer.innerHTML = '';
    for (let i = 0; i < BAR_COUNT; i++) {
        const bar = document.createElement('div');
        bar.className = 'bar-item';
        bar.style.height = `${MIN_HEIGHT}%`;
        barVisualizerContainer.appendChild(bar);
        barElements.push(bar);
    }
}

let freqBuffer = new Uint8Array(64);
let timeData = new Uint8Array(128);
let rollingPeak = 30.0;

// Render Apple Monochrome Style Waveform Loop with Dynamic Normalization & Leftward Motion (60 FPS)
function drawVisualizer() {
    requestAnimationFrame(drawVisualizer);
    const now = Date.now();

    if (isStreaming && analyserNode) {
        analyserNode.getByteTimeDomainData(timeData);
        analyserNode.getByteFrequencyData(freqBuffer);

        // 1. Compute acoustic energy & peak deviation from center line (128)
        let sumAmp = 0;
        let peakDiff = 0;
        for (let i = 0; i < timeData.length; i++) {
            const v = Math.abs(timeData[i] - 128);
            sumAmp += v;
            if (v > peakDiff) peakDiff = v;
        }
        const avgAmp = sumAmp / timeData.length;

        // 2. Adaptive Rolling Peak Tracker (Automatic Gain Control for visualizer)
        rollingPeak = Math.max(avgAmp * 1.2, peakDiff * 0.8, rollingPeak * 0.982, 6.0);

        // 3. Dynamic non-linear range mapping (ensures peaks, valleys, and rhythm)
        const normalized = Math.min(1.0, Math.max(0.0, (avgAmp * 0.55 + peakDiff * 0.45) / (rollingPeak + 1.0)));

        // Add subtle harmonic voice cadence variation to prevent flatline saturation
        const cadenceVar = ((freqBuffer[2] || 0) % 12) / 100.0;
        const liveAmp = Math.min(0.88, Math.max(0.0, Math.pow(normalized, 1.3) + cadenceVar * 0.12));

        // Push into rightmost bar and propagate leftward (Apple Voice Memos waterfall)
        for (let i = 0; i < BAR_COUNT - 1; i++) {
            targetHeights[i] = targetHeights[i + 1];
        }
        targetHeights[BAR_COUNT - 1] = MIN_HEIGHT + liveAmp * (MAX_HEIGHT - MIN_HEIGHT);
    }

    for (let i = 0; i < BAR_COUNT; i++) {
        let target = MIN_HEIGHT;
        if (isStreaming) {
            target = targetHeights[i];
        } else {
            // Apple gentle organic ambient breathing motion
            target = MIN_HEIGHT + Math.sin(now * 0.0028 + i * 0.42) * 2.2;
        }

        // Apple iOS Fluid Spring Physics
        const isAttacking = target > currentHeights[i];
        const lerpFactor = isAttacking ? 0.42 : 0.18;
        currentHeights[i] += (target - currentHeights[i]) * lerpFactor;

        if (barElements[i]) {
            barElements[i].style.height = `${currentHeights[i].toFixed(1)}%`;

            if (isStreaming && currentHeights[i] > MIN_HEIGHT + 1.2) {
                barElements[i].classList.add('speaking');
                const normalized = Math.max(0, Math.min(1, (currentHeights[i] - MIN_HEIGHT) / (MAX_HEIGHT - MIN_HEIGHT)));
                const alpha = 0.25 + normalized * 0.70;
                barElements[i].style.backgroundColor = `rgba(255, 255, 255, ${alpha.toFixed(2)})`;

                if (normalized > 0.60) {
                    barElements[i].style.boxShadow = `0 0 8px rgba(255, 255, 255, ${(normalized * 0.40).toFixed(2)})`;
                } else {
                    barElements[i].style.boxShadow = 'none';
                }
            } else {
                barElements[i].classList.remove('speaking');
                barElements[i].style.backgroundColor = 'rgba(255, 255, 255, 0.22)';
                barElements[i].style.boxShadow = 'none';
            }
        }
    }
}
drawVisualizer();

// ── Transport Badge Helper ──────────────────────────────────────────────────
function setTransportBadge(iconType, text) {
    if (!transportBadge) return;
    let iconSvg = '';
    if (iconType === 'usb') {
        iconSvg = `<svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>`;
    } else if (iconType === 'wifi') {
        iconSvg = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.55a11 11 0 0 1 14.08 0"></path><path d="M1.42 9a16 16 0 0 1 21.16 0"></path><path d="M8.53 16.11a6 6 0 0 1 6.95 0"></path><circle cx="12" cy="20" r="1" fill="currentColor"></circle></svg>`;
    } else if (iconType === 'stable') {
        iconSvg = `<svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm-1 15l-4-4 1.41-1.41L11 13.17l5.59-5.59L18 9l-7 7z"/></svg>`;
    }
    transportBadge.innerHTML = `${iconSvg}<span>${text}</span>`;
}

// ── USB Device Status Checker ──────────────────────────────────────────────
async function checkUsbStatus() {
    const isLocal = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');
    if (!isLocal) {
        return { usb_connected: false, is_local: false, device_id: null };
    }
    try {
        const res = await fetch('/api/usb-status', { cache: 'no-store' });
        if (res.ok) {
            return await res.json();
        }
    } catch (e) {
        console.warn('[WinAudio] Could not query USB status:', e);
    }
    return { usb_connected: false, is_local: isLocal, device_id: null };
}

// ── Initial Transport Detection ─────────────────────────────────────────────
async function detectAndSetTransportBadge() {
    const isLocal = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');
    if (isLocal) {
        const status = await checkUsbStatus();
        if (status.usb_connected) {
            currentMode = 'usb';
            targetBufferMs = 35;
            setTransportBadge('usb', 'USB');
            if (latencyVal) latencyVal.innerText = '~35 ms';
            const usbTab = document.getElementById('modeUsb');
            if (usbTab) {
                modeTabs.forEach(t => t.classList.remove('active'));
                usbTab.classList.add('active');
                updateModeIndicator(0);
            }
        } else {
            currentMode = 'wifi';
            targetBufferMs = 50;
            setTransportBadge('wifi', 'Wi-Fi');
            if (latencyVal) latencyVal.innerText = '~50 ms';
            const wifiTab = document.getElementById('modeWifi');
            if (wifiTab) {
                modeTabs.forEach(t => t.classList.remove('active'));
                wifiTab.classList.add('active');
                updateModeIndicator(1);
            }
        }
    } else {
        currentMode = 'wifi';
        targetBufferMs = 50;
        setTransportBadge('wifi', 'Wi-Fi');
        if (latencyVal) latencyVal.innerText = '~50 ms';
        const wifiTab = document.getElementById('modeWifi');
        if (wifiTab) {
            modeTabs.forEach(t => t.classList.remove('active'));
            wifiTab.classList.add('active');
            updateModeIndicator(1);
        }
    }
    if (sampleRateVal) sampleRateVal.innerText = '48.0 kHz';
    if (bufferVal) bufferVal.innerText = '0.0 ms';
}

// ── Web Audio Engine Initialization (High-Fidelity Timeline Engine) ──────────
let nextPlayTime = 0;

async function initAudioEngine() {
    if (!audioCtx) {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        audioCtx = new AudioContextClass({ latencyHint: 'interactive', sampleRate: 48000 });

        gainNode = audioCtx.createGain();
        gainNode.gain.value = volumeSlider.value / 100;

        analyserNode = audioCtx.createAnalyser();
        analyserNode.fftSize = 128;
        analyserNode.smoothingTimeConstant = 0.4;

        // Pipe: gainNode -> analyserNode -> destination
        gainNode.connect(analyserNode);
        analyserNode.connect(audioCtx.destination);

        if (sampleRateVal) {
            sampleRateVal.innerText = `${(audioCtx.sampleRate / 1000).toFixed(1)} kHz`;
        }
    }

    if (audioCtx.state === 'suspended') {
        await audioCtx.resume();
    }
}

// High-Fidelity Low-Latency PCM Timeline Audio Scheduler
function schedulePCMChunk(arrayBuffer) {
    if (!audioCtx || audioCtx.state !== 'running') return;
    const int16 = new Int16Array(arrayBuffer);
    const numFrames = int16.length / 2;
    if (numFrames === 0) return;

    const audioBuffer = audioCtx.createBuffer(2, numFrames, 48000);
    const leftChannel = audioBuffer.getChannelData(0);
    const rightChannel = audioBuffer.getChannelData(1);

    for (let i = 0; i < numFrames; i++) {
        leftChannel[i] = int16[i * 2] / 32768.0;
        rightChannel[i] = int16[i * 2 + 1] / 32768.0;
    }

    const source = audioCtx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(gainNode);

    const targetDelay = targetBufferMs / 1000.0;
    const now = audioCtx.currentTime;

    if (nextPlayTime < now) {
        nextPlayTime = now + targetDelay;
    } else if (nextPlayTime > now + Math.max(0.120, targetDelay * 3.0)) {
        nextPlayTime = now + targetDelay; // Drain extreme accumulation
    }

    source.start(nextPlayTime);
    nextPlayTime += audioBuffer.duration;

    const liveBufferMs = Math.max(0, (nextPlayTime - now) * 1000);
    if (bufferVal) bufferVal.innerText = `${liveBufferMs.toFixed(1)} ms`;
}

// ── Low-Latency TCP WebSocket Connection ────────────────────────────────────
function connectWebSocket() {
    return new Promise((resolve, reject) => {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;

        if (websocket) {
            try { websocket.close(); } catch (e) { }
            websocket = null;
        }

        websocket = new WebSocket(wsUrl);
        websocket.binaryType = 'arraybuffer';
        nextPlayTime = 0;

        websocket.onopen = () => {
            if (statusDot) statusDot.classList.add('active');
            if (statusTitle) statusTitle.innerText = 'Connected';
            if (statusSub) statusSub.innerText = 'Streaming from PC';
            if (btnText) btnText.innerText = 'Disconnect';
            if (btnIcon) {
                btnIcon.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2.5"/></svg>`;
            }
            if (toggleBtn) toggleBtn.classList.add('active');
            const pill = document.querySelector('.fidelity-pill');
            if (pill) pill.classList.add('active');
            isStreaming = true;

            // Tell the server our connection mode
            websocket.send(JSON.stringify({ type: 'mode', mode: currentMode }));

            resolve();
        };

        websocket.onmessage = (event) => {
            if (typeof event.data === 'string') {
                try {
                    const msg = JSON.parse(event.data);
                    if (msg.type === 'error') {
                        showUsbModal('Connection Notice', msg.message);
                        stopStreaming();
                        return;
                    }
                } catch (e) { }
            } else if (event.data instanceof ArrayBuffer) {
                schedulePCMChunk(event.data);
            }
        };

        websocket.onerror = (err) => {
            console.error('[WinAudio] WebSocket error:', err);
            reject(err);
        };

        websocket.onclose = () => {
            stopStreaming();
        };
    });
}

// ── Apple HIG Modal Dialog Controller ─────────────────────────────────────────
const usbModal = document.getElementById('usbModal');
const modalTitle = document.getElementById('modalTitle');
const modalBody = document.getElementById('modalBody');
const modalCloseBtn = document.getElementById('modalCloseBtn');

function showUsbModal(title, bodyHtml) {
    if (!usbModal) {
        alert(bodyHtml ? bodyHtml.replace(/<[^>]*>/g, '') : title);
        return;
    }
    if (modalTitle && title) modalTitle.innerText = title;
    if (modalBody && bodyHtml) modalBody.innerHTML = bodyHtml;
    usbModal.classList.add('active');
    usbModal.setAttribute('aria-hidden', 'false');
}

function closeUsbModal() {
    if (usbModal) {
        usbModal.classList.remove('active');
        usbModal.setAttribute('aria-hidden', 'true');
    }
}

if (modalCloseBtn) {
    modalCloseBtn.addEventListener('click', closeUsbModal);
}
if (usbModal) {
    usbModal.addEventListener('click', (e) => {
        if (e.target === usbModal) closeUsbModal();
    });
}

// ── Screen WakeLock Management ──────────────────────────────────────────────
let wakeLock = null;

async function acquireWakeLock() {
    if ('wakeLock' in navigator) {
        try {
            wakeLock = await navigator.wakeLock.request('screen');
            wakeLock.addEventListener('release', () => { wakeLock = null; });
        } catch (err) {
            console.log('[WinAudio] Screen WakeLock unavailable:', err);
        }
    }
}

function releaseWakeLock() {
    if (wakeLock) {
        wakeLock.release().catch(() => { });
        wakeLock = null;
    }
}

// ── Lifecycle & Visibility Auto-Resume ──────────────────────────────────────
document.addEventListener('visibilitychange', async () => {
    if (document.visibilityState === 'visible') {
        if (audioCtx && audioCtx.state === 'suspended' && isStreaming) {
            try {
                await audioCtx.resume();
            } catch (e) { }
        }
        if (isStreaming && !wakeLock) {
            await acquireWakeLock();
        }
    }
});

// ── Start / Stop Streaming ──────────────────────────────────────────────────
async function startStreaming() {
    if (currentMode === 'usb') {
        const isLocal = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');
        if (!isLocal) {
            showUsbModal(
                'USB Mode Unavailable',
                'USB mode cannot work over Wi-Fi.<br><br>Please connect your phone to PC via USB cable, enable <strong>USB Debugging</strong>, and open <strong>http://localhost:8080</strong>.'
            );
            return;
        }
        const status = await checkUsbStatus();
        if (!status.usb_connected) {
            showUsbModal(
                'No USB Device Detected',
                'USB mode requires an active USB cable connection with <strong>USB Debugging</strong> enabled.'
            );
            return;
        }
    }

    try {
        await initAudioEngine();
        await connectWebSocket();
        await acquireWakeLock();
    } catch (err) {
        console.error('[WinAudio] Streaming start error:', err);
        showUsbModal('Connection Error', 'Could not connect to PC Audio server: ' + err.message);
        stopStreaming();
    }
}

function stopStreaming() {
    isStreaming = false;
    releaseWakeLock();

    if (websocket) {
        try { websocket.close(); } catch (e) { }
        websocket = null;
    }
    nextPlayTime = 0;

    if (statusDot) statusDot.classList.remove('active');
    if (statusTitle) statusTitle.innerText = 'Ready';
    if (statusSub) statusSub.innerText = 'Tap Connect to stream PC audio';
    if (btnText) btnText.innerText = 'Connect';
    if (btnIcon) {
        btnIcon.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" fill="currentColor"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path></svg>`;
    }
    if (toggleBtn) toggleBtn.classList.remove('active');
    const pill = document.querySelector('.fidelity-pill');
    if (pill) pill.classList.remove('active');
    if (bufferVal) bufferVal.innerText = '0.0 ms';
}

// ── Volume Control (Logarithmic Acoustic Curve + Persistence) ───────────────
function setVolume(val, persist = true) {
    if (volumeVal) volumeVal.innerText = `${val}%`;
    if (volumeSlider) {
        volumeSlider.value = val;
        volumeSlider.style.setProperty('--slider-percent', `${val}%`);
    }
    if (gainNode) {
        const acousticGain = Math.pow(val / 100, 2);
        gainNode.gain.setValueAtTime(acousticGain, audioCtx ? audioCtx.currentTime : 0);
    }
    if (persist) {
        localStorage.setItem('winaudio_volume', val);
    }
}

volumeSlider.addEventListener('input', (e) => {
    setVolume(e.target.value, true);
});

// Restore saved volume
const savedVolume = localStorage.getItem('winaudio_volume');
if (savedVolume !== null) {
    setVolume(savedVolume, false);
}

// ── Controls ────────────────────────────────────────────────────────────────
toggleBtn.addEventListener('click', async () => {
    if (!isStreaming) {
        await startStreaming();
    } else {
        stopStreaming();
    }
});

// ── Mode Selector with Direct Mode Connection Switching ─────────────────────
const modeTabs = document.querySelectorAll('.mode-tab');
const modeIndicator = document.getElementById('modeIndicator');

function updateModeIndicator(index) {
    if (!modeIndicator) return;
    modeIndicator.style.transform = `translateX(calc(${index} * 100% + ${index * 4}px))`;
}

modeTabs.forEach(tab => {
    tab.addEventListener('click', async () => {
        const targetMode = tab.getAttribute('data-mode');

        if (targetMode === 'usb') {
            const isLocal = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');
            if (!isLocal) {
                showUsbModal(
                    'USB Mode Unavailable',
                    'USB mode cannot work over Wi-Fi.<br><br>Please connect your phone to PC via USB cable, enable <strong>USB Debugging</strong>, and open <strong>http://localhost:8080</strong>.'
                );
                return;
            }

            const status = await checkUsbStatus();
            if (!status.usb_connected) {
                showUsbModal(
                    'No USB Device Detected',
                    'USB mode requires an active USB cable connection with <strong>USB Debugging</strong> enabled.'
                );
                return;
            }
        }

        modeTabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');

        const idx = parseInt(tab.getAttribute('data-index') || '0', 10);
        updateModeIndicator(idx);

        currentMode = targetMode;

        if (currentMode === 'usb') {
            targetBufferMs = 35;
            if (latencyVal) latencyVal.innerText = '~35 ms';
            setTransportBadge('usb', 'USB');
        } else if (currentMode === 'wifi' || currentMode === 'stable') {
            targetBufferMs = 50;
            if (latencyVal) latencyVal.innerText = '~50 ms';
            setTransportBadge('wifi', 'Wi-Fi');
        }

        if (isStreaming && websocket && websocket.readyState === WebSocket.OPEN) {
            websocket.send(JSON.stringify({ type: 'mode', mode: currentMode }));
        }
    });
});

// Run initial detection
detectAndSetTransportBadge();
