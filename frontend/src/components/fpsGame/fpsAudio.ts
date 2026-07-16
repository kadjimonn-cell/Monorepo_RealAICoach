/* Procedurally synthesized game audio via Web Audio — no asset downloads. */

type SoundName = 'gunshot' | 'hit' | 'kill' | 'damage' | 'death' | 'respawn' | 'streak' | 'chat';

class FpsAudioEngine {
  private ctx: AudioContext | null = null;
  private noiseBuffer: AudioBuffer | null = null;
  muted = false;

  constructor() {
    if (typeof window !== 'undefined') {
      this.muted = window.localStorage?.getItem('fps_muted') === '1';
    }
  }

  ensure(): void {
    if (typeof window === 'undefined') return;
    if (!this.ctx) {
      const Ctx = (window as any).AudioContext || (window as any).webkitAudioContext;
      if (!Ctx) return;
      this.ctx = new Ctx();
      const sr = this.ctx!.sampleRate;
      this.noiseBuffer = this.ctx!.createBuffer(1, sr * 0.25, sr);
      const data = this.noiseBuffer.getChannelData(0);
      for (let i = 0; i < data.length; i += 1) data[i] = Math.random() * 2 - 1;
    }
    if (this.ctx && this.ctx.state === 'suspended') this.ctx.resume();
  }

  toggleMute(): boolean {
    this.muted = !this.muted;
    if (typeof window !== 'undefined') window.localStorage?.setItem('fps_muted', this.muted ? '1' : '0');
    return this.muted;
  }

  private tone(freq: number, start: number, dur: number, gain: number, type: OscillatorType = 'sine', glideTo?: number): void {
    const ctx = this.ctx!;
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = type;
    const t0 = ctx.currentTime + start;
    osc.frequency.setValueAtTime(freq, t0);
    if (glideTo) osc.frequency.exponentialRampToValueAtTime(glideTo, t0 + dur);
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(gain, t0 + 0.008);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    osc.connect(g); g.connect(ctx.destination);
    osc.start(t0); osc.stop(t0 + dur + 0.02);
  }

  private noise(start: number, dur: number, gain: number, filterFreq: number): void {
    const ctx = this.ctx!;
    if (!this.noiseBuffer) return;
    const src = ctx.createBufferSource();
    src.buffer = this.noiseBuffer;
    const filter = ctx.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.value = filterFreq;
    const g = ctx.createGain();
    const t0 = ctx.currentTime + start;
    g.gain.setValueAtTime(gain, t0);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    src.connect(filter); filter.connect(g); g.connect(ctx.destination);
    src.start(t0); src.stop(t0 + dur + 0.02);
  }

  play(name: SoundName): void {
    if (this.muted) return;
    this.ensure();
    if (!this.ctx) return;
    switch (name) {
      case 'gunshot':
        this.noise(0, 0.09, 0.35, 2200);
        this.tone(160, 0, 0.07, 0.25, 'square', 60);
        break;
      case 'hit':
        this.tone(880, 0, 0.07, 0.22, 'sine', 1320);
        break;
      case 'kill':
        this.tone(523, 0, 0.1, 0.25, 'triangle');
        this.tone(784, 0.09, 0.14, 0.28, 'triangle');
        break;
      case 'damage':
        this.tone(120, 0, 0.12, 0.3, 'sawtooth', 70);
        this.noise(0, 0.08, 0.12, 500);
        break;
      case 'death':
        this.tone(330, 0, 0.4, 0.28, 'sawtooth', 90);
        break;
      case 'respawn':
        this.tone(660, 0, 0.12, 0.2, 'sine');
        this.tone(990, 0.11, 0.18, 0.22, 'sine');
        break;
      case 'streak':
        this.tone(523, 0, 0.09, 0.26, 'square');
        this.tone(659, 0.09, 0.09, 0.26, 'square');
        this.tone(880, 0.18, 0.2, 0.3, 'square');
        break;
      case 'chat':
        this.tone(740, 0, 0.05, 0.12, 'sine');
        break;
      default:
        break;
    }
  }
}

export const fpsAudio = new FpsAudioEngine();
