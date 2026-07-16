import React, { useEffect, useState } from 'react';
import { Modal, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';
import { useTranslation } from '../hooks/useTranslation';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import { handleAppRecoverableError } from '../utils/appRecoverableError';
import { withAlpha } from '../utils/colorAlpha';

interface EnterpriseAIDisclaimerProps {
  testIdPrefix: string;
  maxWidth?: number;
  legalProfile?: 'default' | 'strict_regulated';
  alignContent?: 'start' | 'center';
}

type LegalProfile = 'default' | 'strict_regulated';

const PROFILE_MAP_RAW = process.env.EXPO_PUBLIC_DISCLAIMER_PROFILE_MAP || '{}';
const DEFAULT_PROFILE_RAW = process.env.EXPO_PUBLIC_DEFAULT_DISCLAIMER_PROFILE || 'default';

function asLegalProfile(value: any): LegalProfile | null {
  if (value === 'strict_regulated') return 'strict_regulated';
  if (value === 'default') return 'default';
  return null;
}

function parseProfileMap(): Record<string, LegalProfile> {
  try {
    const parsed = JSON.parse(PROFILE_MAP_RAW);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
    const out: Record<string, LegalProfile> = {};
    for (const [key, value] of Object.entries(parsed)) {
      const normalized = asLegalProfile(value);
      if (normalized) out[String(key).toLowerCase()] = normalized;
    }
    return out;
  } catch {
    return {};
  }
}

const PROFILE_MAP = parseProfileMap();
const DEFAULT_PROFILE = asLegalProfile(DEFAULT_PROFILE_RAW) || 'default';

function resolveTenantMappedProfile(user: any): LegalProfile {
  const email = String(user?.email || '').toLowerCase().trim();
  const domain = email.includes('@') ? email.split('@').pop() || '' : '';

  const candidateKeys = [
    String(user?.tenant_id || '').toLowerCase().trim(),
    String(user?.organization_id || '').toLowerCase().trim(),
    String(user?.company_id || '').toLowerCase().trim(),
    String(user?.workspace_id || '').toLowerCase().trim(),
    domain,
  ].filter(Boolean);

  for (const key of candidateKeys) {
    const mapped = PROFILE_MAP[key];
    if (mapped) return mapped;
  }

  return DEFAULT_PROFILE;
}

export default function EnterpriseAIDisclaimer({
  testIdPrefix,
  maxWidth = 860,
  legalProfile,
  alignContent = 'start',
}: EnterpriseAIDisclaimerProps) {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const { user } = useAuth();
  const [modalVisible, setModalVisible] = useState(false);
  const [backendResolvedProfile, setBackendResolvedProfile] = useState<LegalProfile | null>(null);

  const userSnapshot = user as any;
  const userTenantProfile = asLegalProfile(userSnapshot?.tenant_disclaimer_profile);
  const tenantId = String(userSnapshot?.tenant_id || '').trim();
  const organizationId = String(userSnapshot?.organization_id || '').trim();
  const companyId = String(userSnapshot?.company_id || '').trim();
  const workspaceId = String(userSnapshot?.workspace_id || '').trim();

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams();
    const appendParam = (key: string, value?: string | null) => {
      const normalized = String(value || '').trim();
      if (normalized) params.set(key, normalized);
    };

    appendParam('email', userSnapshot?.email || null);
    appendParam('tenant_id', tenantId || null);
    appendParam('organization_id', organizationId || null);
    appendParam('company_id', companyId || null);
    appendParam('workspace_id', workspaceId || null);
    if (typeof window !== 'undefined') {
      appendParam('host', window.location.hostname);
    }

    const query = params.toString();
    api.get(`/public/tenant-disclaimer-profile${query ? `?${query}` : ''}`, { silentLoading: true })
      .then((response) => {
        if (cancelled) return;
        const nextProfile = asLegalProfile(response?.data?.legal_profile);
        setBackendResolvedProfile(nextProfile);
      })
      .catch(() => {
        if (cancelled) return;
        setBackendResolvedProfile(null);
      });

    return () => {
      cancelled = true;
    };
  }, [userSnapshot?.email, userSnapshot?.user_id, tenantId, organizationId, companyId, workspaceId]);

  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const resolvedProfile: LegalProfile =
    legalProfile || userTenantProfile || backendResolvedProfile || resolveTenantMappedProfile(userSnapshot);
  const isCentered = alignContent === 'center';
  const viewportWidth = typeof window !== 'undefined' ? window.innerWidth : maxWidth;
  const isCompactWeb = viewportWidth < 430;
  const isTabletLike = viewportWidth >= 430 && viewportWidth < 1180;
  const isStrict = resolvedProfile === 'strict_regulated';
  const primaryText = isStrict
    ? tx('disclaimer.strict.primary', 'RealAICoach can make mistakes. AI output may be inaccurate, incomplete, or unsuitable for regulated use.')
    : tx('home.footer.disclaimer.primary', 'RealAICoach can make mistakes. AI-assisted outputs may be inaccurate or incomplete.');
  const secondaryText = isStrict
    ? tx('disclaimer.strict.secondary', 'Independent human verification is required before any legal, financial, medical, compliance, or safety-critical decision.')
    : tx('home.footer.disclaimer.secondary', 'Please validate critical information before making legal, financial, medical, compliance, or safety decisions.');
  const modalTitle = isStrict
    ? tx('disclaimer.strict.modal.title', 'AI Use in Regulated Contexts')
    : tx('disclaimer.modal.title', 'AI Limitations & Responsible Use');
  const modalIntro = isStrict
    ? tx('disclaimer.strict.modal.intro', 'This workspace uses AI assistance under strict governance expectations. Human accountability remains mandatory.')
    : tx('disclaimer.modal.intro', 'RealAICoach provides AI-assisted guidance to support decisions. It does not replace human judgment.');
  const modalPoints = isStrict
    ? [
      tx('disclaimer.strict.modal.point1', 'Treat AI output as draft guidance, not authoritative evidence.'),
      tx('disclaimer.strict.modal.point2', 'Perform independent source verification and document reviewer approval.'),
      tx('disclaimer.strict.modal.point3', 'Apply policy, regulatory, and contractual controls before operational use.'),
      tx('disclaimer.strict.modal.point4', 'Never use AI output as the sole basis for legal, financial, medical, compliance, or safety-critical actions.'),
    ]
    : [
      tx('disclaimer.modal.point1', 'AI outputs may occasionally be incorrect, incomplete, or outdated.'),
      tx('disclaimer.modal.point2', 'Always verify important information with trusted sources before acting.'),
      tx('disclaimer.modal.point3', 'Use human review and professional judgment for high-impact decisions.'),
      tx('disclaimer.modal.point4', 'Do not use AI output as the sole basis for legal, financial, medical, compliance, or safety-critical actions.'),
    ];
  const modalCloseText = isStrict
    ? tx('disclaimer.strict.modal.close', 'Acknowledge')
    : tx('disclaimer.modal.close', 'Got it');
  const learnMoreText = isStrict
    ? tx('disclaimer.strict.learnMore', 'Learn more')
    : tx('disclaimer.learnMore', 'Learn more');

  const trackDisclaimerEvent = async (eventType: 'disclaimer_modal_open' | 'disclaimer_modal_close') => {
    try {
      await api.post('/admin/autonomous-engine/feedback/collect', {
        event_type: eventType,
        route: typeof window !== 'undefined' ? window.location.pathname : 'unknown',
        metadata: {
          source: testIdPrefix,
          component: 'EnterpriseAIDisclaimer',
          legal_profile: resolvedProfile,
        },
      }, { silentLoading: true });
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/EnterpriseAIDisclaimer.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const handleOpen = () => {
    setModalVisible(true);
    trackDisclaimerEvent('disclaimer_modal_open');
  };

  const handleClose = () => {
    setModalVisible(false);
    trackDisclaimerEvent('disclaimer_modal_close');
  };

  return (
    <>
      <View
        style={{
          maxWidth,
          width: '100%',
          borderWidth: 1,
          borderColor: colors.border,
          borderRadius: 12,
          backgroundColor: colors.card,
          paddingHorizontal: isCentered ? (isCompactWeb ? 16 : isTabletLike ? 24 : 22) : 14,
          paddingTop: isCentered ? (isCompactWeb ? 12 : 12) : 10,
          paddingBottom: isCentered ? (isCompactWeb ? 16 : isTabletLike ? 18 : 14) : 10,
          flexDirection: isCentered ? 'column' : 'row',
          alignItems: isCentered ? 'center' : 'flex-start',
          justifyContent: 'center',
          gap: isCentered ? (isCompactWeb ? 8 : 12) : 8,
        }}
        data-testid={`${testIdPrefix}-container`}
        testID={`${testIdPrefix}-container`}
      >
        <Ionicons name="shield-checkmark-outline" size={16} color={colors.primary} style={isCentered ? undefined : { marginTop: 1 }} />
        <View
          style={{
            width: '100%',
            alignItems: isCentered ? 'center' : 'flex-start',
            ...(isCentered
              ? {
                  flexGrow: 0,
                  flexShrink: 0,
                  flexBasis: 'auto' as any,
                }
              : {
                  flexGrow: 1,
                  flexShrink: 1,
                  flexBasis: 0 as any,
                }),
          }}
        >
          <Text
            style={{ color: colors.textMuted, fontSize: isCompactWeb ? 10.5 : 11, fontWeight: '700', lineHeight: isCompactWeb ? 15 : 16, textAlign: isCentered ? 'center' : 'left' }}
            data-testid={`${testIdPrefix}-primary`}
            testID={`${testIdPrefix}-primary`}
          >
              {primaryText}
          </Text>

          <Text
            style={{ color: colors.textMuted, fontSize: isCompactWeb ? 10.5 : 11, marginTop: isCompactWeb ? 3 : 4, lineHeight: isCompactWeb ? 15 : 16, textAlign: isCentered ? 'center' : 'left' }}
            data-testid={`${testIdPrefix}-secondary`}
            testID={`${testIdPrefix}-secondary`}
          >
              {secondaryText}
          </Text>

          <TouchableOpacity
            onPress={handleOpen}
            style={{ marginTop: isCentered ? (isCompactWeb ? 6 : 8) : 6, alignSelf: isCentered ? 'center' : 'flex-start', flexDirection: 'row', alignItems: 'center', gap: 4, minHeight: isCentered && isCompactWeb ? 24 : undefined }}
            data-testid={`${testIdPrefix}-learn-more-link`}
            testID={`${testIdPrefix}-learn-more-link`}
          >
            <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '700' }}>
              {learnMoreText}
            </Text>
            <Ionicons name="open-outline" size={11} color={colors.primary} />
          </TouchableOpacity>
        </View>
      </View>

      <Modal visible={modalVisible} transparent animationType="fade" onRequestClose={handleClose}>
        <View
          style={{
            flex: 1,
            backgroundColor: withAlpha(colors.overlay, 'D9'),
            justifyContent: 'center',
            alignItems: 'center',
            paddingHorizontal: 18,
          }}
          data-testid={`${testIdPrefix}-modal-backdrop`}
          testID={`${testIdPrefix}-modal-backdrop`}
        >
          <View
            style={{
              width: '100%',
              maxWidth: 580,
              borderRadius: 14,
              backgroundColor: colors.card,
              borderWidth: 1,
              borderColor: colors.border,
              padding: 16,
            }}
            data-testid={`${testIdPrefix}-modal-card`}
            testID={`${testIdPrefix}-modal-card`}
          >
            <Text style={{ color: colors.text, fontSize: 17, fontWeight: '800' }} data-testid={`${testIdPrefix}-modal-title`} testID={`${testIdPrefix}-modal-title`}>
              {modalTitle}
            </Text>

            <Text style={{ color: colors.textMuted, fontSize: 12, lineHeight: 18, marginTop: 8 }}>
              {modalIntro}
            </Text>

            <View style={{ marginTop: 10, gap: 6 }}>
              {modalPoints.map((point, i) => (
                <View key={`${testIdPrefix}-point-${i + 1}`} style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 8 }}>
                  <Ionicons name="ellipse" size={7} color={colors.primary} style={{ marginTop: 6 }} />
                  <Text style={{ flex: 1, color: colors.textMuted, fontSize: 12, lineHeight: 18 }}>
                    {point}
                  </Text>
                </View>
              ))}
            </View>

            <TouchableOpacity accessibilityLabel={tx('enterpriseAiDisclaimer.accessibility.close', 'Close enterprise AI disclaimer')}
              onPress={handleClose}
              style={{
                marginTop: 14,
                alignSelf: 'flex-end',
                paddingHorizontal: 14,
                paddingVertical: 8,
                borderRadius: 10,
                backgroundColor: colors.primary,
              }}
              data-testid={`${testIdPrefix}-modal-close`}
              testID={`${testIdPrefix}-modal-close`}
            >
              <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }}>
                {modalCloseText}
              </Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </>
  );
}
