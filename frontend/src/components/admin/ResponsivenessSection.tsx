import React, { useEffect, useState } from 'react';
import { View, Text, ActivityIndicator, TouchableOpacity, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

const tx = (_key: string, fallback: string) => fallback;

const priorityColors: Record<string, string> = { critical: 'var(--app-error)', high: 'var(--app-warning)', medium: 'var(--app-primary)', low: 'var(--app-text-muted)', info: 'var(--app-success)' };
const categoryColors: Record<string, string> = { mobile: 'var(--app-primary)', tablet: 'var(--app-primary)', desktop: 'var(--app-success)', ultrawide: 'var(--app-warning)' };

export default function ResponsivenessSection({ colors: _colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [auditing, setAuditing] = useState(false);
  const [hasReport, setHasReport] = useState(true);

  const fetchLatest = () => {
    api.get('/admin/seo/responsiveness/latest')
      .then(r => {
        if (r.data.status === 'no_reports') { setHasReport(false); setData(null); }
        else { setHasReport(true); setData(r.data); }
      })
      .catch(() => setHasReport(false))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchLatest(); }, []);

  const runAudit = async () => {
    setAuditing(true);
    try {
      const res = await api.post('/admin/seo/responsiveness/audit');
      setData(res.data); setHasReport(true);
    } catch (e) { console.error('Responsiveness audit failed:', e); }
    finally { setAuditing(false); }
  };

  if (loading) return (
    <View style={{ padding: 40, alignItems: 'center' }}>
      <ActivityIndicator size="large" color={'var(--app-primary)'} />
      <Text style={{ color: colors.textMuted, marginTop: 12, fontSize: 13 }}>{tx('admin.responsivenessSection.auto.text.001', 'Loading Responsiveness Report...')}</Text>
    </View>
  );

  if (Platform.OS !== 'web') return (
    <View style={{ padding: 20 }}>
      <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700' }}>{tx('admin.responsivenessSection.auto.text.002', 'Responsiveness Audit')}</Text>
    </View>
  );

  if (!hasReport || !data) return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 48, gap: 16 }} data-testid="resp-no-report">
      <div style={{ width: 64, height: 64, borderRadius: 16, backgroundColor: 'rgba(139,92,246,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Ionicons name="resize" size={28} color={'var(--app-primary)'} />
      </div>
      <Text style={{ fontSize: 16, fontWeight: '700', color: colors.text }}>{tx('admin.responsivenessSection.auto.text.003', 'No Responsiveness Report')}</Text>
      <Text style={{ fontSize: 12, color: colors.textSec, textAlign: 'center', maxWidth: 400 }}>{tx('admin.responsivenessSection.auto.text.004', 'Run an audit to check CSS/layout responsiveness across 7 viewports (320px to 2560px).')}</Text>
      <TouchableOpacity onPress={runAudit} disabled={auditing} data-testid="run-resp-audit-btn" testID="run-resp-audit-btn"
        style={{ backgroundColor: colors.accent, paddingHorizontal: 24, paddingVertical: 12, borderRadius: 10, marginTop: 8, opacity: auditing ? 0.6 : 1 }}>
        <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '700' }}>{auditing ? 'Auditing...' : 'Run Responsiveness Audit'}</Text>
      </TouchableOpacity>
    </div>
  );

  const scoreColor = data.overall_score >= 80 ? 'var(--app-success)' : data.overall_score >= 60 ? 'var(--app-warning)' : 'var(--app-error)';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }} data-testid="resp-section">
      {/* Header with score */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width={90} height={90} viewBox="0 0 90 90" style={{ transform: 'rotate(-90deg)' }}>
              <circle cx={45} cy={45} r={38} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="5" />
              <circle cx={45} cy={45} r={38} fill="none" stroke={scoreColor} strokeWidth="5"
                strokeDasharray={`${2 * Math.PI * 38}`} strokeDashoffset={`${2 * Math.PI * 38 - (data.overall_score / 100) * 2 * Math.PI * 38}`}
                strokeLinecap="round" style={{ transition: 'stroke-dashoffset 1s ease' }} />
            </svg>
            <div style={{ position: 'absolute', textAlign: 'center' }}>
              <div style={{ fontSize: 22, fontWeight: '800', color: scoreColor }}>{data.overall_score}</div>
              <div style={{ fontSize: 8, color: colors.textMuted, fontWeight: '600' }}>RESP SCORE</div>
            </div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: colors.textSec }}>{data.pages_audited} pages, {data.total_issues} issues</div>
            <div style={{ fontSize: 11, color: colors.textSec }}>{data.viewports_tested?.length || 7} viewports tested</div>
            <div style={{ fontSize: 10, color: colors.textSec, marginTop: 4 }}>Last: {new Date(data.timestamp).toLocaleString()}</div>
          </div>
        </div>
        <TouchableOpacity onPress={runAudit} disabled={auditing} data-testid="rerun-resp-btn" testID="rerun-resp-btn"
          style={{ backgroundColor: colors.accent, paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8, opacity: auditing ? 0.6 : 1 }}>
          <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }}>{auditing ? 'Auditing...' : 'Re-run Audit'}</Text>
        </TouchableOpacity>
      </div>

      {/* Category Scores */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 12 }}>
        {Object.entries(data.category_scores || {}).map(([cat, score]: [string, any]) => (
          <div key={cat} style={{ backgroundColor: colors.surface, borderRadius: 12, padding: 16, border: `1px solid ${colors.border}`, textAlign: 'center' }} data-testid={`resp-cat-${cat}`}>
            <div style={{ fontSize: 22, fontWeight: '800', color: score >= 80 ? 'var(--app-success)' : score >= 60 ? 'var(--app-warning)' : 'var(--app-error)' }}>{score}</div>
            <div style={{ fontSize: 10, color: categoryColors[cat] || colors.textSec, fontWeight: '600', textTransform: 'capitalize', marginTop: 4 }}>{cat}</div>
          </div>
        ))}
      </div>

      {/* Page Results */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }} data-testid="resp-page-results">
        {data.page_results?.map((page: any, i: number) => (
          <div key={i} style={{ backgroundColor: colors.surface, borderRadius: 12, padding: 16, border: `1px solid ${page.score >= 80 ? 'rgba(34,197,94,0.2)' : 'rgba(245,158,11,0.2)'}` }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
              <span style={{ fontSize: 13, fontWeight: '700', color: colors.text }}>{page.label}</span>
              <span style={{ fontSize: 11, fontWeight: '700', color: page.score >= 80 ? 'var(--app-success)' : page.score >= 60 ? 'var(--app-warning)' : 'var(--app-error)' }}>{page.score}/100</span>
            </div>
            <div style={{ fontSize: 10, color: colors.textSec, marginBottom: 6 }}>{page.content_size_kb}KB | {page.issues?.length || 0} issues</div>
            {page.issues?.slice(0, 3).map((issue: any, j: number) => (
              <div key={j} style={{ display: 'flex', alignItems: 'flex-start', gap: 6, marginTop: 4 }}>
                <span style={{ fontSize: 8, fontWeight: '700', color: priorityColors[issue.severity], backgroundColor: `${priorityColors[issue.severity]}18`, padding: '1px 4px', borderRadius: 3, textTransform: 'uppercase', flexShrink: 0 }}>{issue.severity}</span>
                <span style={{ fontSize: 10, color: colors.warningText }}>{issue.description?.substring(0, 80)}</span>
              </div>
            ))}
          </div>
        ))}
      </div>

      {/* Recommendations */}
      {data.recommendations?.length > 0 && (
        <div style={{ backgroundColor: colors.surface, borderRadius: 16, padding: 20, border: `1px solid ${colors.border}` }} data-testid="resp-recs">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
            <Ionicons name="bulb" size={16} color={'var(--app-warning)'} />
            <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text }}>{tx('admin.responsivenessSection.auto.text.005', 'Recommendations')}</Text>
          </div>
          {data.recommendations.map((rec: any, i: number) => (
            <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '8px 0', borderBottom: i < data.recommendations.length - 1 ? '1px solid rgba(255,255,255,0.04)' : 'none' }}>
              <span style={{ fontSize: 9, fontWeight: '700', color: priorityColors[rec.priority], backgroundColor: `${priorityColors[rec.priority]}20`, padding: '2px 8px', borderRadius: 4, textTransform: 'uppercase', flexShrink: 0 }}>{rec.priority}</span>
              <div>
                <div style={{ fontSize: 11, fontWeight: '600', color: colors.textMuted }}>{rec.category}</div>
                <div style={{ fontSize: 10, color: colors.textMuted, marginTop: 2 }}>{rec.action}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
