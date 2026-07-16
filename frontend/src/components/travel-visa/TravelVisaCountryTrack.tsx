import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Platform, Text, TouchableOpacity, useWindowDimensions, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import CountryFlag from '../CountryFlag';
import { useTheme } from '../../context/ThemeContext';
import { useLanguage } from '../../i18n/LanguageContext';
import api from '../../services/api';

type Props = {
  countryCode: string;
  userId: string;
  onBack: () => void;
  onUpgradePress: (trigger: 'locked_content' | 'daily_limit') => void;
};

const WEB_TRANSITION = Platform.OS === 'web'
  ? ({ transitionProperty: 'transform,opacity,background-color,border-color', transitionDuration: '180ms', transitionTimingFunction: 'ease' } as any)
  : {};

function toText(v: any) {
  if (v === null || v === undefined) return '';
  return String(v);
}

export default function TravelVisaCountryTrack({ countryCode, userId, onBack, onUpgradePress }: Props) {
  const { colors } = useTheme();
  const { t } = useLanguage();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { width } = useWindowDimensions();
  const isMobile = width < 960;
  const trackCardWidth = width < 560 ? '100%' : width < 960 ? '47.8%' : '31.5%';

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [data, setData] = useState<any>(null);
  const [expandedTrack, setExpandedTrack] = useState('');

  const [selectedVisaType, setSelectedVisaType] = useState('');
  const [checklist, setChecklist] = useState<any[]>([]);
  const [checklistLoading, setChecklistLoading] = useState(false);
  const [checklistError, setChecklistError] = useState('');

  const loadTrack = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get(`/travel-visa/countries/${encodeURIComponent(countryCode)}/track?user_id=${encodeURIComponent(userId)}`, { silentLoading: true });
      setData(res.data || null);
    } catch (e: any) {
      setError(e?.response?.data?.detail || tx('travelVisa.countryTrack.loadFailed', 'Could not load this country track. Please retry.'));
    }
    setLoading(false);
  }, [countryCode, userId, tx]);

  useEffect(() => {
    setExpandedTrack('');
    setChecklist([]);
    setChecklistError('');
    setSelectedVisaType('');
    void loadTrack();
  }, [loadTrack]);

  const generateChecklist = useCallback(async () => {
    if (!selectedVisaType || checklistLoading) return;
    setChecklistLoading(true);
    setChecklistError('');
    setChecklist([]);
    try {
      const res = await api.post('/travel-visa/checklist/generate', {
        user_id: userId,
        country: toText(data?.country?.name || countryCode),
        visa_type: selectedVisaType,
      }, { silentLoading: true });
      setChecklist(Array.isArray(res.data?.checklist) ? res.data.checklist : []);
    } catch (e: any) {
      if (e?.response?.status === 429) {
        onUpgradePress('daily_limit');
        setChecklistError(tx('travelVisa.countryTrack.checklistLimit', 'Daily AI limit reached for your plan. Upgrade to generate more checklists.'));
      } else {
        setChecklistError(e?.response?.data?.detail || tx('travelVisa.countryTrack.checklistFailed', 'Checklist generation failed. Please retry.'));
      }
    }
    setChecklistLoading(false);
  }, [selectedVisaType, checklistLoading, userId, data, countryCode, onUpgradePress, tx]);

  const tierBadge = (tier: string) => {
    const map: Record<string, { bg: string; fg: string; border: string }> = {
      free: { bg: colors.successSoft, fg: colors.successText, border: colors.success },
      basic: { bg: colors.primarySoft, fg: colors.primary, border: colors.primary },
      premium: { bg: colors.warningSoft, fg: colors.warningText, border: colors.warning },
    };
    return map[tier] || map.free;
  };

  const country = data?.country || {};
  const tracks: any[] = data?.tracks || [];
  const visaTypes: string[] = data?.visa_types || [];

  if (loading) {
    return (
      <View data-testid="tv-v2-country-track-loading" style={{ alignItems: 'center', justifyContent: 'center', padding: 60 }}>
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={{ color: colors.textMuted, marginTop: 10, fontSize: 13 }}>{tx('travelVisa.countryTrack.loading', 'Loading country visa track...')}</Text>
      </View>
    );
  }

  if (error) {
    return (
      <View data-testid="tv-v2-country-track-error" style={{ margin: isMobile ? 14 : 20, borderRadius: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '55'), backgroundColor: colors.errorSoft, padding: 14 }}>
        <Text style={{ fontSize: 12, color: colors.errorText, fontWeight: '700', marginBottom: 10 }}>{error}</Text>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TouchableOpacity data-testid="tv-v2-country-track-retry" onPress={() => void loadTrack()} style={{ borderRadius: 8, backgroundColor: colors.error, paddingHorizontal: 12, paddingVertical: 7 }}>
            <Text style={{ fontSize: 11, color: colors.buttonText, fontWeight: '800' }}>{tx('travelVisa.actions.retryLoad', 'Retry Load')}</Text>
          </TouchableOpacity>
          <TouchableOpacity data-testid="tv-v2-country-track-back" onPress={onBack} style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, paddingHorizontal: 12, paddingVertical: 7 }}>
            <Text style={{ fontSize: 11, color: colors.textSec, fontWeight: '800' }}>{tx('travelVisa.countryTrack.backToExplore', 'Back to Explore')}</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  return (
    <View data-testid="tv-v2-country-track" testID="tv-v2-country-track" style={{ padding: isMobile ? 14 : 20, gap: 14 }}>
      <TouchableOpacity
        data-testid="tv-v2-country-track-back"
        testID="tv-v2-country-track-back"
        onPress={onBack}
        style={{ flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start', borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, paddingHorizontal: 12, paddingVertical: 7, ...WEB_TRANSITION }}
      >
        <Ionicons name="arrow-back" size={14} color={colors.textSec} />
        <Text style={{ fontSize: 11, color: colors.textSec, fontWeight: '800' }}>{tx('travelVisa.countryTrack.backToExplore', 'Back to Explore')}</Text>
      </TouchableOpacity>

      <View data-testid="tv-v2-country-track-hero" style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <CountryFlag code={country.code} emoji={country.flag} size={26} />
          <Text style={{ fontSize: isMobile ? 20 : 24, fontWeight: '900', color: colors.text, flexShrink: 1 }}>{toText(country.name)}</Text>
        </View>
        <Text style={{ fontSize: 11, color: colors.textMuted, marginTop: 6 }}>
          {`${toText(country.region) || '-'} • ${toText(country.difficulty) || 'medium'} difficulty • ${data?.embassies_count ?? 0} embassies`}
        </Text>
        {visaTypes.length > 0 && (
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 10 }}>
            {visaTypes.map((vt) => (
              <View key={vt} style={{ borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, paddingHorizontal: 9, paddingVertical: 4 }}>
                <Text style={{ fontSize: 10, color: colors.textSec, fontWeight: '700' }}>{vt}</Text>
              </View>
            ))}
          </View>
        )}
      </View>

      <View style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }}>
        <Text style={{ fontSize: 13, color: colors.text, fontWeight: '700', marginBottom: 8 }}>{tx('travelVisa.countryTrack.visaTracks', 'Visa Lesson Tracks')}</Text>
        {tracks.length === 0 ? (
          <Text data-testid="tv-v2-country-track-empty" style={{ fontSize: 11, color: colors.textMuted }}>{tx('travelVisa.countryTrack.noTracks', 'No dedicated visa tracks are available for this country yet.')}</Text>
        ) : (
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {tracks.map((track) => {
              const badge = tierBadge(toText(track.tier));
              const expanded = expandedTrack === track.category_id;
              return (
                <View key={track.category_id} data-testid={`tv-v2-track-${track.category_id}`} style={{ width: expanded ? '100%' : trackCardWidth, borderRadius: 10, borderWidth: 1, borderColor: expanded ? colors.primary : colors.border, backgroundColor: colors.surfaceHover, padding: 10, ...WEB_TRANSITION }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Text style={{ fontSize: 12, color: colors.text, fontWeight: '800', flex: 1 }} numberOfLines={2}>{toText(track.track_label)}</Text>
                    <View style={{ borderRadius: 999, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(badge.border, '66'), backgroundColor: badge.bg, paddingHorizontal: 7, paddingVertical: 2 }}>
                      <Text style={{ fontSize: 9, color: badge.fg, fontWeight: '800', textTransform: 'uppercase' }}>{toText(track.tier)}</Text>
                    </View>
                  </View>
                  <Text style={{ fontSize: 10, color: colors.textMuted, marginTop: 5 }}>
                    {`${track.lesson_count} lessons • ${track.completed_count} completed`}
                  </Text>
                  {track.locked ? (
                    <TouchableOpacity
                      data-testid={`tv-v2-track-unlock-${track.category_id}`}
                      onPress={() => onUpgradePress('locked_content')}
                      style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, marginTop: 9, borderRadius: 8, backgroundColor: colors.primary, paddingVertical: 7, ...WEB_TRANSITION }}
                    >
                      <Ionicons name="lock-closed" size={12} color={colors.primaryText} />
                      <Text style={{ fontSize: 10, color: colors.primaryText, fontWeight: '800' }}>
                        {`${tx('travelVisa.countryTrack.unlockWith', 'Unlock with')} ${toText(track.tier).toUpperCase()}`}
                      </Text>
                    </TouchableOpacity>
                  ) : (
                    <TouchableOpacity
                      data-testid={`tv-v2-track-toggle-${track.category_id}`}
                      onPress={() => setExpandedTrack(expanded ? '' : track.category_id)}
                      style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, marginTop: 9, borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, paddingVertical: 7, ...WEB_TRANSITION }}
                    >
                      <Ionicons name={expanded ? 'chevron-up' : 'list-outline'} size={12} color={colors.textSec} />
                      <Text style={{ fontSize: 10, color: colors.textSec, fontWeight: '800' }}>
                        {expanded ? tx('travelVisa.countryTrack.hideLessons', 'Hide Lessons') : tx('travelVisa.countryTrack.viewLessons', 'View Lessons')}
                      </Text>
                    </TouchableOpacity>
                  )}
                  {expanded && !track.locked && (
                    <View data-testid={`tv-v2-track-lessons-${track.category_id}`} style={{ marginTop: 9, gap: 6 }}>
                      {(track.lessons || []).map((lesson: any) => (
                        <View key={lesson.lesson_id} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 8 }}>
                          <Ionicons name={lesson.user_completed ? 'checkmark-circle' : 'book-outline'} size={14} color={lesson.user_completed ? colors.success : colors.textMuted} />
                          <View style={{ flex: 1 }}>
                            <Text style={{ fontSize: 11, color: colors.text, fontWeight: '700' }} numberOfLines={1}>{toText(lesson.title)}</Text>
                            <Text style={{ fontSize: 9, color: colors.textMuted, marginTop: 2 }}>{`${toText(lesson.type) || 'reading'} • ${lesson.duration_min || 0} min • ${toText(lesson.difficulty) || 'medium'} • ${lesson.xp || 0} XP`}</Text>
                          </View>
                        </View>
                      ))}
                    </View>
                  )}
                </View>
              );
            })}
          </View>
        )}
      </View>

      <View data-testid="tv-v2-country-checklist" style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }}>
        <Text style={{ fontSize: 13, color: colors.text, fontWeight: '700' }}>{tx('travelVisa.countryTrack.checklistTitle', 'AI Document Checklist')}</Text>
        <Text style={{ fontSize: 10, color: colors.textMuted, marginTop: 4, marginBottom: 8 }}>{tx('travelVisa.countryTrack.checklistHint', 'Pick a visa type to generate a tailored document checklist for this country.')}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
          {visaTypes.map((vt) => {
            const active = selectedVisaType === vt;
            return (
              <TouchableOpacity
                key={vt}
                data-testid={`tv-v2-checklist-type-${vt.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
                onPress={() => setSelectedVisaType(vt)}
                style={{ borderRadius: 999, borderWidth: 1, borderColor: active ? colors.primary : colors.border, backgroundColor: active ? colors.primarySoft : colors.surfaceHover, paddingHorizontal: 10, paddingVertical: 6, ...WEB_TRANSITION }}
              >
                <Text style={{ fontSize: 10, color: active ? colors.primary : colors.textSec, fontWeight: '700' }}>{vt}</Text>
              </TouchableOpacity>
            );
          })}
        </View>
        <TouchableOpacity
          data-testid="tv-v2-checklist-generate"
          testID="tv-v2-checklist-generate"
          disabled={!selectedVisaType || checklistLoading}
          onPress={() => void generateChecklist()}
          style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, marginTop: 10, borderRadius: 9, backgroundColor: colors.primary, paddingVertical: 9, opacity: !selectedVisaType || checklistLoading ? 0.5 : 1, ...WEB_TRANSITION }}
        >
          {checklistLoading ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="sparkles-outline" size={13} color={colors.primaryText} />}
          <Text style={{ fontSize: 11, color: colors.primaryText, fontWeight: '800' }}>
            {checklistLoading ? tx('travelVisa.countryTrack.generating', 'Generating...') : tx('travelVisa.countryTrack.generateChecklist', 'Generate Checklist')}
          </Text>
        </TouchableOpacity>
        {!!checklistError && (
          <Text data-testid="tv-v2-checklist-error" style={{ fontSize: 10, color: colors.errorText, fontWeight: '700', marginTop: 8 }}>{checklistError}</Text>
        )}
        {checklist.length > 0 && (
          <View data-testid="tv-v2-checklist-results" style={{ marginTop: 10, gap: 6 }}>
            {checklist.map((item: any, idx: number) => (
              <View key={`chk-${idx}`} style={{ flexDirection: 'row', gap: 8, borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, padding: 9 }}>
                <Ionicons name={item.required ? 'alert-circle-outline' : 'ellipse-outline'} size={13} color={item.required ? colors.warning : colors.textMuted} style={{ marginTop: 1 }} />
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 11, color: colors.text, fontWeight: '700' }}>{toText(item.item)}</Text>
                  {!!item.description && <Text style={{ fontSize: 10, color: colors.textSec, marginTop: 2 }}>{toText(item.description)}</Text>}
                  {!!item.tips && <Text style={{ fontSize: 9, color: colors.textMuted, marginTop: 2, fontStyle: 'italic' }}>{toText(item.tips)}</Text>}
                </View>
              </View>
            ))}
          </View>
        )}
      </View>
    </View>
  );
}
