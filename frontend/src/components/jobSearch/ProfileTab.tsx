import React, { useEffect, useState } from 'react';
import { View, Text, TextInput, ActivityIndicator, Switch } from 'react-native';
import api from '../../services/api';
import { BillingSectionCard, BillingActionButton } from '../paymentHistory/BillingRoutePrimitives';

type Props = {
  colors: any;
  tx: (key: string, fallback: string) => string;
  onProfileSaved: () => void;
};

const inputStyle = (colors: any) => ({
  backgroundColor: colors.background,
  borderWidth: 1,
  borderColor: colors.border,
  borderRadius: 12,
  paddingHorizontal: 12,
  paddingVertical: 10,
  color: colors.text,
  fontSize: 13,
});

export const ProfileTab = ({ colors, tx, onProfileSaved }: Props) => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState('');
  const [headline, setHeadline] = useState('');
  const [summary, setSummary] = useState('');
  const [skills, setSkills] = useState('');
  const [experienceYears, setExperienceYears] = useState('');
  const [education, setEducation] = useState('');
  const [targetRoles, setTargetRoles] = useState('');
  const [preferredLocation, setPreferredLocation] = useState('');
  const [remotePreferred, setRemotePreferred] = useState(false);
  const [achievements, setAchievements] = useState('');
  const [digestSubscribed, setDigestSubscribed] = useState(true);
  const [digestBusy, setDigestBusy] = useState(false);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const resp = await api.get('/job-search/profile', { silentLoading: true });
        const p = resp?.data?.profile;
        if (mounted && p) {
          setHeadline(p.headline || '');
          setSummary(p.summary || '');
          setSkills((p.skills || []).join(', '));
          setExperienceYears(p.experience_years == null ? '' : String(p.experience_years));
          setEducation(p.education || '');
          setTargetRoles((p.target_roles || []).join(', '));
          setPreferredLocation(p.preferred_location || '');
          setRemotePreferred(Boolean(p.remote_preferred));
          setAchievements(p.achievements || '');
        }
      } catch {
        // profile may not exist yet — form starts empty
      } finally {
        if (mounted) setLoading(false);
      }
      try {
        const prefResp = await api.get('/job-search/digest/preference', { silentLoading: true });
        if (mounted && prefResp?.data) setDigestSubscribed(Boolean(prefResp.data.subscribed));
      } catch {
        // default stays subscribed
      }
    })();
    return () => { mounted = false; };
  }, []);

  const saveProfile = async () => {
    setSaving(true);
    setStatusMsg('');
    try {
      await api.put('/job-search/profile', {
        headline: headline.trim(),
        summary: summary.trim(),
        skills: skills.split(',').map((s) => s.trim()).filter(Boolean),
        experience_years: experienceYears.trim() ? Number(experienceYears.trim()) : null,
        education: education.trim(),
        target_roles: targetRoles.split(',').map((s) => s.trim()).filter(Boolean),
        preferred_location: preferredLocation.trim(),
        remote_preferred: remotePreferred,
        achievements: achievements.trim(),
      });
      setStatusMsg(tx('jobSearch.profile.saved', 'Profile saved. AI matching will now use your latest details.'));
      onProfileSaved();
    } catch {
      setStatusMsg(tx('jobSearch.profile.saveFailed', 'Could not save your profile right now. Please retry.'));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <BillingSectionCard colors={colors} testId="job-search-profile-loading">
        <ActivityIndicator color={colors.primary} />
      </BillingSectionCard>
    );
  }

  const field = (labelKey: string, labelFallback: string, value: string, setter: (v: string) => void, testId: string, multiline = false, placeholderKey = '', placeholderFallback = '') => (
    <View style={{ gap: 6 }}>
      <Text style={{ color: colors.textSecondary, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.6 }}>{tx(labelKey, labelFallback)}</Text>
      <TextInput accessibilityLabel="Text input"
        value={value}
        onChangeText={setter}
        multiline={multiline}
        numberOfLines={multiline ? 4 : 1}
        placeholder={placeholderKey ? tx(placeholderKey, placeholderFallback) : ''}
        placeholderTextColor={colors.muted}
        style={[inputStyle(colors), multiline ? { minHeight: 90, textAlignVertical: 'top' } : null]}
        data-testid={testId}
        testID={testId}
        accessibilityLabel={tx(labelKey, labelFallback)}
      />
    </View>
  );

  return (
    <BillingSectionCard colors={colors} testId="job-search-profile-card">
      <Text style={{ color: colors.text, fontSize: 17, fontWeight: '800' }}>{tx('jobSearch.profile.title', 'Career profile')}</Text>
      <Text style={{ color: colors.textSecondary, fontSize: 12, lineHeight: 18, marginTop: 4, marginBottom: 14 }}>
        {tx('jobSearch.profile.subtitle', 'The richer your profile, the sharper your AI fit scores, CVs, and cover letters. Only real facts — the AI never invents experience.')}
      </Text>
      <View style={{ gap: 12 }}>
        {field('jobSearch.profile.headline', 'Professional headline', headline, setHeadline, 'job-search-profile-headline', false, 'jobSearch.profile.headlinePlaceholder', 'e.g. Senior Full-Stack Engineer')}
        {field('jobSearch.profile.summary', 'Professional summary', summary, setSummary, 'job-search-profile-summary', true, 'jobSearch.profile.summaryPlaceholder', 'Describe your experience, projects, and measurable achievements')}
        {field('jobSearch.profile.skills', 'Skills (comma separated)', skills, setSkills, 'job-search-profile-skills', false, 'jobSearch.profile.skillsPlaceholder', 'e.g. React, Python, FastAPI, MongoDB')}
        <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap' }}>
          <View style={{ flex: 1, minWidth: 160 }}>
            {field('jobSearch.profile.experienceYears', 'Years of experience', experienceYears, setExperienceYears, 'job-search-profile-experience')}
          </View>
          <View style={{ flex: 1, minWidth: 160 }}>
            {field('jobSearch.profile.education', 'Education', education, setEducation, 'job-search-profile-education')}
          </View>
        </View>
        {field('jobSearch.profile.targetRoles', 'Target roles (comma separated)', targetRoles, setTargetRoles, 'job-search-profile-target-roles')}
        <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <View style={{ flex: 1, minWidth: 180 }}>
            {field('jobSearch.profile.preferredLocation', 'Preferred location', preferredLocation, setPreferredLocation, 'job-search-profile-location')}
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingBottom: 8 }}>
            <Switch value={remotePreferred} onValueChange={setRemotePreferred} data-testid="job-search-profile-remote" testID="job-search-profile-remote" accessibilityState={{ checked: remotePreferred }} accessibilityLabel={tx('jobSearch.profile.remotePreferred', 'Remote preferred')} />
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '600' }}>{tx('jobSearch.profile.remotePreferred', 'Remote preferred')}</Text>
          </View>
        </View>
        {field('jobSearch.profile.achievements', 'Key achievements', achievements, setAchievements, 'job-search-profile-achievements', true, 'jobSearch.profile.achievementsPlaceholder', 'e.g. Cut infra costs 40%, led a team of 6, shipped 3 products')}
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingTop: 4, flexWrap: 'wrap' }}>
          <Switch
            value={digestSubscribed}
            disabled={digestBusy}
            onValueChange={async (next) => {
              setDigestBusy(true);
              setDigestSubscribed(next);
              try {
                await api.post('/job-search/digest/preference', { subscribed: next });
              } catch {
                setDigestSubscribed(!next);
              } finally {
                setDigestBusy(false);
              }
            }}
            data-testid="job-search-digest-toggle"
            testID="job-search-digest-toggle"
            accessibilityState={{ checked: digestSubscribed }}
            accessibilityLabel={tx('jobSearch.profile.weeklyDigest', 'Email me a weekly job digest')}
          />
          <View style={{ flex: 1, minWidth: 200 }}>
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '600' }}>{tx('jobSearch.profile.weeklyDigest', 'Email me a weekly job digest')}</Text>
            <Text style={{ color: colors.textSecondary, fontSize: 11, lineHeight: 16, marginTop: 2 }}>
              {tx('jobSearch.profile.weeklyDigestHint', 'New matching roles plus your best fit score of the week, every Monday.')}
            </Text>
          </View>
        </View>
      </View>
      <View style={{ marginTop: 16, flexDirection: 'row', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <BillingActionButton
          label={saving ? tx('jobSearch.profile.saving', 'Saving…') : tx('jobSearch.profile.save', 'Save profile')}
          onPress={saveProfile}
          icon="save-outline"
          colors={colors}
          testId="job-search-profile-save"
          disabled={saving}
        />
        {statusMsg ? <Text style={{ color: colors.textSecondary, fontSize: 12, flex: 1 }} data-testid="job-search-profile-status" testID="job-search-profile-status">{statusMsg}</Text> : null}
      </View>
    </BillingSectionCard>
  );
};
