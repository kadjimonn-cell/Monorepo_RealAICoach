/**
 * Feature 7: Health Guide - Enterprise-Grade Health & Wellness Platform
 * Comprehensive health tracking, symptom checker, medication reminders, wearable data integration
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  StyleSheet,
  Alert,
} from 'react-native';
import { useTheme } from '../../src/context/ThemeContext';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';
import api from '../../src/services/api';
import { useTranslation } from '../../src/hooks/useTranslation';

const GUEST_FALLBACK_ID = `user_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`.slice(0, 78);

type Tab = 'profile' | 'symptoms' | 'medications' | 'wearables' | 'insights';

interface BootstrapData {
  tier: string;
  limits: any;
  usage: any;
  profile?: any;
}

interface Medication {
  medication_id: string;
  name: string;
  dosage: string;
  frequency: string;
  start_date: string;
  end_date?: string;
}

interface SymptomLog {
  log_id: string;
  symptoms: string[];
  severity: number;
  date: string;
  notes?: string;
}

export default function HealthGuideScreen() {
  const { colors, isDark } = useTheme();
  const { t } = useTranslation();
  t('i18n.route.features.medimate.probe');
  const [activeTab, setActiveTab] = useState<Tab>('profile');
  const [loading, setLoading] = useState(true);
  const [bootstrapData, setBootstrapData] = useState<BootstrapData | null>(null);
  const [medications, setMedications] = useState<Medication[]>([]);
  const [symptomLogs, setSymptomLogs] = useState<SymptomLog[]>([]);
  const [insights, setInsights] = useState<any>(null);
  
  // Form states
  const [newMedName, setNewMedName] = useState('');
  const [newMedDosage, setNewMedDosage] = useState('');
  const [newMedFrequency, setNewMedFrequency] = useState('daily');
  const [symptomInput, setSymptomInput] = useState('');
  const [severity, setSeverity] = useState(5);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    loadBootstrap();
  }, []);

  const loadBootstrap = async () => {
    try {
      setLoading(true);
      const response = await api.get('/health-guide/bootstrap', {
        params: { fallback_user_id: GUEST_FALLBACK_ID },
      });
      setBootstrapData(response.data);
      await Promise.all([
        loadMedications(),
        loadSymptomLogs(),
        loadInsights(),
      ]);
    } catch (error: any) {
      handleAppRecoverableError({
        scope: 'features/medimate.tsx#loadBootstrap',
        error,
        message: 'Failed to load Health Guide',
        notifyMode: 'silent',
      });
    } finally {
      setLoading(false);
    }
  };

  const loadMedications = async () => {
    try {
      const response = await api.get('/health-guide/medications', {
        params: { fallback_user_id: GUEST_FALLBACK_ID },
      });
      setMedications(response.data.medications || []);
    } catch (error: any) {
      handleAppRecoverableError({
        scope: 'features/medimate.tsx#loadMedications',
        error,
        message: 'Failed to load medications',
        notifyMode: 'silent',
      });
    }
  };

  const loadSymptomLogs = async () => {
    try {
      const response = await api.get('/health-guide/symptom-checks-history', {
        params: { fallback_user_id: GUEST_FALLBACK_ID },
      });
      const mappedLogs = (response.data.symptom_checks_history || []).map((entry: any) => ({
        log_id: entry.check_id,
        symptoms: entry.symptoms || [],
        severity: entry.severity || 'moderate',
        date: entry.created_at,
        notes: entry.duration,
      }));
      setSymptomLogs(mappedLogs);
    } catch (error: any) {
      handleAppRecoverableError({
        scope: 'features/medimate.tsx#loadSymptomLogs',
        error,
        message: 'Failed to load symptom logs',
        notifyMode: 'silent',
      });
    }
  };

  const loadInsights = async () => {
    try {
      const response = await api.get('/health-guide/insights-history', {
        params: { fallback_user_id: GUEST_FALLBACK_ID, limit: 1 },
      });
      const latest = response.data.insights_history?.[0]?.insights || null;
      setInsights(latest);
    } catch (error: any) {
      handleAppRecoverableError({
        scope: 'features/medimate.tsx#loadInsights',
        error,
        message: 'Failed to load insights',
        notifyMode: 'silent',
      });
    }
  };

  const addMedication = async () => {
    if (!newMedName.trim() || !newMedDosage.trim()) {
      Alert.alert('Error', 'Please enter medication name and dosage');
      return;
    }

    try {
      setSubmitting(true);
      await api.post('/health-guide/medications', {
        name: newMedName,
        dosage: newMedDosage,
        frequency: newMedFrequency,
        fallback_user_id: GUEST_FALLBACK_ID,
      });
      
      setNewMedName('');
      setNewMedDosage('');
      setNewMedFrequency('daily');
      await loadMedications();
      Alert.alert('Success', 'Medication added successfully');
    } catch (error: any) {
      handleAppRecoverableError({
        scope: 'features/medimate.tsx#addMedication',
        error,
        message: 'Failed to add medication',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void addMedication(); },
      });
    } finally {
      setSubmitting(false);
    }
  };

  const logSymptom = async () => {
    if (!symptomInput.trim()) {
      Alert.alert('Error', 'Please describe your symptoms');
      return;
    }

    try {
      setSubmitting(true);
      const severityLabel = severity <= 3 ? 'mild' : severity <= 7 ? 'moderate' : 'severe';
      const checkResponse = await api.post('/health-guide/symptom-check', {
        symptoms: symptomInput.split(',').map(s => s.trim()),
        severity: severityLabel,
        duration: 'recent',
        fallback_user_id: GUEST_FALLBACK_ID,
      });
      setInsights(checkResponse.data || null);
      
      setSymptomInput('');
      setSeverity(5);
      await loadSymptomLogs();
      await loadInsights();
      Alert.alert('Success', 'Symptom logged successfully');
    } catch (error: any) {
      handleAppRecoverableError({
        scope: 'features/medimate.tsx#logSymptom',
        error,
        message: 'Failed to log symptom',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void logSymptom(); },
      });
    } finally {
      setSubmitting(false);
    }
  };

  const renderKPIs = () => {
    if (!bootstrapData) return null;

    const { tier, usage } = bootstrapData;

    return (
      <View style={styles.kpiContainer}>
        <View style={[styles.kpiCard, { backgroundColor: colors.surface }]}>
          <Text style={[styles.kpiValue, { color: colors.primary }]}>
            {medications.length}
          </Text>
          <Text style={[styles.kpiLabel, { color: colors.textSecondary }]}>Medications</Text>
        </View>

        <View style={[styles.kpiCard, { backgroundColor: colors.surface }]}>
          <Text style={[styles.kpiValue, { color: colors.accent }]}>
            {symptomLogs.length}
          </Text>
          <Text style={[styles.kpiLabel, { color: colors.textSecondary }]}>Symptom Logs</Text>
        </View>

        <View style={[styles.kpiCard, { backgroundColor: colors.surface }]}>
          <Text style={[styles.kpiValue, { color: colors.text }]}>
            {usage?.symptom_checks_today || 0}
          </Text>
          <Text style={[styles.kpiLabel, { color: colors.textSecondary }]}>Checks Today</Text>
        </View>

        <View style={[styles.kpiCard, { backgroundColor: colors.surface }]}>
          <Text style={[styles.kpiValue, { color: colors.text }]}>{tier.toUpperCase()}</Text>
          <Text style={[styles.kpiLabel, { color: colors.textSecondary }]}>Plan</Text>
        </View>
      </View>
    );
  };

  const renderProfileTab = () => (
    <View style={styles.tabContent}>
      <View style={[styles.section, { backgroundColor: colors.surface }]}>
        <Text style={[styles.sectionTitle, { color: colors.text }]}>Health Profile</Text>
        {bootstrapData?.profile ? (
          <View>
            <Text style={[styles.infoText, { color: colors.text }]}>
              Age: {bootstrapData.profile.age || 'Not set'}
            </Text>
            <Text style={[styles.infoText, { color: colors.text }]}>
              Blood Type: {bootstrapData.profile.blood_type || 'Not set'}
            </Text>
            <Text style={[styles.infoText, { color: colors.text }]}>
              Allergies: {bootstrapData.profile.allergies?.join(', ') || 'None'}
            </Text>
          </View>
        ) : (
          <Text style={[styles.emptyText, { color: colors.textSecondary }]}>
            Profile not yet created. Complete your health profile to get personalized insights!
          </Text>
        )}
      </View>
    </View>
  );

  const renderSymptomsTab = () => (
    <View style={styles.tabContent}>
      <View style={[styles.section, { backgroundColor: colors.surface }]}>
        <Text style={[styles.sectionTitle, { color: colors.text }]}>Log Symptoms</Text>
        
        <TextInput
          style={[styles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
          placeholder="Describe symptoms (comma-separated)"
          placeholderTextColor={colors.textSecondary}
          value={symptomInput}
          onChangeText={setSymptomInput}
          multiline
          data-testid="health-guide-symptom-input"
          testID="health-guide-symptom-input"
        />

        <View style={styles.severityContainer}>
          <Text style={[styles.label, { color: colors.text }]}>Severity: {severity}/10</Text>
          <View style={styles.severityButtons}>
            {[1, 3, 5, 7, 10].map((level) => (
              <TouchableOpacity
                key={level}
                style={[
                  styles.severityButton,
                  {
                    backgroundColor: severity === level ? colors.primary : colors.surface,
                    borderColor: colors.border,
                  },
                ]}
                onPress={() => setSeverity(level)}
                data-testid={`health-guide-severity-button-${level}`}
                testID={`health-guide-severity-button-${level}`}
              >
                <Text
                  style={[
                    styles.severityText,
                    { color: severity === level ? colors.primaryText : colors.text },
                  ]}
                >
                  {level}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        <TouchableOpacity
          style={[styles.button, { backgroundColor: colors.primary }]}
          onPress={logSymptom}
          disabled={submitting}
          data-testid="health-guide-log-symptom-button"
          testID="health-guide-log-symptom-button"
        >
          {submitting ? (
            <ActivityIndicator color={colors.primaryText} />
          ) : (
            <Text style={styles.buttonText}>Log Symptom</Text>
          )}
        </TouchableOpacity>
      </View>

      <View style={[styles.section, { backgroundColor: colors.surface }]}>
        <Text style={[styles.sectionTitle, { color: colors.text }]}>Recent Logs</Text>
        
        {symptomLogs.length === 0 ? (
          <Text style={[styles.emptyText, { color: colors.textSecondary }]}>
            No symptom logs yet. Start tracking your health above!
          </Text>
        ) : (
          symptomLogs.slice(0, 5).map((log) => (
            <View
              key={log.log_id}
              style={[styles.card, { backgroundColor: colors.background, borderColor: colors.border }]}
            >
              <Text style={[styles.cardTitle, { color: colors.text }]}>
                {log.symptoms.join(', ')}
              </Text>
              <Text style={[styles.cardSubtitle, { color: colors.textSecondary }]}>
                Severity: {log.severity}/10 · {new Date(log.date).toLocaleDateString()}
              </Text>
              {log.notes && (
                <Text style={[styles.cardNotes, { color: colors.textSecondary }]}>
                  {log.notes}
                </Text>
              )}
            </View>
          ))
        )}
      </View>
    </View>
  );

  const renderMedicationsTab = () => (
    <View style={styles.tabContent}>
      <View style={[styles.section, { backgroundColor: colors.surface }]}>
        <Text style={[styles.sectionTitle, { color: colors.text }]}>Add Medication</Text>
        
        <TextInput
          style={[styles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
          placeholder="Medication Name"
          placeholderTextColor={colors.textSecondary}
          value={newMedName}
          onChangeText={setNewMedName}
          data-testid="health-guide-medication-name-input"
          testID="health-guide-medication-name-input"
        />

        <TextInput
          style={[styles.input, { backgroundColor: colors.background, color: colors.text, borderColor: colors.border }]}
          placeholder="Dosage (e.g., 500mg)"
          placeholderTextColor={colors.textSecondary}
          value={newMedDosage}
          onChangeText={setNewMedDosage}
          data-testid="health-guide-medication-dosage-input"
          testID="health-guide-medication-dosage-input"
        />

        <View style={styles.frequencyContainer}>
          {['daily', 'twice_daily', 'weekly', 'as_needed'].map((freq) => (
            <TouchableOpacity
              key={freq}
              style={[
                styles.frequencyButton,
                {
                  backgroundColor: newMedFrequency === freq ? colors.primary : colors.surface,
                  borderColor: colors.border,
                },
              ]}
              onPress={() => setNewMedFrequency(freq)}
              data-testid={`health-guide-frequency-button-${freq}`}
              testID={`health-guide-frequency-button-${freq}`}
            >
              <Text
                style={[
                  styles.frequencyText,
                  { color: newMedFrequency === freq ? colors.primaryText : colors.text },
                ]}
              >
                {freq.replace('_', ' ')}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <TouchableOpacity
          style={[styles.button, { backgroundColor: colors.primary }]}
          onPress={addMedication}
          disabled={submitting}
          data-testid="health-guide-add-medication-button"
          testID="health-guide-add-medication-button"
        >
          {submitting ? (
            <ActivityIndicator color={colors.primaryText} />
          ) : (
            <Text style={styles.buttonText}>Add Medication</Text>
          )}
        </TouchableOpacity>
      </View>

      <View style={[styles.section, { backgroundColor: colors.surface }]}>
        <Text style={[styles.sectionTitle, { color: colors.text }]}>My Medications</Text>
        
        {medications.length === 0 ? (
          <Text style={[styles.emptyText, { color: colors.textSecondary }]}>
            No medications tracked yet. Add your first one above!
          </Text>
        ) : (
          medications.map((med) => (
            <View
              key={med.medication_id}
              style={[styles.card, { backgroundColor: colors.background, borderColor: colors.border }]}
            >
              <Text style={[styles.cardTitle, { color: colors.text }]}>{med.name}</Text>
              <Text style={[styles.cardSubtitle, { color: colors.textSecondary }]}>
                {med.dosage} · {med.frequency.replace('_', ' ')}
              </Text>
            </View>
          ))
        )}
      </View>
    </View>
  );

  const renderWearablesTab = () => (
    <View style={styles.tabContent}>
      <View style={[styles.section, { backgroundColor: colors.surface }]}>
        <Text style={[styles.sectionTitle, { color: colors.text }]}>Wearable Data</Text>
        <Text style={[styles.infoText, { color: colors.textSecondary }]}>
          Connect your fitness tracker or smartwatch to sync health data automatically.
        </Text>
        <Text style={[styles.emptyText, { color: colors.textSecondary }]}>
          Wearable integration coming soon!
        </Text>
      </View>
    </View>
  );

  const renderInsightsTab = () => (
    <View style={styles.tabContent}>
      <View style={[styles.section, { backgroundColor: colors.surface }]}>
        <Text style={[styles.sectionTitle, { color: colors.text }]}>Health Insights</Text>
        
        {insights ? (
          <View>
            <Text style={[styles.insightText, { color: colors.text }]}>
              {insights.summary || 'No insights available yet. Keep logging your health data!'}
            </Text>
          </View>
        ) : (
          <Text style={[styles.emptyText, { color: colors.textSecondary }]}>
            Log symptoms and medications to generate personalized health insights.
          </Text>
        )}
      </View>
    </View>
  );

  if (loading) {
    return (
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  return (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      <ScrollView>
        <Text style={[styles.title, { color: colors.text }]}>Health Guide</Text>
        
        {renderKPIs()}

        <View style={styles.tabs}>
          {(['profile', 'symptoms', 'medications', 'wearables', 'insights'] as Tab[]).map((tab) => (
            <TouchableOpacity
              key={tab}
              style={[
                styles.tab,
                {
                  borderBottomColor: activeTab === tab ? colors.primary : 'transparent',
                  borderBottomWidth: activeTab === tab ? 2 : 0,
                },
              ]}
              onPress={() => setActiveTab(tab)}
              data-testid={`health-guide-tab-${tab}`}
              testID={`health-guide-tab-${tab}`}
            >
              <Text
                style={[
                  styles.tabText,
                  {
                    color: activeTab === tab ? colors.primary : colors.textSecondary,
                    fontWeight: activeTab === tab ? '600' : '400',
                  },
                ]}
              >
                {tab.charAt(0).toUpperCase() + tab.slice(1)}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {activeTab === 'profile' && renderProfileTab()}
        {activeTab === 'symptoms' && renderSymptomsTab()}
        {activeTab === 'medications' && renderMedicationsTab()}
        {activeTab === 'wearables' && renderWearablesTab()}
        {activeTab === 'insights' && renderInsightsTab()}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 16,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    marginBottom: 16,
  },
  kpiContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginBottom: 16,
  },
  kpiCard: {
    width: '48%',
    padding: 16,
    borderRadius: 8,
    marginBottom: 8,
    marginRight: '2%',
  },
  kpiValue: {
    fontSize: 24,
    fontWeight: 'bold',
  },
  kpiLabel: {
    fontSize: 12,
    marginTop: 4,
  },
  tabs: {
    flexDirection: 'row',
    marginBottom: 16,
    flexWrap: 'wrap',
  },
  tab: {
    paddingVertical: 12,
    paddingHorizontal: 8,
    alignItems: 'center',
  },
  tabText: {
    fontSize: 13,
  },
  tabContent: {
    marginBottom: 16,
  },
  section: {
    padding: 16,
    borderRadius: 8,
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    marginBottom: 12,
  },
  input: {
    borderWidth: 1,
    borderRadius: 8,
    padding: 12,
    marginBottom: 12,
    fontSize: 14,
  },
  label: {
    fontSize: 14,
    fontWeight: '500',
    marginBottom: 8,
  },
  severityContainer: {
    marginBottom: 16,
  },
  severityButtons: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  severityButton: {
    padding: 10,
    borderRadius: 6,
    borderWidth: 1,
    minWidth: 45,
    alignItems: 'center',
  },
  severityText: {
    fontSize: 14,
    fontWeight: '500',
  },
  frequencyContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginBottom: 12,
  },
  frequencyButton: {
    padding: 10,
    borderRadius: 6,
    borderWidth: 1,
    marginRight: 8,
    marginBottom: 8,
  },
  frequencyText: {
    fontSize: 12,
    fontWeight: '500',
  },
  button: {
    padding: 14,
    borderRadius: 8,
    alignItems: 'center',
  },
  buttonText: {
    color: 'var(--app-primary-text)',
    fontSize: 16,
    fontWeight: '600',
  },
  emptyText: {
    fontSize: 14,
    textAlign: 'center',
    marginVertical: 20,
  },
  card: {
    padding: 12,
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 12,
  },
  cardTitle: {
    fontSize: 16,
    fontWeight: '600',
  },
  cardSubtitle: {
    fontSize: 12,
    marginTop: 4,
  },
  cardNotes: {
    fontSize: 12,
    marginTop: 8,
    fontStyle: 'italic',
  },
  infoText: {
    fontSize: 14,
    marginBottom: 8,
  },
  insightText: {
    fontSize: 14,
    lineHeight: 22,
  },
});
