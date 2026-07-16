import React, { useMemo } from 'react';
import { View, Text, Platform, useWindowDimensions, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { BODY_FONT_FAMILY, DISPLAY_FONT_FAMILY } from '../../constants/appTypography';

type PulseData = {
  profile_complete: boolean;
  status_counts: Record<string, number>;
  tracked: number;
  new_matching_count: number;
  new_matching_top: Array<{ job_id: string; title: string }>;
  best_fit_score: number;
  best_fit_job_title: string;
  kits_this_week: number;
  apps_this_week: number;
};

export default function HomeJobHuntPulse({ responsiveWidth }: { responsiveWidth?: number }) {
  const { width: windowWidth } = useWindowDimensions();
  const width = responsiveWidth || windowWidth;
  const isDesktop = width >= 768;
  const { colors, darkMode } = useTheme();
  const { tx } = useTranslation();
  const router = useRouter();

  const { data } = useLiveQuery('/job-search/pulse', { entity: 'job_search_pulse', pollInterval: 60000 });
  const pulse: PulseData | null = data || null;

  const alpha = (c: string, a: string) => (globalThis as any).__alphaColor?.(c, a) || c;
  const surfaceBorder = darkMode ? 'rgba(255,255,255,0.06)' : colors.border;

  const stats = useMemo(() => {
    const counts = pulse?.status_counts || {};
    return [
      { key: 'applied', value: counts.applied || 0, label: tx('home.jobPulse.applied', 'Applied'), color: colors.primary, icon: 'paper-plane-outline' },
      { key: 'interviews', value: counts.interview || 0, label: tx('home.jobPulse.interviews', 'Interviews'), color: colors.warningText, icon: 'chatbubbles-outline' },
      { key: 'offers', value: counts.offer || 0, label: tx('home.jobPulse.offers', 'Offers'), color: colors.successText, icon: 'trophy-outline' },
      { key: 'tracked', value: pulse?.tracked || 0, label: tx('home.jobPulse.tracked', 'Tracked'), color: colors.indigoText || colors.purple, icon: 'albums-outline' },
    ];
  }, [pulse, colors, tx]);

  if (!pulse) return null;

  if (Platform.OS !== 'web') {
    return (
      <View data-testid="home-job-hunt-pulse" testID="home-job-hunt-pulse" style={{ paddingHorizontal: 20, paddingBottom: 24 }}>
        <View style={{ padding: 16, borderRadius: 16, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border }}>
          <Text style={{ fontSize: 17, fontWeight: '800', color: colors.text }}>{tx('home.jobPulse.title', 'Job Hunt Pulse')}</Text>
          <TouchableOpacity onPress={() => router.push('/job-search')} style={{ marginTop: 10 }} data-testid="home-job-pulse-cta" testID="home-job-pulse-cta">
            <Text style={{ color: colors.primary, fontWeight: '700', fontSize: 13 }}>{tx('home.jobPulse.cta', 'Open Job Search')}</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  return (
    <View data-testid="home-job-hunt-pulse" testID="home-job-hunt-pulse" style={{ paddingHorizontal: isDesktop ? 40 : 20, paddingBottom: 32 }}>
      <div style={{
        padding: 22, borderRadius: 18,
        background: colors.card,
        border: `1px solid ${surfaceBorder}`,
        boxShadow: darkMode ? '0 18px 40px rgba(0,0,0,0.26)' : '0 14px 30px rgba(15,23,42,0.08)',
      } as any}>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 16 } as any}>
          <div>
            <span style={{ color: colors.textMuted, fontSize: 10, fontWeight: 800, letterSpacing: 1.8, textTransform: 'uppercase', fontFamily: BODY_FONT_FAMILY } as any} data-testid="home-job-pulse-kicker">
              {tx('home.jobPulse.kicker', 'Job hunt pulse')}
            </span>
            <div style={{ color: colors.text, fontSize: 18, fontWeight: 800, letterSpacing: -0.5, marginTop: 6, fontFamily: DISPLAY_FONT_FAMILY } as any} data-testid="home-job-pulse-title">
              {tx('home.jobPulse.title', 'Job Hunt Pulse')}
            </div>
            <div style={{ color: colors.textMuted, fontSize: 12, marginTop: 4, fontFamily: BODY_FONT_FAMILY } as any}>
              {tx('home.jobPulse.subtitle', 'Your job search at a glance — matches, applications, and momentum this week.')}
            </div>
          </div>
          <button
            onClick={() => router.push('/job-search')}
            data-testid="home-job-pulse-cta"
            style={{
              padding: '9px 18px', borderRadius: 999, fontSize: 12, fontWeight: 800, cursor: 'pointer',
              fontFamily: BODY_FONT_FAMILY, background: colors.primary, color: colors.primaryText,
              border: `1px solid ${colors.primary}`, transition: 'opacity 0.2s ease',
            } as any}
          >
            {pulse.profile_complete ? tx('home.jobPulse.cta', 'Open Job Search') : tx('home.jobPulse.setupCta', 'Set up profile')}
          </button>
        </div>

        {!pulse.profile_complete ? (
          <div style={{ padding: '20px 16px', borderRadius: 12, border: `1px dashed ${surfaceBorder}`, textAlign: 'center' } as any} data-testid="home-job-pulse-setup">
            <div style={{ color: colors.text, fontSize: 14, fontWeight: 800, fontFamily: DISPLAY_FONT_FAMILY } as any}>
              {tx('home.jobPulse.setupTitle', 'Set up your career profile')}
            </div>
            <div style={{ color: colors.textMuted, fontSize: 12, marginTop: 6, fontFamily: BODY_FONT_FAMILY } as any}>
              {tx('home.jobPulse.setupHint', 'Add your skills and target roles to unlock personalized job matches and weekly pulse insights.')}
            </div>
          </div>
        ) : (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: isDesktop ? 'repeat(4, minmax(0, 1fr))' : 'repeat(2, minmax(0, 1fr))', gap: 10, marginBottom: 14 } as any} data-testid="home-job-pulse-stats">
              {stats.map((s) => (
                <div key={s.key} data-testid={`home-job-pulse-stat-${s.key}`} style={{
                  padding: '12px 14px', borderRadius: 12,
                  background: alpha(s.color, '0D'),
                  border: `1px solid ${alpha(s.color, '26')}`,
                  display: 'flex', alignItems: 'center', gap: 10,
                } as any}>
                  <Ionicons name={s.icon as any} size={17} color={s.color} />
                  <div>
                    <div style={{ color: colors.text, fontSize: 18, fontWeight: 900, fontFamily: DISPLAY_FONT_FAMILY, lineHeight: 1.1 } as any}>{s.value}</div>
                    <div style={{ color: colors.textMuted, fontSize: 10, fontWeight: 800, textTransform: 'uppercase', letterSpacing: 0.6, fontFamily: BODY_FONT_FAMILY } as any}>{s.label}</div>
                  </div>
                </div>
              ))}
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 } as any}>
              <div style={{ padding: '12px 14px', borderRadius: 12, border: `1px solid ${surfaceBorder}`, background: darkMode ? colors.cardMuted : colors.bgSoft } as any} data-testid="home-job-pulse-matches">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 } as any}>
                  <Ionicons name="sparkles-outline" size={14} color={colors.successText} />
                  <span style={{ color: colors.text, fontSize: 13, fontWeight: 800, fontFamily: BODY_FONT_FAMILY } as any}>
                    {pulse.new_matching_count} {tx('home.jobPulse.newMatches', 'new matching roles this week')}
                  </span>
                </div>
                {pulse.new_matching_count === 0 ? (
                  <div style={{ color: colors.textMuted, fontSize: 11, marginTop: 6, fontFamily: BODY_FONT_FAMILY } as any}>
                    {tx('home.jobPulse.noMatches', 'No new matching roles yet — new openings land here as soon as they match your profile.')}
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 } as any}>
                    {(pulse.new_matching_top || []).map((job, i) => (
                      <span key={job.job_id || i} data-testid={`home-job-pulse-match-${i}`} style={{
                        fontSize: 11, fontWeight: 700, color: colors.successText, padding: '4px 10px', borderRadius: 999,
                        backgroundColor: alpha(colors.success, '12'), border: `1px solid ${alpha(colors.success, '28')}`,
                        fontFamily: BODY_FONT_FAMILY,
                      } as any}>
                        {job.title}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, padding: '10px 14px', borderRadius: 12, border: `1px solid ${surfaceBorder}` } as any} data-testid="home-job-pulse-week-row">
                <span style={{ color: colors.textMuted, fontSize: 11, fontFamily: BODY_FONT_FAMILY } as any}>
                  <span style={{ color: colors.text, fontWeight: 800 } as any}>{pulse.best_fit_score || 0}%</span> {tx('home.jobPulse.bestFit', 'best fit this week')}{pulse.best_fit_job_title ? ` · ${pulse.best_fit_job_title}` : ''}
                </span>
                <span style={{ color: colors.textMuted, fontSize: 11, fontFamily: BODY_FONT_FAMILY } as any}>
                  <span style={{ color: colors.text, fontWeight: 800 } as any}>{pulse.kits_this_week || 0}</span> {tx('home.jobPulse.kits', 'kits this week')}
                </span>
                <span style={{ color: colors.textMuted, fontSize: 11, fontFamily: BODY_FONT_FAMILY } as any}>
                  <span style={{ color: colors.text, fontWeight: 800 } as any}>{pulse.apps_this_week || 0}</span> {tx('home.jobPulse.appsWeek', 'applications this week')}
                </span>
              </div>
            </div>
          </>
        )}
      </div>
    </View>
  );
}
