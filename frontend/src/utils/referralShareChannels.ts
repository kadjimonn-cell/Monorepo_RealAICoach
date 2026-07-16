const encode = (value: string) => encodeURIComponent(value || '');

export type ShareChannelKey =
  | 'whatsapp'
  | 'x'
  | 'linkedin'
  | 'telegram'
  | 'facebook'
  | 'reddit'
  | 'email'
  | 'tiktok'
  | 'youtube'
  | 'copy';

export interface ShareChannelOption {
  key: ShareChannelKey;
  label: string;
  icon: string;
  buildUrl: (link: string, message: string) => string;
}

export type ShareVariantKey = 'short' | 'long' | 'benefit';

export const SHARE_VARIANT_OPTIONS: { key: ShareVariantKey; label: string }[] = [
  { key: 'short', label: 'Short' },
  { key: 'long', label: 'Long' },
  { key: 'benefit', label: 'Benefit-first' },
];

export function shareVariantLabel(variant: ShareVariantKey): string {
  return SHARE_VARIANT_OPTIONS.find((item) => item.key === variant)?.label || 'Benefit-first';
}

export function shareVariantMessage(variant: ShareVariantKey, link: string): string {
  switch (variant) {
    case 'short':
      return `Join me on RealAICoach Blog: ${link}`;
    case 'long':
      return `I’m building a reading streak with RealAICoach Blog. Join with my invite link to get curated insights and weekly digest picks: ${link}`;
    case 'benefit':
      return `Use my RealAICoach invite to unlock streak rewards, referral boosts, and premium insight unlock tokens: ${link}`;
    default:
      return `Join me on RealAICoach Blog: ${link}`;
  }
}

export const SHARE_CHANNELS: ShareChannelOption[] = [
  {
    key: 'whatsapp',
    label: 'WhatsApp',
    icon: 'logo-whatsapp',
    buildUrl: (link, message) => `https://wa.me/?text=${encode(`${message} ${link}`)}`,
  },
  {
    key: 'x',
    label: 'X',
    icon: 'logo-twitter',
    buildUrl: (link, message) => `https://twitter.com/intent/tweet?text=${encode(message)}&url=${encode(link)}`,
  },
  {
    key: 'linkedin',
    label: 'LinkedIn',
    icon: 'logo-linkedin',
    buildUrl: (link, message) => `https://www.linkedin.com/sharing/share-offsite/?url=${encode(link)}&summary=${encode(message)}`,
  },
  {
    key: 'telegram',
    label: 'Telegram',
    icon: 'paper-plane-outline',
    buildUrl: (link, message) => `https://t.me/share/url?url=${encode(link)}&text=${encode(message)}`,
  },
  {
    key: 'facebook',
    label: 'Facebook',
    icon: 'logo-facebook',
    buildUrl: (link) => `https://www.facebook.com/sharer/sharer.php?u=${encode(link)}`,
  },
  {
    key: 'reddit',
    label: 'Reddit',
    icon: 'logo-reddit',
    buildUrl: (link, message) => `https://www.reddit.com/submit?url=${encode(link)}&title=${encode(message)}`,
  },
  {
    key: 'email',
    label: 'Email',
    icon: 'mail-outline',
    buildUrl: (link, message) => `mailto:?subject=${encode('Join me on RealAICoach Blog')}&body=${encode(`${message}\n\n${link}`)}`,
  },
  {
    key: 'tiktok',
    label: 'TikTok',
    icon: 'logo-tiktok',
    buildUrl: (link, message) => `https://www.tiktok.com/share?url=${encode(link)}&title=${encode(message)}`,
  },
  {
    key: 'youtube',
    label: 'YouTube',
    icon: 'logo-youtube',
    buildUrl: (link, message) => `https://www.youtube.com/` + `?share=${encode(`${message} ${link}`)}`,
  },
  {
    key: 'copy',
    label: 'Copy Link',
    icon: 'copy-outline',
    buildUrl: (link) => link,
  },
];
