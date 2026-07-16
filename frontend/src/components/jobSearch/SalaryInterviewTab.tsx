import React, { useState } from 'react';
import { View, Text, TextInput } from 'react-native';
import api from '../../services/api';
import { BillingSectionCard, BillingActionButton } from '../paymentHistory/BillingRoutePrimitives';

type Benchmark = {
  currency: string;
  min_salary: number;
  median_salary: number;
  max_salary: number;
  percentile_25: number;
  percentile_75: number;
  market_trend: string;
  insights: string;
  comparable_roles: string[];
};

type Question = { question: string; type: string; difficulty: string; tips: string };

type Props = {
  colors: any;
  tx: (key: string, fallback: string) => string;
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

export const SalaryInterviewTab = ({ colors, tx }: Props) => {
  const [jobTitle, setJobTitle] = useState('');
  const [location, setLocation] = useState('');
  const [years, setYears] = useState('3');
  const [benchmark, setBenchmark] = useState<Benchmark | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [benchBusy, setBenchBusy] = useState(false);
  const [prepBusy, setPrepBusy] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const fmt = (n: number, cur: string) => `${cur} ${Number(n || 0).toLocaleString()}`;

  const runBenchmark = async () => {
    if (!jobTitle.trim() || !location.trim()) {
      setErrorMsg(tx('jobSearch.salary.needInputs', 'Enter a job title and location first.'));
      return;
    }
    setBenchBusy(true);
    setErrorMsg('');
    try {
      const resp = await api.post('/job-search/ai/salary-benchmark', {
        job_title: jobTitle.trim(),
        location: location.trim(),
        experience_years: Number(years.trim()) || 3,
      }, { timeout: 90000 });
      setBenchmark(resp?.data?.benchmark || null);
    } catch {
      setErrorMsg(tx('jobSearch.salary.benchFailed', 'Salary benchmarking is unavailable right now. Please retry.'));
    } finally {
      setBenchBusy(false);
    }
  };

  const runInterviewPrep = async () => {
    if (!jobTitle.trim()) {
      setErrorMsg(tx('jobSearch.salary.needTitle', 'Enter a job title first.'));
      return;
    }
    setPrepBusy(true);
    setErrorMsg('');
    try {
      const resp = await api.post('/job-search/ai/interview-sim', {
        job_title: jobTitle.trim(),
        num_questions: 5,
      }, { timeout: 90000 });
      setQuestions(resp?.data?.questions || []);
    } catch {
      setErrorMsg(tx('jobSearch.salary.prepFailed', 'Interview prep is unavailable right now. Please retry.'));
    } finally {
      setPrepBusy(false);
    }
  };

  return (
    <View style={{ gap: 14 }}>
      <BillingSectionCard colors={colors} testId="job-search-salary-header">
        <Text style={{ color: colors.text, fontSize: 17, fontWeight: '800' }}>{tx('jobSearch.salary.title', 'Salary benchmark & interview prep')}</Text>
        <Text style={{ color: colors.textSecondary, fontSize: 12, lineHeight: 18, marginTop: 4, marginBottom: 12 }}>
          {tx('jobSearch.salary.subtitle', 'Know your market value before you negotiate, and rehearse with realistic AI interview questions.')}
        </Text>
        <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
          <TextInput
            value={jobTitle}
            onChangeText={setJobTitle}
            placeholder={tx('jobSearch.salary.jobTitlePlaceholder', 'Job title, e.g. Senior Backend Engineer')}
            placeholderTextColor={colors.muted}
            style={[inputStyle(colors), { flex: 2, minWidth: 200 }]}
            data-testid="job-search-salary-title-input"
            testID="job-search-salary-title-input"
            accessibilityLabel={tx('jobSearch.salary.jobTitlePlaceholder', 'Job title, e.g. Senior Backend Engineer')}
          />
          <TextInput
            value={location}
            onChangeText={setLocation}
            placeholder={tx('jobSearch.salary.locationPlaceholder', 'Location, e.g. Copenhagen')}
            placeholderTextColor={colors.muted}
            style={[inputStyle(colors), { flex: 1.5, minWidth: 150 }]}
            data-testid="job-search-salary-location-input"
            testID="job-search-salary-location-input"
            accessibilityLabel={tx('jobSearch.salary.locationPlaceholder', 'Location, e.g. Copenhagen')}
          />
          <TextInput
            value={years}
            onChangeText={setYears}
            placeholder={tx('jobSearch.salary.yearsPlaceholder', 'Years')}
            placeholderTextColor={colors.muted}
            keyboardType="numeric"
            style={[inputStyle(colors), { flex: 0.6, minWidth: 70 }]}
            data-testid="job-search-salary-years-input"
            testID="job-search-salary-years-input"
            accessibilityLabel={tx('jobSearch.salary.yearsPlaceholder', 'Years')}
          />
        </View>
        <View style={{ flexDirection: 'row', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
          <BillingActionButton
            label={benchBusy ? tx('jobSearch.salary.benchBusy', 'Benchmarking…') : tx('jobSearch.salary.runBenchmark', 'Benchmark salary')}
            onPress={runBenchmark}
            icon="cash-outline"
            colors={colors}
            testId="job-search-salary-benchmark-btn"
            disabled={benchBusy}
          />
          <BillingActionButton
            label={prepBusy ? tx('jobSearch.salary.prepBusy', 'Preparing…') : tx('jobSearch.salary.runPrep', 'Interview questions')}
            onPress={runInterviewPrep}
            icon="mic-outline"
            colors={colors}
            variant="secondary"
            testId="job-search-interview-prep-btn"
            disabled={prepBusy}
          />
        </View>
        {errorMsg ? <Text style={{ color: colors.error, fontSize: 12, marginTop: 10 }} data-testid="job-search-salary-error" testID="job-search-salary-error">{errorMsg}</Text> : null}
      </BillingSectionCard>

      {benchmark ? (
        <BillingSectionCard colors={colors} testId="job-search-salary-result">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800', marginBottom: 10 }}>{tx('jobSearch.salary.benchmarkResult', 'Market benchmark')}</Text>
          <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
            {[
              { label: tx('jobSearch.salary.min', 'Minimum'), value: benchmark.min_salary },
              { label: tx('jobSearch.salary.p25', '25th percentile'), value: benchmark.percentile_25 },
              { label: tx('jobSearch.salary.median', 'Median'), value: benchmark.median_salary },
              { label: tx('jobSearch.salary.p75', '75th percentile'), value: benchmark.percentile_75 },
              { label: tx('jobSearch.salary.max', 'Maximum'), value: benchmark.max_salary },
            ].map((cell, cIdx) => (
              <View key={cIdx} style={{ flex: 1, minWidth: 120, backgroundColor: colors.background, borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 10 }}>
                <Text style={{ color: colors.textSecondary, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{cell.label}</Text>
                <Text style={{ color: cIdx === 2 ? colors.primary : colors.text, fontSize: 15, fontWeight: '900', marginTop: 4 }}>{fmt(cell.value, benchmark.currency)}</Text>
              </View>
            ))}
          </View>
          <Text style={{ color: colors.textSecondary, fontSize: 12, marginTop: 10 }}>
            {tx('jobSearch.salary.trend', 'Market trend')}: <Text style={{ color: colors.text, fontWeight: '800' }}>{benchmark.market_trend}</Text>
          </Text>
          <Text style={{ color: colors.textSecondary, fontSize: 12, lineHeight: 18, marginTop: 6 }}>{benchmark.insights}</Text>
        </BillingSectionCard>
      ) : null}

      {questions.length > 0 ? (
        <BillingSectionCard colors={colors} testId="job-search-interview-result">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800', marginBottom: 10 }}>{tx('jobSearch.salary.prepResult', 'Interview prep questions')}</Text>
          <View style={{ gap: 10 }}>
            {questions.map((q, qIdx) => (
              <View key={qIdx} style={{ backgroundColor: colors.background, borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 12 }} data-testid={`job-search-interview-q-${qIdx}`} testID={`job-search-interview-q-${qIdx}`}>
                <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700', lineHeight: 19 }}>{qIdx + 1}. {q.question}</Text>
                <Text style={{ color: colors.textSecondary, fontSize: 10.5, fontWeight: '800', textTransform: 'uppercase', marginTop: 6 }}>{q.type} · {q.difficulty}</Text>
                <Text style={{ color: colors.textSecondary, fontSize: 12, lineHeight: 18, marginTop: 4 }}>{q.tips}</Text>
              </View>
            ))}
          </View>
        </BillingSectionCard>
      ) : null}
    </View>
  );
};
