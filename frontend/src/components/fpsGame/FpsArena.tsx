import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as THREE from 'three';

import api from '../../services/api';
import { useLanguage } from '../../i18n/LanguageContext';
import { buildMap, makeAk47, makeCharacter, makeNameTag, makeSky, type CharacterRig, type Collider } from './fpsAssets';
import { fpsAudio } from './fpsAudio';

type Props = {
  roomId: string;
  roomName: string;
  userId: string;
  playerName: string;
  model: string;
  onExit: () => void;
};

type FeedItem = { id: number; text: string };

const ARENA_HALF = 28;
const EYE_HEIGHT = 1.7;

export default function FpsArena({ roomId, roomName, userId, playerName, model, onExit }: Props) {
  const { t } = useLanguage();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const mountRef = useRef<any>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const cleanupRef = useRef<() => void>(() => {});
  const feedIdRef = useRef(0);

  const [hp, setHp] = useState(100);
  const [kills, setKills] = useState(0);
  const [deaths, setDeaths] = useState(0);
  const [playersOnline, setPlayersOnline] = useState(1);
  const [connected, setConnected] = useState(false);
  const [dead, setDead] = useState(false);
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [damageFlash, setDamageFlash] = useState(false);
  const [hitMarker, setHitMarker] = useState(false);
  const [unsupported, setUnsupported] = useState(false);
  const [streakBanner, setStreakBanner] = useState('');
  const [myStreak, setMyStreak] = useState(0);
  const [muted, setMuted] = useState(fpsAudio.muted);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatText, setChatText] = useState('');
  const [showScoreboard, setShowScoreboard] = useState(false);
  const [inviteCopied, setInviteCopied] = useState(false);
  const [scoreRows, setScoreRows] = useState<Array<{ uid: string; name: string; kills: number; deaths: number }>>([]);
  const chatOpenRef = useRef(false);
  const scoresRef = useRef(new Map<string, { name: string; kills: number; deaths: number }>());

  const syncScores = useCallback(() => {
    const rows = Array.from(scoresRef.current.entries()).map(([uid, s]) => ({ uid, ...s }));
    rows.sort((a, b) => b.kills - a.kills);
    setScoreRows(rows);
  }, []);

  const copyInvite = useCallback(() => {
    const url = `${window.location.origin}/features/fps-game?room=${encodeURIComponent(roomName)}`;
    navigator.clipboard?.writeText(url).then(() => {
      setInviteCopied(true);
      setTimeout(() => setInviteCopied(false), 2000);
    }).catch(() => { /* clipboard unavailable */ });
    (document.activeElement as HTMLElement | null)?.blur?.();
  }, [roomName]);

  const touchStateRef = useRef({ fire: false, jump: false, moveX: 0, moveY: 0 });

  const pushFeed = useCallback((text: string) => {
    feedIdRef.current += 1;
    const item = { id: feedIdRef.current, text };
    setFeed((prev) => [...prev.slice(-5), item]);
  }, []);

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof document === 'undefined') {
      setUnsupported(true);
      return;
    }
    const mountEl: HTMLElement | null = mountRef.current as any;
    if (!mountEl) return;

    let disposed = false;
    const isTouch = typeof window !== 'undefined' && ('ontouchstart' in window || navigator.maxTouchPoints > 0);

    // ── Scene ──
    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog(0x101c2c, 38, 115);
    scene.add(makeSky());
    const camera = new THREE.PerspectiveCamera(75, 1, 0.1, 200);
    camera.position.set(0, EYE_HEIGHT, 0);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    mountEl.appendChild(renderer.domElement);
    renderer.domElement.style.width = '100%';
    renderer.domElement.style.height = '100%';
    renderer.domElement.style.display = 'block';

    const resize = () => {
      const w = mountEl.clientWidth || 800;
      const h = mountEl.clientHeight || 520;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    resize();
    window.addEventListener('resize', resize);

    scene.add(new THREE.HemisphereLight(0x9db4d4, 0x2a3626, 0.85));
    const sun = new THREE.DirectionalLight(0xffe0b0, 1.25);
    sun.position.set(20, 40, 10);
    scene.add(sun);

    // World: textured floor/walls/crates, central structure, barriers, accent lights
    const colliders: Collider[] = buildMap(scene, ARENA_HALF);

    // AK-47 viewmodel (bottom-right, as in the source game)
    const { group: gunGroup, muzzleFlash, flashLight } = makeAk47();
    gunGroup.position.set(0.32, -0.3, -0.55);
    camera.add(gunGroup);
    scene.add(camera);

    // ── State ──
    const remotes = new Map<string, { group: THREE.Group; target: THREE.Vector3; yaw: number; rig: CharacterRig; walkPhase: number; prevPos: THREE.Vector3 }>();
    const keys: Record<string, boolean> = {};
    let yaw = 0, pitch = 0;
    const velocity = new THREE.Vector3();
    const position = new THREE.Vector3(0, EYE_HEIGHT, 0);
    let onGround = true;
    let alive = true;
    let pointerLocked = false;
    let fireHeld = false;
    let lastShot = 0;
    const raycaster = new THREE.Raycaster();
    const tracers: Array<{ line: THREE.Line; born: number }> = [];
    const sparks: Array<{ mesh: THREE.Mesh; born: number }> = [];

    const spawnRemote = (p: any) => {
      if (remotes.has(p.user_id) || p.user_id === userId) return;
      const rig = makeCharacter(String(p.model || 'policeman'));
      rig.group.add(makeNameTag(String(p.name || 'Player')));
      rig.group.traverse((child) => { child.userData.ownerId = p.user_id; });
      rig.group.position.set(p.pos?.[0] ?? 0, 0, p.pos?.[2] ?? 0);
      rig.healthFill.scale.x = 0.88 * (Math.max(0, Math.min(100, Number(p.hp ?? 100))) / 100);
      scene.add(rig.group);
      remotes.set(p.user_id, {
        group: rig.group,
        rig,
        walkPhase: 0,
        prevPos: rig.group.position.clone(),
        target: new THREE.Vector3(p.pos?.[0] ?? 0, 0, p.pos?.[2] ?? 0),
        yaw: p.rot?.[0] ?? 0,
      });
    };
    const removeRemote = (uid: string) => {
      const entry = remotes.get(uid);
      if (entry) { scene.remove(entry.group); remotes.delete(uid); }
    };

    // ── WebSocket (Photon replacement) — auto-reconnect (preview proxy caps WS lifetime) ──
    let stateTimer: ReturnType<typeof setInterval> | null = null;
    let keepAliveTimer: ReturnType<typeof setInterval> | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let reconnectAttempts = 0;
    const connectWs = async () => {
      try {
        const ticketResp = await api.post('/auth/ws-ticket', { channel: 'fps_game' });
        const ticket = String(ticketResp?.data?.ticket || '').trim();
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const ws = new WebSocket(`${protocol}//${window.location.host}/api/ws/fps/${roomId}/${userId}?ticket=${encodeURIComponent(ticket)}`);
        wsRef.current = ws;
        ws.onopen = () => { if (!disposed) { setConnected(true); reconnectAttempts = 0; } };
        ws.onclose = () => {
          if (disposed) return;
          setConnected(false);
          if (reconnectAttempts < 20) {
            reconnectAttempts += 1;
            if (reconnectAttempts === 1) pushFeed(tx('fpsGame.arena.reconnecting', 'Reconnecting...'));
            reconnectTimer = setTimeout(() => { connectWs(); }, 900);
          } else {
            pushFeed(tx('fpsGame.arena.connectionLost', 'Connection lost — leave and rejoin'));
          }
        };
        ws.onmessage = (event) => {
          if (disposed) return;
          let msg: any;
          try { msg = JSON.parse(event.data); } catch { return; }
          switch (msg.type) {
            case 'joined': {
              remotes.forEach((entry) => scene.remove(entry.group));
              remotes.clear();
              scoresRef.current.clear();
              (msg.players || []).forEach((p: any) => {
                spawnRemote(p);
                scoresRef.current.set(p.user_id, { name: String(p.name || 'Player'), kills: Number(p.kills || 0), deaths: Number(p.deaths || 0) });
              });
              setPlayersOnline((msg.players || []).length + 1);
              const selfState = msg.self || {};
              scoresRef.current.set(userId, { name: String(selfState.name || playerName), kills: Number(selfState.kills ?? 0), deaths: Number(selfState.deaths ?? 0) });
              syncScores();
              setHp(Number(selfState.hp ?? 100));
              setKills(Number(selfState.kills ?? 0));
              setDeaths(Number(selfState.deaths ?? 0));
              alive = selfState.alive !== false;
              setDead(!alive);
              if (!msg.resumed) pushFeed(tx('fpsGame.arena.feedYouJoined', 'You joined the room'));
              break;
            }
            case 'player_joined':
              spawnRemote(msg.player);
              scoresRef.current.set(msg.player.user_id, { name: String(msg.player.name || 'Player'), kills: Number(msg.player.kills || 0), deaths: Number(msg.player.deaths || 0) });
              syncScores();
              setPlayersOnline(remotes.size + 1);
              pushFeed(`${msg.player?.name || 'Player'} ${tx('fpsGame.arena.feedJoined', 'joined the room')}`);
              break;
            case 'player_left':
              removeRemote(msg.user_id);
              scoresRef.current.delete(msg.user_id);
              syncScores();
              setPlayersOnline(remotes.size + 1);
              pushFeed(`${msg.name || 'Player'} ${tx('fpsGame.arena.feedLeft', 'left the room')}`);
              break;
            case 'state': {
              const entry = remotes.get(msg.user_id);
              if (entry) {
                entry.target.set(msg.pos?.[0] ?? 0, 0, msg.pos?.[2] ?? 0);
                entry.yaw = msg.rot?.[0] ?? 0;
              }
              break;
            }
            case 'damage': {
              if (msg.target_id === userId) {
                setHp(Math.max(0, Number(msg.hp) || 0));
                setDamageFlash(true);
                setTimeout(() => { if (!disposed) setDamageFlash(false); }, 200);
              } else {
                const entry = remotes.get(msg.target_id);
                if (entry) entry.rig.healthFill.scale.x = 0.88 * (Math.max(0, Number(msg.hp) || 0) / 100);
              }
              if (msg.target_id === userId) fpsAudio.play('damage');
              break;
            }
            case 'kill': {
              pushFeed(`${msg.killer_name} ${tx('fpsGame.arena.feedEliminated', 'eliminated')} ${msg.victim_name}`);
              const killerScore = scoresRef.current.get(msg.killer_id);
              if (killerScore) killerScore.kills = Number(msg.killer_kills) || killerScore.kills + 1;
              const victimScore = scoresRef.current.get(msg.victim_id);
              if (victimScore) victimScore.deaths = Number(msg.victim_deaths) || victimScore.deaths + 1;
              syncScores();
              if (msg.killer_id === userId) {
                setKills(Number(msg.killer_kills) || 0);
                setMyStreak(Number(msg.streak) || 0);
                fpsAudio.play('kill');
                if (msg.milestone) {
                  setStreakBanner(tx(`fpsGame.streak.${msg.milestone}`, String(msg.milestone).replace('_', ' ').toUpperCase()));
                  fpsAudio.play('streak');
                  setTimeout(() => { if (!disposed) setStreakBanner(''); }, 2300);
                }
              }
              if (msg.victim_id === userId) {
                alive = false;
                setDead(true);
                setDeaths(Number(msg.victim_deaths) || 0);
                setMyStreak(0);
                fpsAudio.play('death');
              }
              if (msg.victim_id !== userId) {
                const entry = remotes.get(msg.victim_id);
                if (entry) entry.group.visible = false;
              }
              break;
            }
            case 'respawn':
              if (msg.user_id === userId) {
                position.set(msg.pos?.[0] ?? 0, EYE_HEIGHT, msg.pos?.[2] ?? 0);
                velocity.set(0, 0, 0);
                alive = true;
                setDead(false);
                setHp(Number(msg.hp) || 100);
                fpsAudio.play('respawn');
                pushFeed(tx('fpsGame.arena.feedRespawned', 'You respawned'));
              } else {
                const entry = remotes.get(msg.user_id);
                if (entry) {
                  entry.group.visible = true;
                  entry.rig.healthFill.scale.x = 0.88;
                  entry.target.set(msg.pos?.[0] ?? 0, 0, msg.pos?.[2] ?? 0);
                  entry.group.position.copy(entry.target);
                }
              }
              break;
            case 'chat':
              pushFeed(`${msg.name}: ${msg.text}`);
              fpsAudio.play('chat');
              break;
            default:
              break;
          }
        };
      } catch {
        if (!disposed) setConnected(false);
      }
    };
    connectWs();
    stateTimer = setInterval(() => {
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN && alive) {
        ws.send(JSON.stringify({ type: 'state', pos: [position.x, position.y, position.z], rot: [yaw, pitch] }));
      }
    }, 80);
    keepAliveTimer = setInterval(() => {
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, 20000);

    // ── Input ──
    const canvas = renderer.domElement;
    const onCanvasClick = () => {
      fpsAudio.ensure();
      if (!isTouch && !pointerLocked) canvas.requestPointerLock?.();
    };
    const onPointerLockChange = () => { pointerLocked = document.pointerLockElement === canvas; };
    const onMouseMove = (e: MouseEvent) => {
      if (!pointerLocked) return;
      // clamp: Chrome pointer-lock can emit huge spurious movement spikes on lock/click
      const mx = Math.abs(e.movementX) > 200 ? 0 : e.movementX;
      const my = Math.abs(e.movementY) > 200 ? 0 : e.movementY;
      yaw -= mx * 0.0022;
      pitch = Math.max(-1.45, Math.min(1.45, pitch - my * 0.0022));
    };
    const onKey = (e: KeyboardEvent, down: boolean) => {
      if (chatOpenRef.current) {
        if (down && e.code === 'Escape') { chatOpenRef.current = false; setChatOpen(false); }
        return;
      }
      if (e.code === 'Tab') {
        e.preventDefault();
        setShowScoreboard(down);
        return;
      }
      if (down && e.code === 'Enter') {
        (document.activeElement as HTMLElement | null)?.blur?.();
        chatOpenRef.current = true;
        setChatOpen(true);
        return;
      }
      keys[e.code] = down;
      if (down && e.code === 'Escape' && document.pointerLockElement === canvas) {
        document.exitPointerLock?.();
      }
    };
    const onKeyDown = (e: KeyboardEvent) => onKey(e, true);
    const onKeyUp = (e: KeyboardEvent) => onKey(e, false);
    const onMouseDown = (e: MouseEvent) => { if (e.button === 0 && pointerLocked) fireHeld = true; };
    const onMouseUp = (e: MouseEvent) => { if (e.button === 0) fireHeld = false; };

    canvas.addEventListener('click', onCanvasClick);
    document.addEventListener('pointerlockchange', onPointerLockChange);
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('keyup', onKeyUp);
    document.addEventListener('mousedown', onMouseDown);
    document.addEventListener('mouseup', onMouseUp);

    // Touch look (right half drag)
    let lookTouchId: number | null = null;
    let lastTouchX = 0, lastTouchY = 0;
    let moveTouchId: number | null = null;
    let moveStartX = 0, moveStartY = 0;
    const onTouchStart = (e: TouchEvent) => {
      for (const touch of Array.from(e.changedTouches)) {
        const rect = canvas.getBoundingClientRect();
        if (touch.clientX - rect.left > rect.width / 2) {
          if (lookTouchId === null) { lookTouchId = touch.identifier; lastTouchX = touch.clientX; lastTouchY = touch.clientY; }
        } else if (moveTouchId === null) {
          moveTouchId = touch.identifier; moveStartX = touch.clientX; moveStartY = touch.clientY;
        }
      }
    };
    const onTouchMove = (e: TouchEvent) => {
      for (const touch of Array.from(e.changedTouches)) {
        if (touch.identifier === lookTouchId) {
          yaw -= (touch.clientX - lastTouchX) * 0.005;
          pitch = Math.max(-1.45, Math.min(1.45, pitch - (touch.clientY - lastTouchY) * 0.005));
          lastTouchX = touch.clientX; lastTouchY = touch.clientY;
        } else if (touch.identifier === moveTouchId) {
          touchStateRef.current.moveX = Math.max(-1, Math.min(1, (touch.clientX - moveStartX) / 50));
          touchStateRef.current.moveY = Math.max(-1, Math.min(1, (touch.clientY - moveStartY) / 50));
        }
      }
      e.preventDefault();
    };
    const onTouchEnd = (e: TouchEvent) => {
      for (const touch of Array.from(e.changedTouches)) {
        if (touch.identifier === lookTouchId) lookTouchId = null;
        if (touch.identifier === moveTouchId) { moveTouchId = null; touchStateRef.current.moveX = 0; touchStateRef.current.moveY = 0; }
      }
    };
    if (isTouch) {
      canvas.addEventListener('touchstart', onTouchStart, { passive: true });
      canvas.addEventListener('touchmove', onTouchMove, { passive: false });
      canvas.addEventListener('touchend', onTouchEnd, { passive: true });
    }

    const shoot = () => {
      const now = performance.now();
      if (!alive || now - lastShot < 140) return;
      lastShot = now;
      fpsAudio.play('gunshot');
      muzzleFlash.visible = true;
      muzzleFlash.rotation.z = Math.random() * Math.PI;
      flashLight.intensity = 8;
      gunGroup.position.z = -0.48;
      setTimeout(() => { muzzleFlash.visible = false; flashLight.intensity = 0; gunGroup.position.z = -0.55; }, 55);

      raycaster.setFromCamera(new THREE.Vector2(0, 0), camera);
      const bodies: THREE.Object3D[] = [];
      remotes.forEach((entry) => { if (entry.group.visible) bodies.push(...entry.rig.bodyMeshes); });
      const hits = raycaster.intersectObjects(bodies, false);
      let endPoint = raycaster.ray.at(60, new THREE.Vector3());
      if (hits.length > 0 && hits[0].distance < 100) {
        endPoint = hits[0].point;
        const targetId = String(hits[0].object.userData.ownerId || '');
        if (targetId && wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: 'hit', target_id: targetId }));
          fpsAudio.play('hit');
          setHitMarker(true);
          setTimeout(() => { if (!disposed) setHitMarker(false); }, 110);
        }
        const spark = new THREE.Mesh(
          new THREE.SphereGeometry(0.07, 6, 6),
          new THREE.MeshBasicMaterial({ color: 0xffb454, transparent: true, opacity: 0.95 }),
        );
        spark.position.copy(endPoint);
        scene.add(spark);
        sparks.push({ mesh: spark, born: now });
      }
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'shoot' }));
      }
      const start = camera.localToWorld(new THREE.Vector3(0.32, -0.25, -1.1));
      const geo = new THREE.BufferGeometry().setFromPoints([start, endPoint]);
      const line = new THREE.Line(geo, new THREE.LineBasicMaterial({ color: 0xffdd77, transparent: true, opacity: 0.9 }));
      scene.add(line);
      tracers.push({ line, born: now });
    };

    // ── Collision helpers ──
    const resolveColliders = () => {
      const radius = 0.5;
      colliders.forEach(([cx, cz, w, d]) => {
        const minX = cx - w / 2 - radius, maxX = cx + w / 2 + radius;
        const minZ = cz - d / 2 - radius, maxZ = cz + d / 2 + radius;
        if (position.x > minX && position.x < maxX && position.z > minZ && position.z < maxZ) {
          const dxMin = position.x - minX, dxMax = maxX - position.x;
          const dzMin = position.z - minZ, dzMax = maxZ - position.z;
          const minPen = Math.min(dxMin, dxMax, dzMin, dzMax);
          if (minPen === dxMin) position.x = minX;
          else if (minPen === dxMax) position.x = maxX;
          else if (minPen === dzMin) position.z = minZ;
          else position.z = maxZ;
        }
      });
    };

    // ── Game loop ──
    const clock = new THREE.Clock();
    let rafId = 0;
    let bobPhase = 0;
    const animate = () => {
      if (disposed) return;
      rafId = requestAnimationFrame(animate);
      const dt = Math.min(0.05, clock.getDelta());

      if (alive) {
        const speed = keys.ShiftLeft || keys.ShiftRight ? 9 : 6;
        const forward = Number(keys.KeyW || keys.ArrowUp || false) - Number(keys.KeyS || keys.ArrowDown || false) - touchStateRef.current.moveY;
        const strafe = Number(keys.KeyD || keys.ArrowRight || false) - Number(keys.KeyA || keys.ArrowLeft || false) + touchStateRef.current.moveX;
        const dir = new THREE.Vector3(strafe, 0, -forward);
        if (dir.lengthSq() > 0) {
          dir.normalize().applyAxisAngle(new THREE.Vector3(0, 1, 0), yaw);
          position.x += dir.x * speed * dt;
          position.z += dir.z * speed * dt;
        }
        if ((keys.Space || touchStateRef.current.jump) && onGround) {
          velocity.y = 8;
          onGround = false;
          touchStateRef.current.jump = false;
        }
        velocity.y -= 25 * dt;
        position.y += velocity.y * dt;
        if (position.y <= EYE_HEIGHT) { position.y = EYE_HEIGHT; velocity.y = 0; onGround = true; }
        position.x = Math.max(-ARENA_HALF + 1.2, Math.min(ARENA_HALF - 1.2, position.x));
        position.z = Math.max(-ARENA_HALF + 1.2, Math.min(ARENA_HALF - 1.2, position.z));
        resolveColliders();
        if (fireHeld || touchStateRef.current.fire) shoot();
        // weapon bob while moving
        const moving = dir.lengthSq() > 0;
        bobPhase = moving ? bobPhase + dt * 9 : 0;
        gunGroup.position.y = -0.3 + (moving ? Math.sin(bobPhase) * 0.012 : 0);
        gunGroup.position.x = 0.32 + (moving ? Math.cos(bobPhase * 0.5) * 0.008 : 0);
      }

      camera.position.copy(position);
      camera.rotation.set(0, 0, 0);
      camera.rotateY(yaw);
      camera.rotateX(pitch);

      remotes.forEach((entry) => {
        entry.group.position.lerp(entry.target, Math.min(1, dt * 10));
        entry.group.rotation.y += (entry.yaw - entry.group.rotation.y) * Math.min(1, dt * 10);
        // walk cycle: swing limbs while the character is moving
        const speed2 = entry.group.position.distanceToSquared(entry.prevPos);
        entry.prevPos.copy(entry.group.position);
        if (speed2 > 0.00002) {
          entry.walkPhase += dt * 9;
          const swing = Math.sin(entry.walkPhase) * 0.55;
          entry.rig.lLeg.rotation.x = swing;
          entry.rig.rLeg.rotation.x = -swing;
          entry.rig.lArm.rotation.x = -swing * 0.7;
          entry.rig.rArm.rotation.x = swing * 0.7;
        } else {
          const ease = Math.min(1, dt * 8);
          entry.rig.lLeg.rotation.x *= 1 - ease;
          entry.rig.rLeg.rotation.x *= 1 - ease;
          entry.rig.lArm.rotation.x *= 1 - ease;
          entry.rig.rArm.rotation.x *= 1 - ease;
        }
      });

      const now = performance.now();
      for (let i = tracers.length - 1; i >= 0; i -= 1) {
        if (now - tracers[i].born > 90) {
          scene.remove(tracers[i].line);
          tracers[i].line.geometry.dispose();
          tracers.splice(i, 1);
        }
      }
      for (let i = sparks.length - 1; i >= 0; i -= 1) {
        const age = now - sparks[i].born;
        if (age > 160) {
          scene.remove(sparks[i].mesh);
          sparks[i].mesh.geometry.dispose();
          sparks.splice(i, 1);
        } else {
          const k = 1 + age / 60;
          sparks[i].mesh.scale.set(k, k, k);
          (sparks[i].mesh.material as THREE.MeshBasicMaterial).opacity = 0.95 * (1 - age / 160);
        }
      }

      renderer.render(scene, camera);
    };
    animate();

    cleanupRef.current = () => {
      disposed = true;
      cancelAnimationFrame(rafId);
      if (stateTimer) clearInterval(stateTimer);
      if (keepAliveTimer) clearInterval(keepAliveTimer);
      if (reconnectTimer) clearTimeout(reconnectTimer);
      const sock = wsRef.current;
      if (sock && sock.readyState === WebSocket.OPEN) {
        sock.send(JSON.stringify({ type: 'leave' }));
      }
      if (sock && sock.readyState !== WebSocket.CLOSED) sock.close();
      wsRef.current = null;
      window.removeEventListener('resize', resize);
      canvas.removeEventListener('click', onCanvasClick);
      document.removeEventListener('pointerlockchange', onPointerLockChange);
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('keyup', onKeyUp);
      document.removeEventListener('mousedown', onMouseDown);
      document.removeEventListener('mouseup', onMouseUp);
      if (isTouch) {
        canvas.removeEventListener('touchstart', onTouchStart);
        canvas.removeEventListener('touchmove', onTouchMove);
        canvas.removeEventListener('touchend', onTouchEnd);
      }
      if (document.pointerLockElement === canvas) document.exitPointerLock?.();
      renderer.dispose();
      if (renderer.domElement.parentElement === mountEl) mountEl.removeChild(renderer.domElement);
    };
    return () => cleanupRef.current();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roomId, userId]);

  const sendChat = useCallback(() => {
    const text = chatText.trim();
    if (text && wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'chat', text }));
    }
    setChatText('');
    chatOpenRef.current = false;
    setChatOpen(false);
  }, [chatText]);

  if (unsupported) {
    return (
      <View style={styles.unsupported} data-testid="fps-arena-unsupported" testID="fps-arena-unsupported">
        <Text style={{ color: '#e2e8f0' /* @theme-ok fixed-dark-canvas */, textAlign: 'center' }}>
          {tx('fpsGame.arena.webOnly', 'The FPS arena runs in the web app. Open this feature in your browser to play.')}
        </Text>
        <Pressable onPress={onExit} style={styles.exitBtn} data-testid="fps-arena-exit-button" testID="fps-arena-exit-button">
          <Text style={styles.exitBtnText}>{tx('fpsGame.arena.backToLobby', 'Back to lobby')}</Text>
        </Pressable>
      </View>
    );
  }

  const isTouchDevice = Platform.OS === 'web' && typeof window !== 'undefined' && ('ontouchstart' in window || (navigator as any).maxTouchPoints > 0);

  return (
    <View style={styles.wrapper} data-testid="fps-arena" testID="fps-arena">
      <View ref={mountRef} style={styles.canvasHost} data-testid="fps-arena-canvas-host" testID="fps-arena-canvas-host" />

      {/* Red crosshair (center) */}
      <View pointerEvents="none" style={styles.crosshair} data-testid="fps-arena-crosshair" testID="fps-arena-crosshair">
        <View style={styles.crosshairH} />
        <View style={styles.crosshairV} />
      </View>

      {/* Hit confirmation marker */}
      {hitMarker && (
        <View pointerEvents="none" style={styles.hitMarker} data-testid="fps-arena-hit-marker" testID="fps-arena-hit-marker">
          <View style={[styles.hitMarkerLine, { transform: [{ rotate: '45deg' }] }]} />
          <View style={[styles.hitMarkerLine, { transform: [{ rotate: '-45deg' }] }]} />
        </View>
      )}

      {/* Damage flash */}
      {damageFlash && <View pointerEvents="none" style={styles.damageFlash} />}

      {/* HP + score (top-left) */}
      <View style={styles.hudTopLeft} pointerEvents="none" data-testid="fps-arena-hud" testID="fps-arena-hud">
        <Text style={styles.hudRoom}>{roomName} · {playersOnline} {tx('fpsGame.arena.players', 'players')}</Text>
        <View style={styles.hpRow}>
          <Text style={styles.hpLabel}>{tx('fpsGame.arena.hp', 'HP')}</Text>
          <View style={styles.hpBarOuter}>
            <View style={[styles.hpBarInner, { width: `${Math.max(0, Math.min(100, hp))}%`, backgroundColor: hp > 40 ? '#22c55e' : '#ef4444' }]} />
          </View>
          <Text style={styles.hpValue} data-testid="fps-arena-hp-value" testID="fps-arena-hp-value">{hp}</Text>
        </View>
        <Text style={styles.scoreText} data-testid="fps-arena-score" testID="fps-arena-score">
          {tx('fpsGame.arena.kills', 'Kills')}: {kills} · {tx('fpsGame.arena.deaths', 'Deaths')}: {deaths}
        </Text>
        {myStreak >= 2 && (
          <Text style={styles.streakText} data-testid="fps-arena-streak" testID="fps-arena-streak">
            <Ionicons name="flame" size={12} color="#fbbf24" /> {tx('fpsGame.arena.streakLabel', 'Streak')}: {myStreak}
          </Text>
        )}
      </View>

      {/* Streak milestone banner */}
      {!!streakBanner && (
        <View style={styles.streakBanner} pointerEvents="none" data-testid="fps-arena-streak-banner" testID="fps-arena-streak-banner">
          <Text style={styles.streakBannerText}>{streakBanner}</Text>
        </View>
      )}

      {/* Message panel (bottom-left, as in the source game) */}
      <View style={styles.feedPanel} pointerEvents="none" data-testid="fps-arena-feed" testID="fps-arena-feed">
        {feed.map((item) => (
          <Text key={item.id} style={styles.feedText}>{item.text}</Text>
        ))}
        <Text style={[styles.feedText, { color: connected ? '#4ade80' : '#f87171' }]} data-testid="fps-arena-connection-state" testID="fps-arena-connection-state">
          {connected ? tx('fpsGame.arena.connected', 'Connected') : tx('fpsGame.arena.connecting', 'Connecting...')}
        </Text>
      </View>

      {/* Top-right controls */}
      <View style={styles.controlRow}>
        <Pressable
          onPress={copyInvite}
          style={styles.ctrlBtn}
          data-testid="fps-arena-invite-button" testID="fps-arena-invite-button"
        >
          <Ionicons name="link-outline" size={15} color={'#fff' /* @theme-ok fixed-dark-canvas */} />
          <Text style={styles.exitBtnText}>{inviteCopied ? tx('fpsGame.arena.inviteCopied', 'Invite link copied') : tx('fpsGame.arena.invite', 'Invite')}</Text>
        </Pressable>
        <Pressable
          onPress={() => setMuted(fpsAudio.toggleMute())}
          style={styles.ctrlBtn}
          accessibilityLabel={muted ? tx('fpsGame.arena.unmute', 'Unmute sound') : tx('fpsGame.arena.mute', 'Mute sound')}
          data-testid="fps-arena-mute-button" testID="fps-arena-mute-button"
        >
          <Ionicons name={muted ? 'volume-mute-outline' : 'volume-high-outline'} size={16} color={'#fff' /* @theme-ok fixed-dark-canvas */} />
        </Pressable>
        <Pressable onPress={onExit} style={[styles.ctrlBtn, { backgroundColor: 'rgba(239,68,68,0.85)' }]} data-testid="fps-arena-leave-button" testID="fps-arena-leave-button">
          <Text style={styles.exitBtnText}>{tx('fpsGame.arena.leave', 'Leave')}</Text>
        </Pressable>
      </View>
      <Text style={styles.escHint} pointerEvents="none" data-testid="fps-arena-esc-hint" testID="fps-arena-esc-hint">
        {tx('fpsGame.arena.escHint', 'Press ESC to release your mouse')} · {tx('fpsGame.arena.scoreboardHint', 'Hold Tab for scoreboard')} · {tx('fpsGame.arena.chatHint', 'Press Enter to chat')}
      </Text>

      {/* Scoreboard (hold Tab, or while dead) */}
      {(showScoreboard || dead) && scoreRows.length > 0 && (
        <View style={styles.scoreboard} pointerEvents="none" data-testid="fps-arena-scoreboard" testID="fps-arena-scoreboard">
          <Text style={styles.scoreboardTitle}>{tx('fpsGame.arena.scoreboard', 'Scoreboard')}</Text>
          {scoreRows.map((row) => (
            <View key={row.uid} style={styles.scoreboardRow}>
              <Text style={[styles.scoreboardName, row.uid === userId && { color: '#4ade80' /* @theme-ok fixed-dark-canvas */ }]} numberOfLines={1}>{row.name}</Text>
              <Text style={styles.scoreboardStat}>{row.kills} / {row.deaths}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Quick chat */}
      {chatOpen && (
        <View style={styles.chatBox} data-testid="fps-arena-chat-box" testID="fps-arena-chat-box">
          <TextInput accessibilityLabel="Text input"
            value={chatText}
            onChangeText={setChatText}
            onSubmitEditing={sendChat}
            autoFocus
            maxLength={200}
            placeholder={tx('fpsGame.arena.chatPlaceholder', 'Say something...')}
            placeholderTextColor="rgba(226,232,240,0.5)"
            style={styles.chatInput}
            data-testid="fps-arena-chat-input" testID="fps-arena-chat-input"
          />
        </View>
      )}

      {/* Death overlay */}
      {dead && (
        <View style={styles.deadOverlay} pointerEvents="none" data-testid="fps-arena-dead-overlay" testID="fps-arena-dead-overlay">
          <Text style={styles.deadTitle}>{tx('fpsGame.arena.eliminated', 'You were eliminated')}</Text>
          <Text style={styles.deadSub}>{tx('fpsGame.arena.respawning', 'Respawning in 3 seconds...')}</Text>
        </View>
      )}

      {/* Touch controls */}
      {isTouchDevice && (
        <>
          <Pressable
            style={styles.fireBtn}
            onPressIn={() => { touchStateRef.current.fire = true; }}
            onPressOut={() => { touchStateRef.current.fire = false; }}
            data-testid="fps-arena-fire-button" testID="fps-arena-fire-button"
          >
            <Text style={styles.fireBtnText}>{tx('fpsGame.arena.fire', 'FIRE')}</Text>
          </Pressable>
          <Pressable
            style={styles.jumpBtn}
            onPress={() => { touchStateRef.current.jump = true; }}
            data-testid="fps-arena-jump-button" testID="fps-arena-jump-button"
          >
            <Text style={styles.fireBtnText}>{tx('fpsGame.arena.jump', 'JUMP')}</Text>
          </Pressable>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: { width: '100%', height: 560, maxHeight: '80vh' as any, borderRadius: 16, overflow: 'hidden', position: 'relative', backgroundColor: '#0b1420' /* @theme-ok fixed-dark-canvas */ },
  canvasHost: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 },
  crosshair: { position: 'absolute', top: '50%', left: '50%', width: 22, height: 22, marginLeft: -11, marginTop: -11, alignItems: 'center', justifyContent: 'center' },
  crosshairH: { position: 'absolute', width: 22, height: 2, backgroundColor: '#ef4444' /* @theme-ok fixed-dark-canvas */, borderRadius: 1 },
  crosshairV: { position: 'absolute', width: 2, height: 22, backgroundColor: '#ef4444' /* @theme-ok fixed-dark-canvas */, borderRadius: 1 },
  damageFlash: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundImage: 'radial-gradient(ellipse at center, rgba(239,68,68,0) 45%, rgba(239,68,68,0.45) 100%)' } as any,
  hitMarker: { position: 'absolute', top: '50%', left: '50%', width: 30, height: 30, marginLeft: -15, marginTop: -15, alignItems: 'center', justifyContent: 'center' },
  hitMarkerLine: { position: 'absolute', width: 22, height: 2.5, backgroundColor: '#ffffff' /* @theme-ok fixed-dark-canvas */, borderRadius: 1 },
  hudTopLeft: { position: 'absolute', top: 12, left: 12, backgroundColor: 'rgba(2,6,23,0.55)', borderRadius: 10, padding: 10, minWidth: 190 },
  hudRoom: { color: '#94a3b8' /* @theme-ok fixed-dark-canvas */, fontSize: 11, fontWeight: '700', marginBottom: 6 },
  hpRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  hpLabel: { color: '#e2e8f0' /* @theme-ok fixed-dark-canvas */, fontSize: 12, fontWeight: '800' },
  hpBarOuter: { flex: 1, height: 8, backgroundColor: 'rgba(255,255,255,0.15)', borderRadius: 4, overflow: 'hidden' },
  hpBarInner: { height: 8, borderRadius: 4 },
  hpValue: { color: '#e2e8f0' /* @theme-ok fixed-dark-canvas */, fontSize: 12, fontWeight: '800', width: 30, textAlign: 'right' },
  scoreText: { color: '#cbd5e1' /* @theme-ok fixed-dark-canvas */, fontSize: 12, marginTop: 6, fontWeight: '600' },
  streakText: { color: '#fbbf24' /* @theme-ok fixed-dark-canvas */, fontSize: 12, marginTop: 4, fontWeight: '800' },
  streakBanner: { position: 'absolute', top: 80, left: 0, right: 0, alignItems: 'center' },
  streakBannerText: { color: '#fbbf24' /* @theme-ok fixed-dark-canvas */, fontSize: 34, fontWeight: '900', letterSpacing: 3, textShadowColor: 'rgba(0,0,0,0.8)', textShadowRadius: 8, textShadowOffset: { width: 0, height: 2 } },
  controlRow: { position: 'absolute', top: 12, right: 12, flexDirection: 'row', gap: 8 },
  ctrlBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: 'rgba(15,23,42,0.7)', borderRadius: 999, paddingHorizontal: 14, paddingVertical: 8 },
  scoreboard: { position: 'absolute', top: '18%' as any, alignSelf: 'center', minWidth: 280, maxWidth: '86%' as any, backgroundColor: 'rgba(2,6,23,0.82)', borderRadius: 12, padding: 14, borderWidth: 1, borderColor: 'rgba(148,163,184,0.25)' },
  scoreboardTitle: { color: '#e2e8f0' /* @theme-ok fixed-dark-canvas */, fontSize: 13, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1.2, marginBottom: 8, textAlign: 'center' },
  scoreboardRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4, gap: 16 },
  scoreboardName: { color: '#e2e8f0' /* @theme-ok fixed-dark-canvas */, fontSize: 13, fontWeight: '600', flex: 1 },
  scoreboardStat: { color: '#94a3b8' /* @theme-ok fixed-dark-canvas */, fontSize: 13, fontWeight: '700' },
  chatBox: { position: 'absolute', bottom: 90, alignSelf: 'center', width: '60%' as any, maxWidth: 480 },
  chatInput: { backgroundColor: 'rgba(2,6,23,0.85)' /* @theme-ok fixed-dark-canvas */, borderWidth: 1, borderColor: 'rgba(148,163,184,0.35)', borderRadius: 10, color: '#e2e8f0', paddingHorizontal: 12, paddingVertical: 9, fontSize: 14 },
  feedPanel: { position: 'absolute', bottom: 12, left: 12, backgroundColor: 'rgba(2,6,23,0.5)', borderRadius: 10, padding: 10, maxWidth: 320 },
  feedText: { color: '#e2e8f0' /* @theme-ok fixed-dark-canvas */, fontSize: 12, marginBottom: 2 },
  escHint: { position: 'absolute', top: 46, right: 12, color: 'rgba(226,232,240,0.55)', fontSize: 10, fontWeight: '600' },
  exitBtn: { marginTop: 16, backgroundColor: '#0ea5e9' /* @theme-ok fixed-dark-canvas */, borderRadius: 999, paddingHorizontal: 20, paddingVertical: 10 },
  exitBtnText: { color: '#fff' /* @theme-ok fixed-dark-canvas */, fontWeight: '800', fontSize: 13 },
  deadOverlay: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(2,6,23,0.6)', alignItems: 'center', justifyContent: 'center' },
  deadTitle: { color: '#f87171' /* @theme-ok fixed-dark-canvas */, fontSize: 24, fontWeight: '900' },
  deadSub: { color: '#e2e8f0' /* @theme-ok fixed-dark-canvas */, fontSize: 14, marginTop: 8 },
  fireBtn: { position: 'absolute', bottom: 24, right: 20, width: 78, height: 78, borderRadius: 39, backgroundColor: 'rgba(239,68,68,0.75)', alignItems: 'center', justifyContent: 'center' },
  jumpBtn: { position: 'absolute', bottom: 116, right: 32, width: 58, height: 58, borderRadius: 29, backgroundColor: 'rgba(59,130,246,0.7)', alignItems: 'center', justifyContent: 'center' },
  fireBtnText: { color: '#fff' /* @theme-ok fixed-dark-canvas */, fontWeight: '900', fontSize: 13 },
  unsupported: { padding: 40, alignItems: 'center', justifyContent: 'center', backgroundColor: '#0b1420' /* @theme-ok fixed-dark-canvas */, borderRadius: 16 },
});
