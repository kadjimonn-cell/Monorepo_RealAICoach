import * as THREE from 'three';

export type CharacterRig = {
  group: THREE.Group;
  lArm: THREE.Group;
  rArm: THREE.Group;
  lLeg: THREE.Group;
  rLeg: THREE.Group;
  healthFill: THREE.Sprite;
  bodyMeshes: THREE.Mesh[];
};

const MODEL_STYLES: Record<string, { body: number; accent: number; head: number; kind: 'human' | 'robot' }> = {
  policeman: { body: 0x2c3a4a, accent: 0xeab308, head: 0xd9c4a1, kind: 'human' },
  robotx: { body: 0x8a2255, accent: 0xdb2777, head: 0xb8bec8, kind: 'robot' },
  roboty: { body: 0x1e3a6e, accent: 0x3b82f6, head: 0xb8bec8, kind: 'robot' },
};

function canvasTexture(size: number, draw: (ctx: CanvasRenderingContext2D, s: number) => void, repeatX = 1, repeatY = 1): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = size; canvas.height = size;
  const ctx = canvas.getContext('2d')!;
  draw(ctx, size);
  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(repeatX, repeatY);
  return tex;
}

function floorTexture(): THREE.CanvasTexture {
  return canvasTexture(256, (ctx, s) => {
    ctx.fillStyle = '#3a423c'; ctx.fillRect(0, 0, s, s);
    for (let i = 0; i < 900; i += 1) {
      const shade = 52 + Math.random() * 26;
      ctx.fillStyle = `rgb(${shade},${shade + 6},${shade})`;
      ctx.fillRect(Math.random() * s, Math.random() * s, 2, 2);
    }
    ctx.strokeStyle = 'rgba(20,26,22,0.7)'; ctx.lineWidth = 3;
    ctx.strokeRect(1, 1, s - 2, s - 2);
    ctx.strokeStyle = 'rgba(90,100,92,0.25)'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(s / 2, 0); ctx.lineTo(s / 2, s); ctx.moveTo(0, s / 2); ctx.lineTo(s, s / 2); ctx.stroke();
  }, 14, 14);
}

function wallTexture(): THREE.CanvasTexture {
  return canvasTexture(256, (ctx, s) => {
    ctx.fillStyle = '#4d5866'; ctx.fillRect(0, 0, s, s);
    for (let y = 0; y < s; y += 64) {
      ctx.fillStyle = y % 128 === 0 ? '#525d6c' : '#485362';
      ctx.fillRect(0, y, s, 60);
      ctx.fillStyle = 'rgba(24,30,38,0.85)';
      ctx.fillRect(0, y + 60, s, 4);
    }
    ctx.fillStyle = 'rgba(30,36,44,0.9)';
    for (let y = 30; y < s; y += 64) {
      for (let x = 12; x < s; x += 48) { ctx.beginPath(); ctx.arc(x, y, 2.4, 0, Math.PI * 2); ctx.fill(); }
    }
    ctx.fillStyle = 'rgba(20,25,32,0.15)';
    for (let i = 0; i < 6; i += 1) ctx.fillRect(Math.random() * s, 0, 6 + Math.random() * 10, s);
  }, 6, 1);
}

function crateTexture(): THREE.CanvasTexture {
  return canvasTexture(256, (ctx, s) => {
    ctx.fillStyle = '#8a6a3e'; ctx.fillRect(0, 0, s, s);
    for (let y = 0; y < s; y += 42) {
      ctx.fillStyle = y % 84 === 0 ? '#93714a' : '#7d5f36';
      ctx.fillRect(0, y, s, 38);
      ctx.fillStyle = 'rgba(50,36,18,0.8)'; ctx.fillRect(0, y + 38, s, 4);
      ctx.strokeStyle = 'rgba(70,52,26,0.5)'; ctx.lineWidth = 1;
      for (let i = 0; i < 5; i += 1) {
        ctx.beginPath(); ctx.moveTo(0, y + 6 + Math.random() * 26);
        ctx.bezierCurveTo(s / 3, y + Math.random() * 38, (2 * s) / 3, y + Math.random() * 38, s, y + Math.random() * 38);
        ctx.stroke();
      }
    }
    ctx.strokeStyle = 'rgba(40,44,50,0.9)'; ctx.lineWidth = 10;
    ctx.strokeRect(5, 5, s - 10, s - 10);
  }, 1, 1);
}

export function makeSky(): THREE.Mesh {
  const canvas = document.createElement('canvas');
  canvas.width = 4; canvas.height = 256;
  const ctx = canvas.getContext('2d')!;
  const grad = ctx.createLinearGradient(0, 0, 0, 256);
  grad.addColorStop(0, '#0a1526');
  grad.addColorStop(0.42, '#1c3450');
  grad.addColorStop(0.55, '#4a6584');
  grad.addColorStop(0.62, '#2a4058');
  grad.addColorStop(1, '#0b1420');
  ctx.fillStyle = grad; ctx.fillRect(0, 0, 4, 256);
  const tex = new THREE.CanvasTexture(canvas);
  const sky = new THREE.Mesh(
    new THREE.SphereGeometry(150, 24, 16),
    new THREE.MeshBasicMaterial({ map: tex, side: THREE.BackSide, fog: false }),
  );
  return sky;
}

export type Collider = [number, number, number, number]; // x, z, width, depth

const CRATE_BOXES: Array<[number, number, number, number, number, number]> = [
  [-10, 1, -8, 3, 2, 3], [12, 1, -12, 4, 2, 4], [6, 1, 8, 3, 2, 5],
  [-14, 1, 12, 5, 2, 3], [0, 1, -18, 6, 2, 2], [-4, 1, 2, 2, 2, 2],
  [18, 1, 6, 3, 2, 3], [-20, 1, -16, 3, 2, 3],
];

export function buildMap(scene: THREE.Scene, arenaHalf: number): Collider[] {
  const colliders: Collider[] = [];

  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(arenaHalf * 2, arenaHalf * 2),
    new THREE.MeshStandardMaterial({ map: floorTexture(), roughness: 0.95 }),
  );
  floor.rotation.x = -Math.PI / 2;
  scene.add(floor);

  const wallMat = new THREE.MeshStandardMaterial({ map: wallTexture(), roughness: 0.85 });
  const wallTrimMat = new THREE.MeshStandardMaterial({ color: 0x37bd9a, emissive: 0x1a5f4d, roughness: 0.4 });
  const walls: Array<[number, number, number, number, number, number]> = [
    [0, 2.5, -arenaHalf, arenaHalf * 2, 5, 1], [0, 2.5, arenaHalf, arenaHalf * 2, 5, 1],
    [-arenaHalf, 2.5, 0, 1, 5, arenaHalf * 2], [arenaHalf, 2.5, 0, 1, 5, arenaHalf * 2],
  ];
  walls.forEach(([x, y, z, w, h, d]) => {
    const wall = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), wallMat);
    wall.position.set(x, y, z);
    scene.add(wall);
    const trim = new THREE.Mesh(new THREE.BoxGeometry(w === 1 ? 1.02 : w, 0.12, d === 1 ? 1.02 : d), wallTrimMat);
    trim.position.set(x, 5.05, z);
    scene.add(trim);
  });

  const crateMat = new THREE.MeshStandardMaterial({ map: crateTexture(), roughness: 0.9 });
  CRATE_BOXES.forEach(([x, y, z, w, h, d]) => {
    const crate = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), crateMat);
    crate.position.set(x, y, z);
    scene.add(crate);
    colliders.push([x, z, w, d]);
  });

  // central two-level structure: 4 pillars + elevated slab
  const pillarMat = new THREE.MeshStandardMaterial({ color: 0x5c6874, roughness: 0.7 });
  const slabMat = new THREE.MeshStandardMaterial({ color: 0x424e5a, roughness: 0.8 });
  [[-3.5, -3.5], [3.5, -3.5], [-3.5, 3.5], [3.5, 3.5]].forEach(([px, pz]) => {
    const pillar = new THREE.Mesh(new THREE.BoxGeometry(1, 3.2, 1), pillarMat);
    pillar.position.set(px, 1.6, pz);
    scene.add(pillar);
    colliders.push([px, pz, 1, 1]);
  });
  const slab = new THREE.Mesh(new THREE.BoxGeometry(9, 0.4, 9), slabMat);
  slab.position.set(0, 3.4, 0);
  scene.add(slab);
  const slabTrim = new THREE.Mesh(new THREE.BoxGeometry(9.1, 0.08, 9.1), wallTrimMat);
  slabTrim.position.set(0, 3.65, 0);
  scene.add(slabTrim);

  // side barriers for cover lanes
  const barrierMat = new THREE.MeshStandardMaterial({ color: 0x6b5a3a, roughness: 0.9 });
  [[12, 0], [-12, 0]].forEach(([bx, bz]) => {
    const barrier = new THREE.Mesh(new THREE.BoxGeometry(0.5, 1.2, 6), barrierMat);
    barrier.position.set(bx, 0.6, bz);
    scene.add(barrier);
    colliders.push([bx, bz, 0.5, 6]);
  });

  // accent lights
  const teal = new THREE.PointLight(0x37bd9a, 14, 26);
  teal.position.set(-16, 4, -16);
  const magenta = new THREE.PointLight(0xdb2777, 12, 26);
  magenta.position.set(16, 4, 16);
  scene.add(teal, magenta);

  return colliders;
}

export function makeNameTag(name: string): THREE.Sprite {
  const canvas = document.createElement('canvas');
  canvas.width = 256; canvas.height = 64;
  const ctx = canvas.getContext('2d')!;
  ctx.font = 'bold 30px sans-serif';
  ctx.textAlign = 'center';
  ctx.fillStyle = 'rgba(0,0,0,0.45)';
  ctx.fillRect(0, 8, 256, 48);
  ctx.fillStyle = '#ffffff';
  ctx.fillText(name.slice(0, 14), 128, 42);
  const texture = new THREE.CanvasTexture(canvas);
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, depthTest: false }));
  sprite.scale.set(2.4, 0.6, 1);
  sprite.position.y = 2.62;
  return sprite;
}

function solidSprite(color: string): THREE.Sprite {
  const canvas = document.createElement('canvas');
  canvas.width = 8; canvas.height = 8;
  const ctx = canvas.getContext('2d')!;
  ctx.fillStyle = color; ctx.fillRect(0, 0, 8, 8);
  return new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(canvas), depthTest: false }));
}

export function makeCharacter(model: string): CharacterRig {
  const style = MODEL_STYLES[model] ?? MODEL_STYLES.policeman;
  const bodyMat = new THREE.MeshStandardMaterial({ color: style.body, roughness: 0.6 });
  const accentMat = new THREE.MeshStandardMaterial({ color: style.accent, roughness: 0.45 });
  const headMat = new THREE.MeshStandardMaterial({ color: style.head, roughness: 0.7 });
  const darkMat = new THREE.MeshStandardMaterial({ color: 0x141a22, roughness: 0.35 });

  const group = new THREE.Group();
  const bodyMeshes: THREE.Mesh[] = [];
  const tag = (mesh: THREE.Mesh) => { mesh.userData.isPlayerBody = true; bodyMeshes.push(mesh); return mesh; };

  const torso = tag(new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.7, 0.32), bodyMat));
  torso.position.y = 1.3;
  const vest = tag(new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.4, 0.38), accentMat));
  vest.position.y = 1.34;
  group.add(torso, vest);

  const head = tag(new THREE.Mesh(
    style.kind === 'human' ? new THREE.SphereGeometry(0.22, 16, 16) : new THREE.BoxGeometry(0.36, 0.34, 0.34),
    headMat,
  ));
  head.position.y = 1.86;
  group.add(head);
  if (style.kind === 'human') {
    const capTop = new THREE.Mesh(new THREE.CylinderGeometry(0.23, 0.24, 0.12, 12), darkMat);
    capTop.position.y = 2.0;
    const brim = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.03, 0.22), darkMat);
    brim.position.set(0, 1.94, -0.2);
    group.add(capTop, brim);
  } else {
    const visor = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.1, 0.05), new THREE.MeshStandardMaterial({ color: 0x0c1018, emissive: style.accent, emissiveIntensity: 0.7 }));
    visor.position.set(0, 1.88, -0.18);
    group.add(visor);
    if (model === 'roboty') {
      const antenna = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.015, 0.28, 6), darkMat);
      antenna.position.set(0.14, 2.15, 0);
      const bulb = new THREE.Mesh(new THREE.SphereGeometry(0.035, 8, 8), new THREE.MeshStandardMaterial({ color: style.accent, emissive: style.accent, emissiveIntensity: 0.9 }));
      bulb.position.set(0.14, 2.3, 0);
      group.add(antenna, bulb);
    }
  }

  const makeArm = (side: number): THREE.Group => {
    const pivot = new THREE.Group();
    pivot.position.set(side * 0.37, 1.58, 0);
    const arm = tag(new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.58, 0.16), bodyMat));
    arm.position.y = -0.26;
    const hand = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.12, 0.14), headMat);
    hand.position.y = -0.58;
    pivot.add(arm, hand);
    group.add(pivot);
    return pivot;
  };
  const makeLeg = (side: number): THREE.Group => {
    const pivot = new THREE.Group();
    pivot.position.set(side * 0.16, 0.95, 0);
    const leg = tag(new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.82, 0.2), darkMat));
    leg.position.y = -0.42;
    const boot = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.12, 0.3), darkMat);
    boot.position.set(0, -0.82, -0.04);
    pivot.add(leg, boot);
    group.add(pivot);
    return pivot;
  };
  const lArm = makeArm(-1);
  const rArm = makeArm(1);
  const lLeg = makeLeg(-1);
  const rLeg = makeLeg(1);

  // rifle in right hand
  const rifle = new THREE.Mesh(new THREE.BoxGeometry(0.09, 0.12, 0.72), darkMat);
  rifle.position.set(0.02, -0.5, -0.28);
  rArm.add(rifle);

  // floating health bar
  const barBg = solidSprite('rgba(10,14,20,0.85)');
  barBg.scale.set(0.96, 0.12, 1);
  barBg.position.y = 2.3;
  const healthFill = solidSprite('#22c55e');
  healthFill.center.set(0, 0.5);
  healthFill.scale.set(0.88, 0.07, 1);
  healthFill.position.set(-0.44, 2.3, 0.001);
  group.add(barBg, healthFill);

  return { group, lArm, rArm, lLeg, rLeg, healthFill, bodyMeshes };
}

export function makeAk47(): { group: THREE.Group; muzzleFlash: THREE.Mesh; flashLight: THREE.PointLight } {
  const metal = new THREE.MeshStandardMaterial({ color: 0x23252a, roughness: 0.35, metalness: 0.5 });
  const darkMetal = new THREE.MeshStandardMaterial({ color: 0x15171b, roughness: 0.3, metalness: 0.6 });
  const wood = new THREE.MeshStandardMaterial({ color: 0x7a5426, roughness: 0.7 });

  const group = new THREE.Group();
  const receiver = new THREE.Mesh(new THREE.BoxGeometry(0.075, 0.13, 0.4), metal);
  receiver.position.set(0, 0, 0.02);
  const barrel = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.44, 10), darkMetal);
  barrel.rotation.x = Math.PI / 2;
  barrel.position.set(0, 0.015, -0.4);
  const gasTube = new THREE.Mesh(new THREE.CylinderGeometry(0.013, 0.013, 0.3, 8), metal);
  gasTube.rotation.x = Math.PI / 2;
  gasTube.position.set(0, 0.05, -0.32);
  const handguard = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.08, 0.2), wood);
  handguard.position.set(0, 0, -0.28);
  const frontSight = new THREE.Mesh(new THREE.BoxGeometry(0.015, 0.06, 0.02), darkMetal);
  frontSight.position.set(0, 0.07, -0.58);
  const rearSight = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.03, 0.02), darkMetal);
  rearSight.position.set(0, 0.085, -0.08);
  const mag = new THREE.Mesh(new THREE.BoxGeometry(0.055, 0.24, 0.11), metal);
  mag.position.set(0, -0.15, -0.02);
  mag.rotation.x = 0.45;
  const grip = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.13, 0.07), wood);
  grip.position.set(0, -0.1, 0.16);
  grip.rotation.x = -0.3;
  const stock = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.1, 0.3), wood);
  stock.position.set(0, -0.03, 0.36);
  stock.rotation.x = 0.08;

  const muzzleFlash = new THREE.Mesh(
    new THREE.ConeGeometry(0.08, 0.24, 8),
    new THREE.MeshBasicMaterial({ color: 0xffcc55, transparent: true, opacity: 0.95 }),
  );
  muzzleFlash.rotation.x = Math.PI / 2;
  muzzleFlash.position.set(0, 0.015, -0.68);
  muzzleFlash.visible = false;
  const flashLight = new THREE.PointLight(0xffaa33, 0, 4);
  flashLight.position.set(0, 0.015, -0.66);

  group.add(receiver, barrel, gasTube, handguard, frontSight, rearSight, mag, grip, stock, muzzleFlash, flashLight);
  return { group, muzzleFlash, flashLight };
}
