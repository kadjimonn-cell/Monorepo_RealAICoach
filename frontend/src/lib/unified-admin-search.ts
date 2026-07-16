import { EXECUTIVE_PHASE_B_HUBS } from '../config/phaseBTabConsolidation';

export interface UnifiedSearchItem {
  id: string;
  label: string;
  icon: string;
  source: 'executive' | 'operations';
  sourceLabel: string;
  catLabel?: string;
  catColor?: string;
  catId?: string;
}

export const EXEC_NAV_ITEMS: UnifiedSearchItem[] = [
  ...EXECUTIVE_PHASE_B_HUBS.map((hub) => ({
    id: hub.id,
    label: hub.label,
    icon: hub.icon,
    source: 'executive' as const,
    sourceLabel: 'Executive' as const,
  })),
];

export const OPS_SEO_ITEMS: UnifiedSearchItem[] = [
  { id: 'seo-dashboard', label: 'SEO & ASO Command Center', icon: 'search', source: 'operations', sourceLabel: 'Operations', catLabel: 'Analytics', catColor: '#F59E0B', catId: 'analytics' },
  { id: 'ai-insights', label: 'AI Insights & Recommendations', icon: 'bulb', source: 'operations', sourceLabel: 'Operations', catLabel: 'Analytics', catColor: '#F59E0B', catId: 'analytics' },
  { id: 'automation-engine', label: 'Automation Engine', icon: 'flash', source: 'operations', sourceLabel: 'Operations', catLabel: 'Operations', catColor: '#14B8A6', catId: 'operations' },
  { id: 'notification-history', label: 'Notification History', icon: 'notifications', source: 'operations', sourceLabel: 'Operations', catLabel: 'Support', catColor: '#10B981', catId: 'support' },
  { id: 'executive-quality-dashboard', label: 'Executive Quality Dashboard', icon: 'shield-half', source: 'operations', sourceLabel: 'Operations', catLabel: 'Analytics', catColor: '#F59E0B', catId: 'analytics' },
  { id: 'languages', label: 'Language Quality Dashboard', icon: 'language', source: 'operations', sourceLabel: 'Operations', catLabel: 'Communications', catColor: '#A855F7', catId: 'comms' },
];
