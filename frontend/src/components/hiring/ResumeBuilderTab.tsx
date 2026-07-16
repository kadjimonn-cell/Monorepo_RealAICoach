import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity } from 'react-native';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { HColors, Badge, ScoreBar, scoreColor } from './shared';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

interface Props { C: HColors; }

export function ResumeBuilderTab({ C }: Props) {
  const [resumeTarget, setResumeTarget] = useState({ job_title: '', industry: '' });
  const [resumeScore, setResumeScore] = useState<any>(null);
  const [generatingResume, setGeneratingResume] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);

  const { data: resumeData, refetch: refetchResume } = useLiveQuery('/career-tools/resume/latest', { entity: 'resume', pollInterval: 60000 });
  const generatedResume = resumeData?.resume || null;

  const handleGenerateResume = async () => {
    setGeneratingResume(true);
    try {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const _res = await api.post('/career-tools/resume/generate', {
        target_job_title: resumeTarget.job_title || undefined,
        target_industry: resumeTarget.industry || undefined,
      });
      await refetchResume();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/hiring/ResumeBuilderTab.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setGeneratingResume(false);
  };

  const handleScoreResume = async () => {
    setAiLoading(true);
    try { const res = await api.post('/career-tools/resume/score', {}); setResumeScore(res.data?.analysis || null); } catch (error) { handleAppRecoverableError({ scope: 'src/components/hiring/ResumeBuilderTab.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setAiLoading(false);
  };

  return (
    <View data-testid="resume-builder-tab" testID="resume-builder-tab">
      <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
        <Text style={{ color: C.text, fontSize: 16, fontWeight: '700', marginBottom: 12 }}>AI Resume Generator</Text>
        <TextInput data-testid="resume-target-job" testID="resume-target-job" placeholder="Target job title (e.g., Product Manager)" placeholderTextColor={C.muted}
          value={resumeTarget.job_title} onChangeText={v => setResumeTarget(p => ({ ...p, job_title: v }))}
          style={{ backgroundColor: C.bgSoft, borderRadius: 8, padding: 12, marginBottom: 8, color: C.text, borderWidth: 1, borderColor: C.border }} />
        <TextInput data-testid="resume-target-industry" testID="resume-target-industry" placeholder="Target industry (optional)" placeholderTextColor={C.muted}
          value={resumeTarget.industry} onChangeText={v => setResumeTarget(p => ({ ...p, industry: v }))}
          style={{ backgroundColor: C.bgSoft, borderRadius: 8, padding: 12, marginBottom: 12, color: C.text, borderWidth: 1, borderColor: C.border }} />
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TouchableOpacity data-testid="generate-resume-btn" testID="generate-resume-btn" onPress={handleGenerateResume} disabled={generatingResume}
            style={{ flex: 1, padding: 14, borderRadius: 12, backgroundColor: C.accent, alignItems: 'center' }}>
            <Text style={{ color: C.primaryText, fontSize: 14, fontWeight: '600' }}>{generatingResume ? 'Generating...' : 'Generate Resume'}</Text>
          </TouchableOpacity>
          <TouchableOpacity data-testid="score-resume-btn" testID="score-resume-btn" onPress={handleScoreResume} disabled={aiLoading}
            style={{ flex: 1, padding: 14, borderRadius: 12, backgroundColor: C.primary, alignItems: 'center' }}>
            <Text style={{ color: C.primaryText, fontSize: 14, fontWeight: '600' }}>{aiLoading ? 'Scoring...' : 'Score Resume'}</Text>
          </TouchableOpacity>
        </View>
      </View>
      {resumeScore && (
        <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.accent }}>
          <Text style={{ color: C.accent, fontSize: 15, fontWeight: '700', marginBottom: 8 }}>Resume Score: {resumeScore.grade}</Text>
          <ScoreBar C={C} score={resumeScore.overall_score || 0} label="Overall" color={scoreColor(resumeScore.overall_score || 0, C)} />
          <ScoreBar C={C} score={resumeScore.ats_score || 0} label="ATS Score" color={scoreColor(resumeScore.ats_score || 0, C)} />
          <ScoreBar C={C} score={resumeScore.content_score || 0} label="Content" color={scoreColor(resumeScore.content_score || 0, C)} />
          {resumeScore.summary && <Text style={{ color: C.muted, fontSize: 12, marginTop: 8 }}>{resumeScore.summary}</Text>}
        </View>
      )}
      {generatedResume && (
        <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <Text style={{ color: C.text, fontSize: 16, fontWeight: '700' }}>Generated Resume</Text>
            <View style={{ flexDirection: 'row', gap: 6 }}>
              {generatedResume.ats_score && <Badge label={`ATS: ${generatedResume.ats_score}%`} color={C.successText} bg={C.success + '22'} />}
              {generatedResume.resume_score && <Badge label={`Score: ${generatedResume.resume_score}%`} color={C.accent} bg={C.accent + '22'} />}
            </View>
          </View>
          <Text style={{ color: C.accent, fontSize: 18, fontWeight: '700' }}>{generatedResume.full_name}</Text>
          {generatedResume.contact && (
            <Text style={{ color: C.muted, fontSize: 12 }}>{generatedResume.contact.email} {generatedResume.contact.phone ? `| ${generatedResume.contact.phone}` : ''}</Text>
          )}
          <View style={{ height: 1, backgroundColor: C.border, marginVertical: 10 }} />
          {generatedResume.professional_summary && (
            <View style={{ marginBottom: 12 }}>
              <Text style={{ color: C.text, fontSize: 13, fontWeight: '600', marginBottom: 4 }}>Professional Summary</Text>
              <Text style={{ color: C.muted, fontSize: 12, lineHeight: 18 }}>{generatedResume.professional_summary}</Text>
            </View>
          )}
          {generatedResume.skills?.length > 0 && (
            <View style={{ marginBottom: 12 }}>
              <Text style={{ color: C.text, fontSize: 13, fontWeight: '600', marginBottom: 6 }}>Skills</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4 }}>
                {generatedResume.skills.map((s: string) => <Badge key={s} label={s} color={C.primary} bg={C.primary + '22'} />)}
              </View>
            </View>
          )}
          {generatedResume.experience?.map((exp: any, i: number) => (
            <View key={i} style={{ marginBottom: 10, paddingBottom: 10, borderBottomWidth: 1, borderBottomColor: C.border }}>
              <Text style={{ color: C.text, fontSize: 13, fontWeight: '600' }}>{exp.title} @ {exp.company}</Text>
              <Text style={{ color: C.muted, fontSize: 11 }}>{exp.period}</Text>
              {exp.highlights?.map((h: string, j: number) => (
                <Text key={j} style={{ color: C.text, fontSize: 12, marginLeft: 8 }}>- {h}</Text>
              ))}
            </View>
          ))}
          {generatedResume.improvement_tips?.length > 0 && (
            <View style={{ marginTop: 8, padding: 10, backgroundColor: (globalThis as any).__alphaColor(C.warning, '15'), borderRadius: 8 }}>
              <Text style={{ color: C.warningText, fontSize: 12, fontWeight: '600', marginBottom: 4 }}>Improvement Tips</Text>
              {generatedResume.improvement_tips.map((t: string, i: number) => (
                <Text key={i} style={{ color: C.text, fontSize: 12 }}>- {t}</Text>
              ))}
            </View>
          )}
        </View>
      )}
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
