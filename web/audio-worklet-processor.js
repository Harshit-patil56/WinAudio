// WinAudio AudioWorklet Processor — Dynamic Micro Time-Stretching & Low-Latency Ring Buffer
// - SPSC Circular Ring Buffer (48kHz Stereo)
// - Dynamic Micro Time-Stretching (1.00x – 1.045x smooth drift absorption without pitch clicks)
// - High-Performance Int16 to Float32 conversion on audio thread
// - Mode-dependent target delays (20ms USB / 35ms Wi-Fi / 70ms High Stability)

class WinAudioWorkletProcessor extends AudioWorkletProcessor {
    constructor() {
        super();

        this.SAMPLE_RATE = 48000;
        this.targetSamples = Math.floor(this.SAMPLE_RATE * 0.020); // 20ms default
        this.maxSamples = Math.floor(this.SAMPLE_RATE * 0.120); // 120ms hard catchup limit
        this.CAPACITY = Math.floor(this.SAMPLE_RATE * 0.500); // 500ms ring buffer

        this.ringL = new Float32Array(this.CAPACITY);
        this.ringR = new Float32Array(this.CAPACITY);
        this.writeIdx = 0;
        this.readPos = 0.0; // Fractional read position for smooth time-stretching

        this.primed = false;
        this.underruns = 0;
        this.reportCounter = 0;
        this.currentSpeed = 1.000;

        this.port.onmessage = (event) => {
            const data = event.data;
            if (data instanceof ArrayBuffer) {
                this._pushInt16PCM(new Int16Array(data));
            } else if (data && data.buffer instanceof ArrayBuffer) {
                this._pushInt16PCM(new Int16Array(data.buffer));
            } else if (data && data.type === 'SET_TARGET_MS') {
                const targetMs = data.targetMs || 20;
                this.targetSamples = Math.floor(this.SAMPLE_RATE * (targetMs / 1000));
                this.maxSamples = Math.floor(this.SAMPLE_RATE * Math.max(0.080, targetMs * 2.5 / 1000));
                this.primed = false;
            } else if (data && data.type === 'RESET') {
                this._reset();
            }
        };
    }

    _reset() {
        this.writeIdx = 0;
        this.readPos = 0.0;
        this.primed = false;
        this.ringL.fill(0);
        this.ringR.fill(0);
    }

    _getAvailable() {
        const wi = this.writeIdx;
        const ri = Math.floor(this.readPos);
        return (wi - ri + this.CAPACITY) % this.CAPACITY;
    }

    _pushInt16PCM(int16) {
        const numSamples = int16.length / 2;
        const cap = this.CAPACITY;
        let wi = this.writeIdx;

        for (let i = 0; i < numSamples; i++) {
            this.ringL[wi] = int16[i * 2] / 32768.0;
            this.ringR[wi] = int16[i * 2 + 1] / 32768.0;
            wi = (wi + 1) % cap;
        }
        this.writeIdx = wi;
    }

    process(inputs, outputs) {
        const output = outputs[0];
        if (!output || output.length === 0) return true;

        const outL = output[0];
        const outR = output.length > 1 ? output[1] : null;
        const need = outL.length; // 128 frames
        const cap = this.CAPACITY;

        let available = this._getAvailable();

        // 1. Initial Priming Gate
        if (!this.primed) {
            if (available >= this.targetSamples) {
                this.primed = true;
                this.readPos = (this.writeIdx - this.targetSamples + cap) % cap;
            } else {
                outL.fill(0);
                if (outR) outR.fill(0);
                this._sendStats(available, 1.0);
                return true;
            }
        }

        // 2. Emergency Hard-Seek (if network packet stall accumulated > maxSamples)
        if (available > this.maxSamples) {
            this.readPos = (this.writeIdx - this.targetSamples + cap) % cap;
            available = this._getAvailable();
        }

        // 3. Dynamic Micro Time-Stretching (Fractional Resampling Speed Calculation)
        // If buffer depth is higher than target, speed up subtly (1.01x – 1.040x) to catch up
        // If buffer depth is lower than target, slow down subtly (0.970x – 0.99x) to prevent underruns
        const bufferDiff = available - this.targetSamples;
        const span = Math.max(960, Math.floor(this.targetSamples * 0.8));
        let targetSpeed = 1.000;

        if (bufferDiff > 48) { // More than ~1ms ahead of target
            targetSpeed = 1.000 + Math.min(0.040, ((bufferDiff - 48) / span) * 0.040);
        } else if (bufferDiff < -48) { // Falling behind target
            targetSpeed = 1.000 - Math.min(0.030, ((Math.abs(bufferDiff) - 48) / span) * 0.030);
        }

        // Smooth speed transitions (inertia prevents sudden pitch waver)
        this.currentSpeed += (targetSpeed - this.currentSpeed) * 0.065;

        // 4. Fractional Sample Interpolation Playback with Safe Underrun Protection
        if (available >= need) {
            let rPos = this.readPos;
            const speed = this.currentSpeed;

            for (let i = 0; i < need; i++) {
                const i0 = Math.floor(rPos) % cap;
                const i1 = (i0 + 1) % cap;
                const frac = rPos - Math.floor(rPos);

                const sL = (1.0 - frac) * this.ringL[i0] + frac * this.ringL[i1];
                const sR = (1.0 - frac) * this.ringR[i0] + frac * this.ringR[i1];

                outL[i] = sL;
                if (outR) {
                    outR[i] = sR;
                } else {
                    outL[i] = (sL + sR) * 0.5;
                }

                rPos += speed;
                if (rPos >= cap) {
                    rPos -= cap;
                }
            }
            this.readPos = rPos;
        } else if (available >= 2) {
            // Graceful partial playback: render valid frames, zero-fill remainder to avoid clicks
            let rPos = this.readPos;
            const speed = this.currentSpeed;
            const playable = Math.min(need, Math.floor(available));

            for (let i = 0; i < playable; i++) {
                const i0 = Math.floor(rPos) % cap;
                const i1 = (i0 + 1) % cap;
                const frac = rPos - Math.floor(rPos);

                outL[i] = (1.0 - frac) * this.ringL[i0] + frac * this.ringL[i1];
                if (outR) {
                    outR[i] = (1.0 - frac) * this.ringR[i0] + frac * this.ringR[i1];
                }

                rPos += speed;
                if (rPos >= cap) {
                    rPos -= cap;
                }
            }
            for (let i = playable; i < need; i++) {
                outL[i] = 0;
                if (outR) outR[i] = 0;
            }
            this.readPos = rPos;
        } else {
            // Buffer Underrun
            outL.fill(0);
            if (outR) outR.fill(0);
            this.underruns++;
            this.primed = false;
        }

        // 5. Periodic UI Stats Telemetry (~100ms interval)
        this._sendStats(available, this.currentSpeed);

        return true;
    }

    _sendStats(available, speed) {
        this.reportCounter = (this.reportCounter || 0) + 1;
        if (this.reportCounter >= 38) {
            this.reportCounter = 0;
            const bufferedMs = (available / this.SAMPLE_RATE) * 1000;
            this.port.postMessage({
                type: 'STATS',
                bufferedMs: Math.max(0, bufferedMs),
                speed: speed,
                underruns: this.underruns
            });
        }
    }
}

registerProcessor('winaudio-stream-processor', WinAudioWorkletProcessor);
