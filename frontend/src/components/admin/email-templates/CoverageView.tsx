import { useTranslation } from '../../../hooks/useTranslation';
import React, { useState, useEffect } from 'react';
import { View, Text, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../../services/api';
import { C, StatCard } from './shared';

interface EnforcementReport {
  v7_enforcement: {
    status: string;
    guardrails_active: boolean;
    skip_branding_override: boolean;
    subject_category_fallback: boolean;
    missing_template_key_warnings: boolean;
    skip_branding_whitelist: string[];
  };
  template_catalog: { total_templates: number; categories: number };
  coverage: {
    send_catalog_template_calls: number;
    send_email_calls: number;
    total_email_sends: number;
    catalog_coverage_pct: number;
  };
  remaining_send_email_breakdown: {
    with_skip_branding: number;
    with_attachments: number;
    pass_through_wrappers: number;
    other_inline: number;
  };
  enforcement_rules: string[];
}

const tx = (_key: string, fallback: string) => fallback;

function GuardrailBadge({ active, label }: { active: boolean; label: string }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: active ? (globalThis as any).__alphaColor(C.green, '12') : C.red + '12', paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: active ? (globalThis as any).__alphaColor(C.green, '30') : C.red + '30' }}>
      <Ionicons name={active ? 'checkmark-circle' : 'close-circle'} size={14} color={active ? C.green : C.red} />
      <Text style={{ fontSize: 11, fontWeight: '700', color: active ? C.green : C.red }}>{label}</Text>
    </View>
  );
}

function CoverageGauge({ pct, size = 120 }: { pct: number; size?: number }) {
  const color = pct >= 90 ? C.green : pct >= 70 ? C.warning : C.red;
  const radius = (size - 12) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (pct / 100) * circumference;

  return (
    <View style={{ alignItems: 'center', justifyContent: 'center', width: size, height: size }}>
      <svg width={size} height={size} style={{ position: 'absolute' }}>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={C.border} strokeWidth={8} />
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={color} strokeWidth={8} strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={strokeDashoffset} transform={`rotate(-90 ${size / 2} ${size / 2})`} style={{ transition: 'stroke-dashoffset 1s ease' }} />
      </svg>
      <Text style={{ fontSize: 28, fontWeight: '900', color }}>{pct.toFixed(1)}%</Text>
      <Text style={{ fontSize: 9, fontWeight: '700', color: C.muted, marginTop: 2 }}>{tx('admin.coverageView.auto.text.001', 'COVERAGE')}</Text>
    </View>
  );
}

function BreakdownBar({ data }: { data: EnforcementReport['remaining_send_email_breakdown'] }) {
  const total = data.with_skip_branding + data.with_attachments + data.pass_through_wrappers + data.other_inline;
  if (total === 0) return null;

  const segments = [
    { label: 'Skip Branding', count: data.with_skip_branding, color: C.warningText },
    { label: 'Attachments', count: data.with_attachments, color: C.purpleText },
    { label: 'Wrappers', count: data.pass_through_wrappers, color: C.blue },
    { label: 'Other Inline', count: data.other_inline, color: C.muted },
  ].filter(s => s.count > 0);

  return (
    <View data-testid="breakdown-bar">
      <View style={{ flexDirection: 'row', height: 8, borderRadius: 4, overflow: 'hidden', marginBottom: 10 }}>
        {segments.map((s, i) => (
          <View key={i} style={{ flex: s.count, backgroundColor: s.color, marginRight: i < segments.length - 1 ? 1 : 0 }} />
        ))}
      </View>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
        {segments.map((s, i) => (
          <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
            <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: s.color }} />
            <Text style={{ fontSize: 11, color: C.muted }}>{s.label}: <Text style={{ fontWeight: '700', color: C.text }}>{s.count}</Text></Text>
          </View>
        ))}
      </View>
    </View>
  );
}

export default function CoverageView() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const [report, setReport] = useState<EnforcementReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get('/email-notifications/v7-enforcement-report');
        setReport(res.data);
      } catch (e: any) {
        setError(e?.response?.data?.detail || 'Failed to load enforcement report');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return (
      <View style={{ padding: 40, alignItems: 'center' }}>
        <ActivityIndicator size="large" color={C.blue} />
        <Text style={{ color: C.muted, marginTop: 10, fontSize: 12 }}>{tx('admin.coverageView.auto.text.002', 'Loading enforcement report...')}</Text>
      </View>
    );
  }

  if (error || !report) {
    return (
      <View style={{ padding: 20, backgroundColor: (globalThis as any).__alphaColor(C.red, '10'), borderRadius: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.red, '30') }}>
        <Text style={{ color: C.red, fontWeight: '700' }}>{error || 'No data'}</Text>
      </View>
    );
  }

  const { v7_enforcement: enf, template_catalog: cat, coverage: cov, remaining_send_email_breakdown: breakdown, enforcement_rules: rules } = report;
  const statusColor = enf.status === 'ENFORCED' ? C.green : C.warning;

  return (
    <View data-testid="coverage-dashboard" testID="coverage-dashboard">
      {/* Status Banner */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: (globalThis as any).__alphaColor(statusColor, '10'), borderRadius: 12, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(statusColor, '25') }}>
        <Ionicons name={enf.status === 'ENFORCED' ? 'shield-checkmark' : 'warning'} size={24} color={statusColor} />
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 16, fontWeight: '800', color: statusColor }}>v7 Design: {enf.status}</Text>
          <Text style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>{tx('admin.coverageView.auto.text.003', 'All emails are wrapped with the v7 colorful design system')}</Text>
        </View>
      </View>

      {/* KPI Cards */}
      <View style={{ flexDirection: 'row', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <StatCard val={cat.total_templates} label="Templates" color={C.purpleText} />
        <StatCard val={cat.categories} label="Categories" color={C.blue} />
        <StatCard val={cov.send_catalog_template_calls} label="Catalog Calls" color={C.green} />
        <StatCard val={cov.send_email_calls} label="Inline Sends" color={C.warningText} />
      </View>

      {/* Coverage Gauge + Stats */}
      <View style={{ flexDirection: 'row', gap: 16, marginBottom: 16 }}>
        <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 20, alignItems: 'center', borderWidth: 1, borderColor: C.border, flex: 1 }}>
          <CoverageGauge pct={cov.catalog_coverage_pct} />
          <Text style={{ fontSize: 12, color: C.muted, marginTop: 8, textAlign: 'center' }}>
            <Text style={{ fontWeight: '800', color: C.green }}>{cov.send_catalog_template_calls}</Text> catalog / <Text style={{ fontWeight: '800', color: C.text }}>{cov.total_email_sends}</Text> total
          </Text>
        </View>

        <View style={{ flex: 1.5, backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ fontSize: 13, fontWeight: '800', color: C.text, marginBottom: 12 }}>{tx('admin.coverageView.auto.text.004', 'Remaining send_email Breakdown')}</Text>
          <BreakdownBar data={breakdown} />
          <Text style={{ fontSize: 10, color: C.muted, marginTop: 10 }}>
            These {cov.send_email_calls} calls are legitimate — PDF attachments, brand probes, admin previews, pass-through wrappers
          </Text>
        </View>
      </View>

      {/* Guardrails */}
      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border, marginBottom: 16 }}>
        <Text style={{ fontSize: 13, fontWeight: '800', color: C.text, marginBottom: 12 }}>{tx('admin.coverageView.auto.text.005', 'Active Guardrails')}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          <GuardrailBadge active={enf.guardrails_active} label="Guardrails Active" />
          <GuardrailBadge active={enf.skip_branding_override} label="Skip Branding Override" />
          <GuardrailBadge active={enf.subject_category_fallback} label="Subject Category Fallback" />
          <GuardrailBadge active={enf.missing_template_key_warnings} label="Missing Key Warnings" />
        </View>

        {enf.skip_branding_whitelist.length > 0 && (
          <View style={{ marginTop: 12 }}>
            <Text style={{ fontSize: 11, color: C.muted, fontWeight: '600', marginBottom: 6 }}>{tx('admin.coverageView.auto.text.006', 'Skip Branding Whitelist:')}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
              {enf.skip_branding_whitelist.map((w, i) => (
                <View key={i} style={{ backgroundColor: C.border, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 }}>
                  <Text style={{ fontSize: 10, fontWeight: '600', color: C.muted, fontFamily: 'monospace' }}>{w}</Text>
                </View>
              ))}
            </View>
          </View>
        )}
      </View>

      {/* Enforcement Rules */}
      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border }}>
        <Text style={{ fontSize: 13, fontWeight: '800', color: C.text, marginBottom: 10 }}>{tx('admin.coverageView.auto.text.007', 'Enforcement Rules')}</Text>
        {rules.map((rule, i) => (
          <View key={i} style={{ flexDirection: 'row', gap: 8, marginBottom: 8 }}>
            <Ionicons name="checkmark-circle" size={14} color={C.green} style={{ marginTop: 1 }} />
            <Text style={{ fontSize: 12, color: C.muted, flex: 1, lineHeight: 18 }}>{rule}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}
