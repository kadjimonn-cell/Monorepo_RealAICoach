import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useLanguage } from '../../i18n/LanguageContext';

// Faithful Canvas-2D port of ellisonleao/clumsy-bird (MIT, MelonJS 2.x).
// Classic physics constants preserved: gravity 0.2/frame, flap tween -72px/50ms,
// pipe speed 5px/frame, pipe frequency 92 frames, gap 176px, ground speed 4px/frame.
// Upgrades: difficulty modes, progressive speed, countdown, pause, day/night sky,
// hit flash, score pop, medals and new-best confetti.

const GAME_W = 900;
const GAME_H = 600;
const GROUND_H = 96;
const GROUND_Y = GAME_H - GROUND_H;
const BIRD_W = 85;
const BIRD_H = 60;
const BIRD_X = 60;
const PIPE_W = 148;
const PIPE_IMG_H = 1664;
const GRAVITY_STEP = 0.2;
const FLAP_DELTA = -72;
const FLAP_MS = 50;
const MAX_ANGLE_UP = -30 * (Math.PI / 180);
const MAX_ANGLE_DOWN = 35 * (Math.PI / 180);
const ASSET_BASE = '/flappy-bird';
const COUNTDOWN_MS = 2100;

export type FlappyDifficulty = 'easy' | 'classic' | 'hard';

const DIFFICULTY_TUNING: Record<FlappyDifficulty, { gap: number; speed: number; freq: number }> = {
  easy: { gap: 212, speed: 4.2, freq: 104 },
  classic: { gap: 176, speed: 5, freq: 92 },
  hard: { gap: 150, speed: 5.6, freq: 84 },
};

export const medalForScore = (score: number): 'none' | 'bronze' | 'silver' | 'gold' | 'diamond' => {
  if (score >= 100) return 'diamond';
  if (score >= 50) return 'gold';
  if (score >= 25) return 'silver';
  if (score >= 10) return 'bronze';
  return 'none';
};

const MEDAL_COLORS: Record<string, string> = {
  bronze: '#cd7f32',
  silver: '#c0c0c0',
  gold: '#fbbf24',
  diamond: '#7dd3fc',
};

type GamePhase = 'loading' | 'error' | 'ready' | 'countdown' | 'playing' | 'paused' | 'dying' | 'gameover';

type Props = {
  onGameOver: (score: number, durationMs: number) => void;
  difficulty?: FlappyDifficulty;
  personalBest?: number;
};

type Pipe = { x: number; gapBottomY: number; scored: boolean };
type Confetto = { x: number; y: number; vx: number; vy: number; color: string; size: number; rot: number; vr: number };

export default function FlappyBirdGame({ onGameOver, difficulty = 'classic', personalBest = 0 }: Props) {
  const { t } = useLanguage();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const mountRef = useRef<any>(null);
  const phaseRef = useRef<GamePhase>('loading');
  const scoreRef = useRef(0);
  const startActionRef = useRef<() => void>(() => {});
  const pauseActionRef = useRef<() => void>(() => {});
  const mutedRef = useRef(false);
  const difficultyRef = useRef<FlappyDifficulty>(difficulty);
  difficultyRef.current = difficulty;
  const personalBestRef = useRef(personalBest);
  personalBestRef.current = personalBest;
  const onGameOverRef = useRef(onGameOver);
  onGameOverRef.current = onGameOver;

  const [phase, setPhase] = useState<GamePhase>('loading');
  const [score, setScore] = useState(0);
  const [lastScore, setLastScore] = useState(0);
  const [lastWasNewBest, setLastWasNewBest] = useState(false);
  const [muted, setMuted] = useState(false);
  const [retryToken, setRetryToken] = useState(0);

  const setPhaseBoth = useCallback((p: GamePhase) => {
    phaseRef.current = p;
    setPhase(p);
  }, []);

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;
    let storedMute = false;
    try { storedMute = window.localStorage?.getItem('flappy_bird_muted') === '1'; } catch { /* ignore */ }
    mutedRef.current = storedMute;
    setMuted(storedMute);
  }, []);

  const toggleMute = useCallback(() => {
    setMuted((prev) => {
      const next = !prev;
      mutedRef.current = next;
      try { window.localStorage?.setItem('flappy_bird_muted', next ? '1' : '0'); } catch { /* ignore */ }
      return next;
    });
  }, []);

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;
    const mountEl: HTMLElement | null = mountRef.current as any;
    if (!mountEl) return;

    let disposed = false;
    setPhaseBoth('loading');

    const canvas = document.createElement('canvas');
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    canvas.style.display = 'block';
    canvas.style.touchAction = 'manipulation';
    canvas.setAttribute('data-testid', 'flappy-bird-canvas');
    mountEl.appendChild(canvas);
    const ctx = canvas.getContext('2d');

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const resize = () => {
      const w = mountEl.clientWidth || GAME_W;
      const h = mountEl.clientHeight || GAME_H;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    };
    resize();
    window.addEventListener('resize', resize);

    const loadImage = (src: string) => new Promise<HTMLImageElement>((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error(src));
      img.src = src;
    });

    const makeAudio = (src: string, volume: number, loop = false) => {
      const audio = new Audio(src);
      audio.volume = volume;
      audio.loop = loop;
      audio.preload = 'auto';
      return audio;
    };

    const sounds = {
      wing: makeAudio(`${ASSET_BASE}/wing.mp3`, 0.5),
      hit: makeAudio(`${ASSET_BASE}/hit.mp3`, 0.5),
      lose: makeAudio(`${ASSET_BASE}/lose.mp3`, 0.5),
      theme: makeAudio(`${ASSET_BASE}/theme.mp3`, 0.25, true),
    };
    const playSound = (name: 'wing' | 'hit' | 'lose') => {
      if (mutedRef.current) return;
      try {
        sounds[name].currentTime = 0;
        void sounds[name].play();
      } catch { /* autoplay restrictions */ }
    };
    const syncTheme = () => {
      try {
        const p = phaseRef.current;
        if (mutedRef.current || (p !== 'playing' && p !== 'ready' && p !== 'countdown')) {
          sounds.theme.pause();
        } else if (sounds.theme.paused) {
          void sounds.theme.play().catch(() => { /* needs gesture */ });
        }
      } catch { /* ignore */ }
    };

    let images: Record<string, HTMLImageElement> = {};
    let rafId = 0;
    let pipes: Pipe[] = [];
    let birdY = 0;
    let birdAngle = 0;
    let gravityForce = GRAVITY_STEP;
    let frameCount = 0;
    let flapStartTs = 0;
    let flapFromY = 0;
    let flapActive = false;
    let groundOffset = 0;
    let dieStartTs = 0;
    let dieFromY = 0;
    let idleTs = 0;
    let runStartTs = 0;
    let lastTs = 0;
    let hidden = false;
    let runCount = 0;
    let nightMode = false;
    let tuning = DIFFICULTY_TUNING.classic;
    let countdownStartTs = 0;
    let pauseStartTs = 0;
    let flashStartTs = -10_000;
    let scorePopTs = -10_000;
    let confetti: Confetto[] = [];
    let confettiStartTs = 0;
    const stars = Array.from({ length: 40 }, () => ({
      x: Math.random() * GAME_W,
      y: Math.random() * (GROUND_Y - 140),
      r: 0.8 + Math.random() * 1.6,
      tw: Math.random() * Math.PI * 2,
    }));

    const speedScale = () => 1 + Math.min(0.36, Math.floor(scoreRef.current / 10) * 0.06);

    const resetWorld = () => {
      pipes = [];
      birdY = GAME_H / 2 - BIRD_H;
      birdAngle = 0;
      gravityForce = GRAVITY_STEP;
      frameCount = 0;
      flapActive = false;
      confetti = [];
      scoreRef.current = 0;
      setScore(0);
    };

    const startRun = () => {
      if (phaseRef.current !== 'ready' && phaseRef.current !== 'gameover') return;
      resetWorld();
      tuning = DIFFICULTY_TUNING[difficultyRef.current] || DIFFICULTY_TUNING.classic;
      runCount += 1;
      nightMode = runCount % 2 === 0;
      countdownStartTs = performance.now();
      setPhaseBoth('countdown');
      syncTheme();
    };
    startActionRef.current = startRun;

    const togglePause = () => {
      const now = performance.now();
      if (phaseRef.current === 'playing') {
        pauseStartTs = now;
        setPhaseBoth('paused');
        syncTheme();
      } else if (phaseRef.current === 'paused') {
        const delta = now - pauseStartTs;
        flapStartTs += delta;
        runStartTs += delta;
        lastTs = 0;
        setPhaseBoth('playing');
        syncTheme();
      }
    };
    pauseActionRef.current = togglePause;

    const flap = () => {
      if (phaseRef.current !== 'playing') return;
      playSound('wing');
      gravityForce = GRAVITY_STEP;
      flapFromY = birdY;
      flapStartTs = performance.now();
      flapActive = true;
      birdAngle = MAX_ANGLE_UP;
    };

    const spawnConfetti = () => {
      const palette = ['#fbbf24', '#34d399', '#60a5fa', '#f472b6', '#fde68a', '#5eead4'];
      confetti = Array.from({ length: 90 }, () => ({
        x: GAME_W / 2 + (Math.random() - 0.5) * 240,
        y: GAME_H / 3 + (Math.random() - 0.5) * 80,
        vx: (Math.random() - 0.5) * 9,
        vy: -4 - Math.random() * 7,
        color: palette[Math.floor(Math.random() * palette.length)],
        size: 5 + Math.random() * 6,
        rot: Math.random() * Math.PI * 2,
        vr: (Math.random() - 0.5) * 0.3,
      }));
      confettiStartTs = performance.now();
    };

    const die = () => {
      if (phaseRef.current !== 'playing') return;
      playSound('lose');
      flashStartTs = performance.now();
      dieStartTs = performance.now();
      dieFromY = birdY;
      setPhaseBoth('dying');
      syncTheme();
    };

    const onPointerDown = (e: Event) => {
      e.preventDefault();
      const p = phaseRef.current;
      if (p === 'ready' || p === 'gameover') startRun();
      else if (p === 'paused') togglePause();
      else flap();
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.code === 'Space') {
        e.preventDefault();
        const p = phaseRef.current;
        if (p === 'ready' || p === 'gameover') startRun();
        else if (p === 'paused') togglePause();
        else flap();
      } else if (e.code === 'KeyM') {
        toggleMute();
      } else if (e.code === 'KeyP') {
        togglePause();
      }
    };
    const onVisibility = () => {
      hidden = document.hidden;
      if (hidden) {
        try { sounds.theme.pause(); } catch { /* ignore */ }
        if (phaseRef.current === 'playing') togglePause();
      } else { lastTs = 0; syncTheme(); }
    };
    canvas.addEventListener('pointerdown', onPointerDown);
    window.addEventListener('keydown', onKeyDown);
    document.addEventListener('visibilitychange', onVisibility);

    const easeExpInOut = (k: number) => {
      if (k === 0) return 0;
      if (k === 1) return 1;
      if ((k *= 2) < 1) return 0.5 * Math.pow(1024, k - 1);
      return 0.5 * (-Math.pow(2, -10 * (k - 1)) + 2);
    };

    const update = (now: number, tick: number) => {
      const p = phaseRef.current;
      if (p === 'ready' || p === 'countdown') {
        idleTs += tick;
        birdY = GAME_H / 2 - BIRD_H + Math.sin(idleTs / 18) * 12;
        groundOffset = (groundOffset + 4 * tick) % images.ground.width;
        if (p === 'countdown' && now - countdownStartTs >= COUNTDOWN_MS) {
          runStartTs = now;
          setPhaseBoth('playing');
          syncTheme();
        }
        return;
      }
      if (p === 'paused') return;
      if (p === 'playing') {
        const scale = speedScale();
        groundOffset = (groundOffset + 4 * scale * tick) % images.ground.width;
        frameCount += tick * scale;

        if (flapActive) {
          const k = Math.min(1, (now - flapStartTs) / FLAP_MS);
          birdY = flapFromY + FLAP_DELTA * easeExpInOut(k);
          if (k >= 1) flapActive = false;
        } else {
          gravityForce += GRAVITY_STEP * tick;
          birdY += tick * gravityForce;
          birdAngle = Math.min(MAX_ANGLE_DOWN, birdAngle + 3 * (Math.PI / 180) * tick);
        }

        if (frameCount >= tuning.freq) {
          frameCount -= tuning.freq;
          const gapBottomY = 200 + Math.random() * (GROUND_Y - 100 - 200);
          pipes.push({ x: GAME_W, gapBottomY, scored: false });
        }
        for (const pipe of pipes) pipe.x -= tuning.speed * scale * tick;
        pipes = pipes.filter((pipe) => pipe.x > -PIPE_W);

        const bx = BIRD_X + 7;
        const by = birdY + 5;
        const bw = BIRD_W - 18;
        const bh = BIRD_H - 12;

        if (birdY <= -80 || by + bh >= GROUND_Y) { die(); return; }

        for (const pipe of pipes) {
          if (!pipe.scored && pipe.x + PIPE_W < BIRD_X) {
            pipe.scored = true;
            scoreRef.current += 1;
            scorePopTs = now;
            setScore(scoreRef.current);
            playSound('hit');
          }
          if (bx < pipe.x + PIPE_W && bx + bw > pipe.x) {
            const gapTop = pipe.gapBottomY - tuning.gap;
            if (by < gapTop || by + bh > pipe.gapBottomY) { die(); return; }
          }
        }
        return;
      }
      if (p === 'dying') {
        const k = Math.min(1, (now - dieStartTs) / 900);
        birdAngle = Math.PI / 2;
        const finalY = GROUND_Y - BIRD_H + 8;
        birdY = dieFromY + (finalY - dieFromY) * easeExpInOut(k);
        if (k >= 1) {
          const finalScore = scoreRef.current;
          const isNewBest = finalScore > 0 && finalScore > personalBestRef.current;
          setLastScore(finalScore);
          setLastWasNewBest(isNewBest);
          if (isNewBest) spawnConfetti();
          setPhaseBoth('gameover');
          onGameOverRef.current(finalScore, Math.max(0, Math.round(performance.now() - runStartTs)));
        }
        return;
      }
      if (p === 'gameover' && confetti.length) {
        for (const c of confetti) {
          c.x += c.vx * tick;
          c.y += c.vy * tick;
          c.vy += 0.25 * tick;
          c.rot += c.vr * tick;
        }
        if (now - confettiStartTs > 3200) confetti = [];
      }
    };

    const draw = (now: number) => {
      if (!ctx) return;
      const scale = Math.min(canvas.width / GAME_W, canvas.height / GAME_H);
      const offsetX = (canvas.width - GAME_W * scale) / 2;
      const offsetY = (canvas.height - GAME_H * scale) / 2;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.fillStyle = nightMode ? '#101c3a' : '#8bd0dc';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.setTransform(scale, 0, 0, scale, offsetX, offsetY);
      ctx.imageSmoothingEnabled = true;

      ctx.drawImage(images.bg, 0, 0, GAME_W, GROUND_Y);
      if (nightMode) {
        ctx.fillStyle = 'rgba(9,14,44,0.52)';
        ctx.fillRect(0, 0, GAME_W, GROUND_Y);
        for (const s of stars) {
          const alpha = 0.45 + 0.4 * Math.abs(Math.sin(now / 900 + s.tw));
          ctx.fillStyle = `rgba(255,255,240,${alpha.toFixed(2)})`;
          ctx.beginPath();
          ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.fillStyle = 'rgba(253,230,138,0.9)';
        ctx.beginPath();
        ctx.arc(GAME_W - 120, 90, 34, 0, Math.PI * 2);
        ctx.fill();
      }

      for (const pipe of pipes) {
        const gapTop = pipe.gapBottomY - tuning.gap;
        ctx.drawImage(images.pipe, pipe.x, pipe.gapBottomY, PIPE_W, PIPE_IMG_H);
        ctx.save();
        ctx.translate(pipe.x + PIPE_W / 2, gapTop);
        ctx.scale(1, -1);
        ctx.drawImage(images.pipe, -PIPE_W / 2, 0, PIPE_W, PIPE_IMG_H);
        ctx.restore();
      }

      const gw = images.ground.width;
      for (let x = -groundOffset; x < GAME_W; x += gw) {
        ctx.drawImage(images.ground, x, GROUND_Y, gw, GROUND_H);
      }

      const animating = phaseRef.current === 'playing' || phaseRef.current === 'ready' || phaseRef.current === 'countdown';
      const frame = animating ? Math.floor(now / 90) % 3 : 0;
      ctx.save();
      ctx.translate(BIRD_X + BIRD_W / 2, birdY + BIRD_H / 2);
      ctx.rotate(birdAngle);
      ctx.drawImage(images.clumsy, frame * BIRD_W, 0, BIRD_W, BIRD_H, -BIRD_W / 2, -BIRD_H / 2, BIRD_W, BIRD_H);
      ctx.restore();

      if (phaseRef.current === 'playing' || phaseRef.current === 'dying' || phaseRef.current === 'paused') {
        const pop = 1 + 0.35 * Math.max(0, 1 - (now - scorePopTs) / 260);
        ctx.save();
        ctx.translate(GAME_W / 2, 110);
        ctx.scale(pop, pop);
        ctx.font = '800 64px system-ui, sans-serif';
        ctx.textAlign = 'center';
        ctx.lineWidth = 8;
        ctx.strokeStyle = 'rgba(0,0,0,0.45)';
        ctx.strokeText(String(scoreRef.current), 0, 0);
        ctx.fillStyle = '#ffffff';
        ctx.fillText(String(scoreRef.current), 0, 0);
        ctx.restore();
      }

      if (phaseRef.current === 'countdown') {
        const elapsed = now - countdownStartTs;
        const step = Math.min(2, Math.floor(elapsed / (COUNTDOWN_MS / 3)));
        const label = String(3 - step);
        const within = (elapsed % (COUNTDOWN_MS / 3)) / (COUNTDOWN_MS / 3);
        const popScale = 1.5 - 0.5 * within;
        ctx.save();
        ctx.translate(GAME_W / 2, GAME_H / 2 - 40);
        ctx.scale(popScale, popScale);
        ctx.font = '900 120px system-ui, sans-serif';
        ctx.textAlign = 'center';
        ctx.lineWidth = 12;
        ctx.strokeStyle = 'rgba(0,0,0,0.5)';
        ctx.strokeText(label, 0, 0);
        ctx.fillStyle = '#fde68a';
        ctx.fillText(label, 0, 0);
        ctx.restore();
      }

      if (confetti.length) {
        for (const c of confetti) {
          ctx.save();
          ctx.translate(c.x, c.y);
          ctx.rotate(c.rot);
          ctx.fillStyle = c.color;
          ctx.fillRect(-c.size / 2, -c.size / 2, c.size, c.size * 0.6);
          ctx.restore();
        }
      }

      const flashAlpha = Math.max(0, 1 - (now - flashStartTs) / 280) * 0.55;
      if (flashAlpha > 0.01) {
        ctx.fillStyle = `rgba(255,255,255,${flashAlpha.toFixed(2)})`;
        ctx.fillRect(0, 0, GAME_W, GAME_H);
      }
    };

    const loop = (now: number) => {
      if (disposed) return;
      rafId = window.requestAnimationFrame(loop);
      if (hidden) { lastTs = 0; return; }
      if (!lastTs) { lastTs = now; return; }
      const tick = Math.min(3, (now - lastTs) / (1000 / 60));
      lastTs = now;
      update(now, tick);
      draw(now);
    };

    Promise.all([
      loadImage(`${ASSET_BASE}/bg.png`),
      loadImage(`${ASSET_BASE}/clumsy.png`),
      loadImage(`${ASSET_BASE}/pipe.png`),
      loadImage(`${ASSET_BASE}/ground.png`),
    ]).then(([bg, clumsy, pipe, ground]) => {
      if (disposed) return;
      images = { bg, clumsy, pipe, ground };
      resetWorld();
      setPhaseBoth('ready');
      rafId = window.requestAnimationFrame(loop);
    }).catch(() => {
      if (!disposed) setPhaseBoth('error');
    });

    return () => {
      disposed = true;
      window.cancelAnimationFrame(rafId);
      window.removeEventListener('resize', resize);
      window.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('visibilitychange', onVisibility);
      canvas.removeEventListener('pointerdown', onPointerDown);
      Object.values(sounds).forEach((audio) => { try { audio.pause(); audio.src = ''; } catch { /* ignore */ } });
      if (canvas.parentElement === mountEl) mountEl.removeChild(canvas);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [retryToken]);

  if (Platform.OS !== 'web') {
    return (
      <View style={styles.unsupported} data-testid="flappy-bird-unsupported" testID="flappy-bird-unsupported">
        <Text style={styles.unsupportedText}>{tx('flappyBird.game.webOnly', 'The Flappy Bird game is available on the web version of RealAICoach.')}</Text>
      </View>
    );
  }

  const lastMedal = medalForScore(lastScore);

  return (
    <View style={styles.frame} data-testid="flappy-bird-game-frame" testID="flappy-bird-game-frame">
      <View ref={mountRef} style={styles.mount} />

      {phase === 'loading' && (
        <View style={styles.overlay} data-testid="flappy-bird-loading" testID="flappy-bird-loading">
          <ActivityIndicator size="large" color="#ffffff" />
          <Text style={styles.overlayText}>{tx('flappyBird.game.loading', 'Loading game assets…')}</Text>
        </View>
      )}

      {phase === 'error' && (
        <View style={styles.overlay} data-testid="flappy-bird-asset-error" testID="flappy-bird-asset-error">
          <Ionicons name="cloud-offline-outline" size={34} color="#fca5a5" />
          <Text style={styles.overlayText}>{tx('flappyBird.game.assetError', 'Game assets failed to load. Check your connection and try again.')}</Text>
          <Pressable
            onPress={() => setRetryToken((v) => v + 1)}
            style={styles.primaryBtn}
            data-testid="flappy-bird-retry-button" testID="flappy-bird-retry-button"
          >
            <Ionicons name="refresh" size={16} color={'#0f172a' /* @theme-ok fixed-dark-canvas */} />
            <Text style={styles.primaryBtnText}>{tx('flappyBird.game.retry', 'Retry')}</Text>
          </Pressable>
        </View>
      )}

      {phase === 'ready' && (
        <View style={styles.overlay} data-testid="flappy-bird-get-ready" testID="flappy-bird-get-ready">
          <Text style={styles.bigTitle}>{tx('flappyBird.game.getReady', 'Get Ready!')}</Text>
          <Text style={styles.overlayText}>{tx('flappyBird.game.startHint', 'Tap, click or press Space to flap. Avoid the pipes!')}</Text>
          <Pressable
            onPress={() => startActionRef.current()}
            style={styles.primaryBtn}
            data-testid="flappy-bird-start-button" testID="flappy-bird-start-button"
          >
            <Ionicons name="play" size={16} color={'#0f172a' /* @theme-ok fixed-dark-canvas */} />
            <Text style={styles.primaryBtnText}>{tx('flappyBird.game.start', 'Start Game')}</Text>
          </Pressable>
        </View>
      )}

      {phase === 'paused' && (
        <View style={styles.overlay} data-testid="flappy-bird-paused" testID="flappy-bird-paused">
          <Ionicons name="pause-circle-outline" size={44} color={'#fde68a' /* @theme-ok fixed-dark-canvas */} />
          <Text style={styles.bigTitle}>{tx('flappyBird.game.paused', 'Paused')}</Text>
          <Text style={styles.overlayText}>{tx('flappyBird.game.resumeHint', 'Press P or tap the game to resume.')}</Text>
        </View>
      )}

      {phase === 'gameover' && (
        <View style={styles.overlay} data-testid="flappy-bird-game-over" testID="flappy-bird-game-over">
          <Text style={styles.bigTitle}>{tx('flappyBird.game.gameOver', 'Game Over')}</Text>
          <Text style={styles.scoreLine} data-testid="flappy-bird-final-score" testID="flappy-bird-final-score">
            {tx('flappyBird.game.score', 'Score')}: {lastScore}
          </Text>
          {lastMedal !== 'none' && (
            <View style={styles.medalRow} data-testid="flappy-bird-medal" testID="flappy-bird-medal">
              <Ionicons name="medal" size={22} color={MEDAL_COLORS[lastMedal] /* @theme-ok fixed-dark-canvas */} />
              <Text style={[styles.medalText, { color: MEDAL_COLORS[lastMedal] /* @theme-ok fixed-dark-canvas */ }]}>
                {lastMedal === 'diamond' ? tx('flappyBird.game.medalDiamond', 'Diamond medal!')
                  : lastMedal === 'gold' ? tx('flappyBird.game.medalGold', 'Gold medal!')
                  : lastMedal === 'silver' ? tx('flappyBird.game.medalSilver', 'Silver medal!')
                  : tx('flappyBird.game.medalBronze', 'Bronze medal!')}
              </Text>
            </View>
          )}
          {lastWasNewBest && (
            <Text style={styles.newBestText} data-testid="flappy-bird-new-best-label" testID="flappy-bird-new-best-label">
              {tx('flappyBird.game.newBest', 'New personal best!')}
            </Text>
          )}
          <Pressable
            onPress={() => startActionRef.current()}
            style={styles.primaryBtn}
            data-testid="flappy-bird-restart-button" testID="flappy-bird-restart-button"
          >
            <Ionicons name="refresh" size={16} color={'#0f172a' /* @theme-ok fixed-dark-canvas */} />
            <Text style={styles.primaryBtnText}>{tx('flappyBird.game.playAgain', 'Play Again')}</Text>
          </Pressable>
        </View>
      )}

      <View style={styles.topRightControls}>
        {(phase === 'playing' || phase === 'paused') && (
          <Pressable
            onPress={() => pauseActionRef.current()}
            style={styles.ctrlBtn}
            accessibilityRole="button"
            accessibilityLabel={phase === 'paused' ? tx('flappyBird.game.resume', 'Resume game') : tx('flappyBird.game.pause', 'Pause game')}
            data-testid="flappy-bird-pause-button" testID="flappy-bird-pause-button"
          >
            <Ionicons name={phase === 'paused' ? 'play' : 'pause'} size={18} color={'#ffffff' /* @theme-ok fixed-dark-canvas */} />
          </Pressable>
        )}
        <Pressable
          onPress={toggleMute}
          style={styles.ctrlBtn}
          accessibilityRole="button"
          accessibilityLabel={muted ? tx('flappyBird.game.unmute', 'Unmute sound') : tx('flappyBird.game.mute', 'Mute sound')}
          data-testid="flappy-bird-mute-button" testID="flappy-bird-mute-button"
        >
          <Ionicons name={muted ? 'volume-mute' : 'volume-high'} size={18} color={'#ffffff' /* @theme-ok fixed-dark-canvas */} />
        </Pressable>
      </View>

      {(phase === 'playing' || phase === 'paused') && (
        <View style={styles.liveScoreBadge} pointerEvents="none" data-testid="flappy-bird-live-score" testID="flappy-bird-live-score">
          <Text style={styles.liveScoreText}>{score}</Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  frame: { width: '100%', maxWidth: 960, alignSelf: 'center', aspectRatio: 3 / 2, borderRadius: 16, overflow: 'hidden', backgroundColor: '#8bd0dc' /* @theme-ok fixed-dark-canvas */, position: 'relative' },
  mount: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 },
  overlay: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, alignItems: 'center', justifyContent: 'center', gap: 14, backgroundColor: 'rgba(15,23,42,0.55)', paddingHorizontal: 24 },
  overlayText: { color: 'rgba(255,255,255,0.92)', fontSize: 14, textAlign: 'center', maxWidth: 420 },
  bigTitle: { color: '#ffffff' /* @theme-ok fixed-dark-canvas */, fontSize: 34, fontWeight: '900', textAlign: 'center' },
  scoreLine: { color: '#fde68a' /* @theme-ok fixed-dark-canvas */, fontSize: 20, fontWeight: '800' },
  medalRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  medalText: { fontSize: 16, fontWeight: '900' },
  newBestText: { color: '#6ee7b7' /* @theme-ok fixed-dark-canvas */, fontSize: 15, fontWeight: '900' },
  primaryBtn: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: '#fde68a' /* @theme-ok fixed-dark-canvas */, borderRadius: 999, paddingHorizontal: 22, paddingVertical: 12 },
  primaryBtnText: { color: '#0f172a' /* @theme-ok fixed-dark-canvas */, fontWeight: '800', fontSize: 15 },
  topRightControls: { position: 'absolute', top: 12, right: 12, flexDirection: 'row', gap: 8 },
  ctrlBtn: { width: 38, height: 38, borderRadius: 999, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(15,23,42,0.55)' },
  liveScoreBadge: { position: 'absolute', top: 12, left: 12, backgroundColor: 'rgba(15,23,42,0.55)', borderRadius: 999, paddingHorizontal: 14, paddingVertical: 6 },
  liveScoreText: { color: '#ffffff' /* @theme-ok fixed-dark-canvas */, fontWeight: '900', fontSize: 18 },
  unsupported: { padding: 24, alignItems: 'center' },
  unsupportedText: { fontSize: 14, textAlign: 'center', color: '#64748b' /* @theme-ok fixed-dark-canvas */ },
});
