import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { HColors, Badge, ScoreBar, scoreColor } from './shared';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

interface Props { C: HColors; }

export function CareerCoachTab({ C }: Props) {
  const [resumeImprovements, setResumeImprovements] = useState<any>(null);
  const [aiLoading, setAiLoading] = useState(false);

  const { data: careerAdvice, loading } = useLiveQuery('/aris/career/advice', { entity: 'career_coach', pollInterval: 60000 });

  const loadResumeImprovements = async () => {
    setAiLoading(true);
    try { const res = await api.post('/aris/career/improve-resume', {}); setResumeImprovements(res.data?.improvements || null); } catch (error) { handleAppRecoverableError({ scope: 'src/components/hiring/CareerCoachTab.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setAiLoading(false);
  };

  if (loading) return (
    <View style={{ alignItems: 'center', paddingVertical: 40 }}>
      <ActivityIndicator size="large" color={C.accent} />
      <Text style={{ color: C.muted, marginTop: 12 }}>AI Career Coach is analyzing your profile...</Text>
    </View>
  );

  if (!careerAdvice) return (
    <View style={{ alignItems: 'center', paddingVertical: 32 }}>
      <Text style={{ color: C.muted }}>Career advice unavailable. Update your profile first.</Text>
    </View>
  );

  return (
    <View data-testid="career-coach-tab" testID="career-coach-tab">
      <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border, alignItems: 'center' }}>
        <Text style={{ color: scoreColor(careerAdvice.career_score || 0, C), fontSize: 48, fontWeight: '700' }}>{careerAdvice.career_score}</Text>
        <Text style={{ color: C.muted, fontSize: 14 }}>Career Score</Text>
        <Text style={{ color: C.text, fontSize: 13, textAlign: 'center', marginTop: 8 }}>{careerAdvice.overall_advice}</Text>
      </View>
      <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 10 }}>
          <Ionicons name="document-text-outline" size={18} color={C.accent} />
          <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginLeft: 8 }}>Resume Improvements</Text>
        </View>
        {(careerAdvice.resume_improvements || []).map((tip: string, i: number) => (
          <View key={i} style={{ flexDirection: 'row', marginBottom: 6 }}>
            <Ionicons name="arrow-forward" size={14} color={C.accent} style={{ marginTop: 2, marginRight: 8 }} />
            <Text style={{ color: C.text, fontSize: 13, flex: 1 }}>{tip}</Text>
          </View>
        ))}
        <TouchableOpacity data-testid="get-resume-ai" testID="get-resume-ai" onPress={loadResumeImprovements}
          style={{ marginTop: 10, paddingVertical: 8, borderRadius: 8, backgroundColor: C.accent, alignItems: 'center' }}>
          <Text style={{ color: C.primaryText || C.buttonText || C.text, fontSize: 13, fontWeight: '600' }}>{aiLoading ? 'Analyzing...' : 'Get Detailed AI Resume Review'}</Text>
        </TouchableOpacity>
      </View>
      {resumeImprovements && (
        <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.accent }}>
          <Text style={{ color: C.accent, fontSize: 15, fontWeight: '700', marginBottom: 8 }}>AI Resume Analysis</Text>
          <ScoreBar score={resumeImprovements.score || 0} label="Overall Score" color={scoreColor(resumeImprovements.score || 0, C)} C={C} />
          <ScoreBar score={resumeImprovements.ats_score || 0} label="ATS Score" color={scoreColor(resumeImprovements.ats_score || 0, C)} C={C} />
          {resumeImprovements.improved_summary && (
            <View style={{ marginTop: 8 }}>
              <Text style={{ color: C.text, fontSize: 12, fontWeight: '600' }}>Improved Summary:</Text>
              <Text style={{ color: C.muted, fontSize: 12, marginTop: 4, fontStyle: 'italic' }}>{resumeImprovements.improved_summary}</Text>
            </View>
          )}
        </View>
      )}
      <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 10 }}>
          <Ionicons name="bulb-outline" size={18} color={C.warningText} />
          <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginLeft: 8 }}>Skills to Learn</Text>
        </View>
        {(careerAdvice.skills_to_learn || []).map((s: any, i: number) => (
          <View key={i} style={{ marginBottom: 8, paddingBottom: 8, borderBottomWidth: 1, borderBottomColor: C.border }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <Text style={{ color: C.text, fontSize: 13, fontWeight: '600' }}>{s.skill}</Text>
              <Badge label={s.priority} color={s.priority === 'high' ? C.error : s.priority === 'medium' ? C.warning : C.success}
                bg={(s.priority === 'high' ? C.error : s.priority === 'medium' ? C.warning : C.success) + '22'} />
            </View>
            <Text style={{ color: C.muted, fontSize: 12, marginTop: 2 }}>{s.reason}</Text>
          </View>
        ))}
      </View>
      {(careerAdvice.career_paths || []).length > 0 && (
        <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 10 }}>
            <Ionicons name="trending-up" size={18} color={C.successText} />
            <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginLeft: 8 }}>Career Paths</Text>
          </View>
          {(careerAdvice.career_paths || []).map((path: any, i: number) => (
            <View key={i} style={{ marginBottom: 10, padding: 10, backgroundColor: C.bgSoft, borderRadius: 8 }}>
              <Text style={{ color: C.accent, fontSize: 14, fontWeight: '600' }}>{path.title}</Text>
              <Text style={{ color: C.muted, fontSize: 12 }}>Timeline: {path.timeline} | Salary: {path.salary_range}</Text>
              {(path.steps || []).map((step: string, j: number) => (
                <Text key={j} style={{ color: C.text, fontSize: 12, marginTop: 2 }}>{j + 1}. {step}</Text>
              ))}
            </View>
          ))}
        </View>
      )}
      {(careerAdvice.certifications_recommended || []).length > 0 && (
        <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 10 }}>
            <Ionicons name="ribbon-outline" size={18} color={C.primary} />
            <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginLeft: 8 }}>Certifications</Text>
          </View>
          {(careerAdvice.certifications_recommended || []).map((c: any, i: number) => (
            <View key={i} style={{ marginBottom: 6 }}>
              <Text style={{ color: C.text, fontSize: 13, fontWeight: '600' }}>{c.name}</Text>
              <Text style={{ color: C.muted, fontSize: 12 }}>{c.provider} - {c.relevance}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
