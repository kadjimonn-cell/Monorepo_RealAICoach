export const IDENTITY_LAYOUT = {
  userCard: {
    compact: {
      gap: 10,
      paddingX: 10,
      paddingY: 10,
      avatarSize: 36,
      avatarRadius: 18,
    },
    regular: {
      gap: 12,
      paddingX: 12,
      paddingY: 12,
      avatarSize: 36,
      avatarRadius: 18,
    },
  },
  ownerBadge: {
    compactMinWidth: 52,
    compactText: 'ADMIN',
    fullText: 'OWNER',
    alphaLight: '18',
    alphaDark: '2E',
    borderAlpha: '72',
  },
  qualityGates: {
    minContrastAA: 4.5,
  },
} as const;
