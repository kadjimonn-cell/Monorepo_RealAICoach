import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { HColors, Badge } from './shared';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

interface Props { C: HColors; }

export function InterviewPrepTab({ C }: Props) {
  const [prepJobTitle, setPrepJobTitle] = useState('');
  const [prepCompany, setPrepCompany] = useState('');
  const [interviewPrep, setInterviewPrep] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const loadInterviewPrep = async () => {
    if (!prepJobTitle) return;
    setLoading(true);
    try {
      const res = await api.post('/aris/career/interview-prep', { job_title: prepJobTitle, company: prepCompany, industry: 'technology' });
      setInterviewPrep(res.data?.prep || null);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/hiring/InterviewPrepTab.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setLoading(false);
  };

  return (
    <View data-testid="interview-prep-tab" testID="interview-prep-tab">
      <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
        <Text style={{ color: C.text, fontSize: 16, fontWeight: '700', marginBottom: 12 }}>AI Interview Preparation</Text>
        <TextInput data-testid="prep-job-title" testID="prep-job-title" placeholder="Job title (e.g., Software Engineer)" placeholderTextColor={C.muted}
          value={prepJobTitle} onChangeText={setPrepJobTitle}
          style={{ backgroundColor: C.bgSoft, borderRadius: 8, padding: 12, marginBottom: 8, color: C.text, borderWidth: 1, borderColor: C.border }} />
        <TextInput data-testid="prep-company" testID="prep-company" placeholder="Company name (optional)" placeholderTextColor={C.muted}
          value={prepCompany} onChangeText={setPrepCompany}
          style={{ backgroundColor: C.bgSoft, borderRadius: 8, padding: 12, marginBottom: 12, color: C.text, borderWidth: 1, borderColor: C.border }} />
        <TouchableOpacity data-testid="generate-prep-btn" testID="generate-prep-btn" onPress={loadInterviewPrep} disabled={!prepJobTitle || loading}
          style={{ backgroundColor: !prepJobTitle ? C.border : C.accent, padding: 14, borderRadius: 12, alignItems: 'center' }}>
          <Text style={{ color: C.primaryText || C.buttonText || C.text, fontSize: 14, fontWeight: '600' }}>{loading ? 'Generating...' : 'Generate Interview Prep'}</Text>
        </TouchableOpacity>
      </View>
      {interviewPrep && (
        <View>
          <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
            <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 10 }}>Practice Questions</Text>
            {(interviewPrep.common_questions || []).map((q: any, i: number) => (
              <View key={i} data-testid={`prep-question-${i}`} testID={`prep-question-${i}`} style={{ marginBottom: 12, paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: C.border }}>
                <Badge label={q.type || 'general'} color={C.accent} bg={C.accent + '22'} />
                <Text style={{ color: C.text, fontSize: 14, fontWeight: '600', marginTop: 4 }}>{q.question}</Text>
                <Text style={{ color: C.muted, fontSize: 12, marginTop: 4, fontStyle: 'italic' }}>Tip: {q.tips || q.sample_answer}</Text>
              </View>
            ))}
          </View>
          {(interviewPrep.preparation_checklist || []).length > 0 && (
            <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
              <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 10 }}>Preparation Checklist</Text>
              {interviewPrep.preparation_checklist.map((item: string, i: number) => (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 6 }}>
                  <Ionicons name="checkmark-circle-outline" size={16} color={C.successText} />
                  <Text style={{ color: C.text, fontSize: 13, marginLeft: 8 }}>{item}</Text>
                </View>
              ))}
            </View>
          )}
          {(interviewPrep.salary_negotiation_tips || []).length > 0 && (
            <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
              <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 10 }}>Salary Negotiation</Text>
              {interviewPrep.salary_negotiation_tips.map((tip: string, i: number) => (
                <Text key={i} style={{ color: C.text, fontSize: 13, marginBottom: 4 }}>- {tip}</Text>
              ))}
            </View>
          )}
        </View>
      )}
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
