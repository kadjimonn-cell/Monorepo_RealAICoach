#!/usr/bin/env node

const TOKENS = {
  light: {
    card: '#FFFFFF',
    text: '#0F172A',
    primary: '#0F766E',
    success: '#14B8A6',
  },
  dark: {
    card: '#0F172A',
    text: '#E6EAF2',
    primary: '#14B8A6',
    success: '#2DD4BF',
  },
};

const CONTRACT = {
  minContrastAA: 4.5,
  alphaLight: '18',
  alphaDark: '2E',
};

function hexToRgb(hex) {
  const v = String(hex || '').trim().replace('#', '');
  if (![3, 6].includes(v.length)) throw new Error(`Invalid hex: ${hex}`);
  const full = v.length === 3 ? v.split('').map((c) => c + c).join('') : v;
  return {
    r: parseInt(full.slice(0, 2), 16),
    g: parseInt(full.slice(2, 4), 16),
    b: parseInt(full.slice(4, 6), 16),
  };
}

function toLinear(c) {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
}

function luminance(rgb) {
  return 0.2126 * toLinear(rgb.r) + 0.7152 * toLinear(rgb.g) + 0.0722 * toLinear(rgb.b);
}

function contrastRatio(a, b) {
  const L1 = luminance(a);
  const L2 = luminance(b);
  const hi = Math.max(L1, L2);
  const lo = Math.min(L1, L2);
  return (hi + 0.05) / (lo + 0.05);
}

function blend(topHex, alphaHex, baseHex) {
  const top = hexToRgb(topHex);
  const base = hexToRgb(baseHex);
  const alpha = parseInt(alphaHex, 16) / 255;
  return {
    r: Math.round((top.r * alpha) + (base.r * (1 - alpha))),
    g: Math.round((top.g * alpha) + (base.g * (1 - alpha))),
    b: Math.round((top.b * alpha) + (base.b * (1 - alpha))),
  };
}

function run() {
  const min = Number(CONTRACT.minContrastAA || 4.5);

  const checks = [
    {
      name: 'owner_badge_compact_light',
      fg: hexToRgb(TOKENS.light.text),
      bg: blend(TOKENS.light.primary, CONTRACT.alphaLight, TOKENS.light.card),
      min,
    },
    {
      name: 'owner_badge_compact_dark',
      fg: hexToRgb(TOKENS.dark.text),
      bg: blend(TOKENS.dark.primary, CONTRACT.alphaDark, TOKENS.dark.card),
      min,
    },
    {
      name: 'basic_badge_light',
      fg: hexToRgb(TOKENS.light.text),
      bg: blend(TOKENS.light.primary, CONTRACT.alphaLight, TOKENS.light.card),
      min,
    },
    {
      name: 'basic_badge_dark',
      fg: hexToRgb(TOKENS.dark.text),
      bg: blend(TOKENS.dark.primary, CONTRACT.alphaLight, TOKENS.dark.card),
      min,
    },
    {
      name: 'premium_badge_light',
      fg: hexToRgb(TOKENS.light.text),
      bg: blend(TOKENS.light.success, CONTRACT.alphaLight, TOKENS.light.card),
      min,
    },
    {
      name: 'premium_badge_dark',
      fg: hexToRgb(TOKENS.dark.text),
      bg: blend(TOKENS.dark.success, CONTRACT.alphaLight, TOKENS.dark.card),
      min,
    },
  ];

  const failed = [];
  console.log('\n[contrast-gate] Checking badge contrast pairs');
  checks.forEach((c) => {
    const ratio = contrastRatio(c.fg, c.bg);
    const pass = ratio >= c.min;
    console.log(` - ${c.name}: ${ratio.toFixed(2)} (${pass ? 'PASS' : 'FAIL'})`);
    if (!pass) failed.push({ ...c, ratio });
  });

  if (failed.length) {
    console.error(`\n[contrast-gate] FAILED (${failed.length} pair(s) below ${min})`);
    process.exit(1);
  }

  console.log(`[contrast-gate] PASS (min ${min})`);
}

run();
