/**
 * siteConfig.ts — Single Source of Truth
 *
 * ALL navigation links, footer links, social links, and feature previews
 * are defined here. Both the Welcome page nav and the Footer component
 * consume this config. To add, remove, or update any feature/page,
 * ONLY edit this file — changes propagate automatically everywhere.
 */

export interface NavLink {
  label: string;
  i18nKey?: string;       // i18n translation key (auto-translation v2)
  section?: string;       // scroll-to section on welcome page (Features, Analytics)
  href?: string;          // direct navigation (Security, Pricing)
  public?: boolean;       // accessible without authentication
}

export interface FooterLink {
  label: string;
  i18nKey?: string;       // i18n translation key (auto-translation v2)
  href: string;
  public?: boolean;
}

export interface FooterSection {
  title: string;
  i18nKey?: string;       // i18n translation key for the section title
  links: FooterLink[];
}

export interface SocialLink {
  icon: string;
  label: string;
  slug: string;
  shortLabel?: string;
  accent?: string;
  intentLabel?: string;
  url?: string;
}

// ─── Welcome Page Top Navigation ───
export const NAV_LINKS: NavLink[] = [
  { label: 'Features', i18nKey: 'nav.features', section: 'features' },
  { label: 'Analytics', i18nKey: 'nav.analytics', section: 'analytics' },
  { label: 'Security', i18nKey: 'nav.security', section: 'security' },
  { label: 'Pricing', i18nKey: 'nav.pricing', section: 'pricing' },
];

// ─── Footer Link Sections ───
export const FOOTER_LINKS: Record<string, FooterSection> = {
  product: {
    title: 'Product',
    i18nKey: 'footer.section.product',
    links: [
      { label: 'AI Coaching Tools', i18nKey: 'footer.link.aiCoachingTools', href: '/feature-gallery' },
      { label: 'Learning Hub', i18nKey: 'footer.link.learningHub', href: '/ai-learning-hub' },
      { label: 'AI Coaching Team', i18nKey: 'footer.link.coachingTeam', href: '/ai-coaching-team' },
      { label: 'Integrations', i18nKey: 'footer.link.integrations', href: '/integrations' },
      { label: 'Pricing', i18nKey: 'footer.link.pricing', href: '/pricing', public: true },
    ],
  },
  resources: {
    title: 'Resources',
    i18nKey: 'footer.section.resources',
    links: [
      { label: 'Help Center', i18nKey: 'footer.link.helpCenter', href: '/help' },
      { label: 'My Analytics', i18nKey: 'footer.link.myAnalytics', href: '/my-analytics' },
      { label: 'Content Library', i18nKey: 'footer.link.contentLibrary', href: '/content-library' },
      { label: 'Daily Briefing', i18nKey: 'footer.link.dailyBriefing', href: '/ai-briefing' },
      { label: 'Leaderboard', i18nKey: 'footer.link.leaderboard', href: '/leaderboard' },
    ],
  },
  company: {
    title: 'Company',
    i18nKey: 'footer.section.company',
    links: [
      { label: 'About Us', i18nKey: 'footer.link.aboutUs', href: '/about-us', public: true },
      { label: 'Careers', i18nKey: 'footer.link.careers', href: '/careers', public: true },
      { label: 'Talent Network', i18nKey: 'footer.link.talentNetwork', href: '/talent-network?ref=footer-talent-network', public: true },
      { label: 'Blog', i18nKey: 'footer.link.blog', href: '/blog', public: true },
      { label: 'Press', i18nKey: 'footer.link.press', href: '/press', public: true },
      { label: 'Contact', i18nKey: 'footer.link.contact', href: '/contact', public: true },
    ],
  },
  legal: {
    title: 'Legal',
    i18nKey: 'footer.section.legal',
    links: [
      { label: 'Privacy Policy', i18nKey: 'footer.link.privacyPolicy', href: '/privacy-policy', public: true },
      { label: 'Manage My Data', i18nKey: 'footer.link.manageMyData', href: '/privacy-request', public: true },
      { label: 'Terms of Service', i18nKey: 'footer.link.termsOfService', href: '/terms', public: true },
      { label: 'Security', i18nKey: 'footer.link.security', href: '/security', public: true },
      { label: 'GDPR Compliance', i18nKey: 'footer.link.gdprCompliance', href: '/gdpr', public: true },
      { label: 'Cookie Policy', i18nKey: 'footer.link.cookiePolicy', href: '/cookies', public: true },
    ],
  },
};

// ─── Social Links ───
export const SOCIAL_LINKS: SocialLink[] = [
  { icon: 'logo-twitter', label: 'X / Twitter', shortLabel: 'X', slug: 'x', accent: '#1D9BF0', intentLabel: 'Live signals', url: 'https://x.com' },
  { icon: 'logo-linkedin', label: 'LinkedIn', shortLabel: 'LinkedIn', slug: 'linkedin', accent: '#0A66C2', intentLabel: 'Operator notes', url: 'https://www.linkedin.com' },
  { icon: 'logo-github', label: 'GitHub', shortLabel: 'GitHub', slug: 'github', accent: '#24292F', intentLabel: 'Build updates', url: 'https://github.com' },
  { icon: 'logo-youtube', label: 'YouTube', shortLabel: 'YouTube', slug: 'youtube', accent: '#FF0033', intentLabel: 'Product clips', url: 'https://www.youtube.com' },
  { icon: 'logo-instagram', label: 'Instagram', shortLabel: 'Instagram', slug: 'instagram', accent: '#E4405F', intentLabel: 'Behind the scenes', url: 'https://www.instagram.com' },
  { icon: 'logo-discord', label: 'Discord', shortLabel: 'Discord', slug: 'discord', accent: '#5865F2', intentLabel: 'Community chat', url: 'https://discord.com' },
];

// ─── App Metadata ───
export const APP_META = {
  name: 'RealAICoach',
  domain: 'realaicoach.app',
  tagline: 'Enterprise AI Coaching Platform',
  copyright: `${new Date().getFullYear()} RealAICoach. All rights reserved.`,
  supportEmail: 'support@realaicoach.app',
  address: '11501 Domain Dr, Suite 200\nAustin, TX 78758, USA',
};

