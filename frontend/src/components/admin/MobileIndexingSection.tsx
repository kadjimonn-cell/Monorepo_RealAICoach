import React, { useEffect, useState } from 'react';
import { View, Text, ActivityIndicator, Platform, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

interface MFIData {
  analysis_id: string;
  timestamp: string;
  overall_score: number;
  pages_checked: number;
  pages_with_parity: number;
  total_issues: number;
  issues: { page: string; issue: string }[];
  page_results: {
    path: string;
    label: string;
    score: number;
    parity: boolean;
    issues: string[];
    mobile?: { status: number; load_time: number; size_bytes: number; has_viewport: boolean };
    desktop?: { status: number; load_time: number; size_bytes: number };
    error?: string;
  }[];
  recommendations: { priority: string; category: string; action: string }[];
}

const priorityColors: Record<string, string> = {
  critical: 'var(--app-error)',
  high: 'var(--app-warning)',
  medium: 'var(--app-primary)',
  info: 'var(--app-success)',
};

export default function MobileIndexingSection({ colors: _colors }: { colors: any }) {
  const colors = useAdminTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [data, setData] = useState<MFIData | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [hasReport, setHasReport] = useState(true);

  const fetchLatest = () => {
    api.get('/admin/seo/mobile-indexing/latest')
      .then(r => {
        if (r.data.status === 'no_reports') {
          setHasReport(false);
          setData(null);
        } else {
          setHasReport(true);
          setData(r.data);
        }
      })
      .catch(() => setHasReport(false))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchLatest(); }, []);

  const runAnalysis = async () => {
    setAnalyzing(true);
    try {
      const res = await api.post('/admin/seo/mobile-indexing/analyze');
      setData(res.data);
      setHasReport(true);
    } catch (e) {
      console.error('Mobile indexing analysis failed:', e);
    } finally {
      setAnalyzing(false);
    }
  };

  if (loading) return (
    <View style={{ padding: 40, alignItems: 'center' }}>
      <ActivityIndicator size="large" color={'var(--app-primary)'} />
      <Text style={{ color: colors.textMuted, marginTop: 12, fontSize: 13 }}>{tx('admin.mobileIndexing.loading', 'Loading Mobile Indexing Report...')}</Text>
    </View>
  );

  if (Platform.OS !== 'web') return (
    <View style={{ padding: 20 }}>
      <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700' }}>{tx('admin.mobileIndexing.title', 'Mobile-First Indexing')}</Text>
      <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 4 }}>{tx('admin.mobileIndexing.desktopOnly', 'Available on desktop')}</Text>
    </View>
  );

  if (!hasReport || !data) return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 48, gap: 16 }} data-testid="mfi-no-report">
      <div style={{ width: 64, height: 64, borderRadius: 16, backgroundColor: 'rgba(6,182,212,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Ionicons name="phone-portrait" size={28} color={'var(--app-primary)'} />
      </div>
      <Text style={{ fontSize: 16, fontWeight: '700', color: colors.text }}>{tx('admin.mobileIndexing.empty.title', 'No Mobile Indexing Report')}</Text>
      <Text style={{ fontSize: 12, color: colors.textSec, textAlign: 'center', maxWidth: 400 }}>
        {tx('admin.mobileIndexing.empty.subtitle', "Run your first analysis to see how Google's mobile crawler views your pages vs desktop.")}
      </Text>
      <TouchableOpacity onPress={runAnalysis} disabled={analyzing} data-testid="run-mfi-analysis-btn" testID="run-mfi-analysis-btn"
        style={{ backgroundColor: colors.accent, paddingHorizontal: 24, paddingVertical: 12, borderRadius: 10, marginTop: 8, opacity: analyzing ? 0.6 : 1 }}>
        <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '700' }}>
          {analyzing ? 'Analyzing...' : 'Run Mobile Indexing Analysis'}
        </Text>
      </TouchableOpacity>
    </div>
  );

  const scoreColor = data.overall_score >= 80 ? 'var(--app-success)' : data.overall_score >= 60 ? 'var(--app-warning)' : 'var(--app-error)';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }} data-testid="mfi-section">
      {/* Header with score & run button */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width={90} height={90} viewBox="0 0 90 90" style={{ transform: 'rotate(-90deg)' }}>
              <circle cx={45} cy={45} r={38} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="5" />
              <circle cx={45} cy={45} r={38} fill="none" stroke={scoreColor} strokeWidth="5"
                strokeDasharray={`${2 * Math.PI * 38}`}
                strokeDashoffset={`${2 * Math.PI * 38 - (data.overall_score / 100) * 2 * Math.PI * 38}`}
                strokeLinecap="round" style={{ transition: 'stroke-dashoffset 1s ease' }} />
            </svg>
            <div style={{ position: 'absolute', textAlign: 'center' }}>
              <div style={{ fontSize: 22, fontWeight: '800', color: scoreColor }}>{data.overall_score}</div>
              <div style={{ fontSize: 8, color: colors.textMuted, fontWeight: '600' }}>MFI SCORE</div>
            </div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: colors.textSec }}>{data.pages_with_parity}/{data.pages_checked} pages with full parity</div>
            <div style={{ fontSize: 11, color: colors.textSec }}>{data.total_issues} issue{data.total_issues !== 1 ? 's' : ''} found</div>
            <div style={{ fontSize: 10, color: colors.textSec, marginTop: 4 }}>Last: {new Date(data.timestamp).toLocaleString()}</div>
          </div>
        </div>
        <TouchableOpacity onPress={runAnalysis} disabled={analyzing} data-testid="rerun-mfi-btn" testID="rerun-mfi-btn"
          style={{ backgroundColor: colors.accent, paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8, opacity: analyzing ? 0.6 : 1 }}>
          <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }}>
            {analyzing ? 'Analyzing...' : 'Re-run Analysis'}
          </Text>
        </TouchableOpacity>
      </div>

      {/* Page Results */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }} data-testid="mfi-page-results">
        {data.page_results.map((page, i) => (
          <div key={i} style={{ backgroundColor: colors.surface, borderRadius: 12, padding: 16, border: `1px solid ${page.parity ? 'rgba(34,197,94,0.2)' : 'rgba(245,158,11,0.2)'}` }} data-testid={`mfi-page-${i}`}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <Ionicons name={page.parity ? 'checkmark-circle' : 'warning'} size={14} color={page.parity ? 'var(--app-success)' : 'var(--app-warning)'} />
                <span style={{ fontSize: 13, fontWeight: '700', color: colors.text }}>{page.label}</span>
              </div>
              <span style={{ fontSize: 11, fontWeight: '700', color: page.score >= 80 ? 'var(--app-success)' : page.score >= 60 ? 'var(--app-warning)' : 'var(--app-error)' }}>{page.score}/100</span>
            </div>
            {page.mobile && page.desktop && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 10 }}>
                <div>
                  <div style={{ color: colors.textSec, marginBottom: 2 }}>Mobile</div>
                  <div style={{ color: colors.textMuted }}>{page.mobile.load_time}s / {Math.round(page.mobile.size_bytes / 1024)}KB</div>
                </div>
                <div>
                  <div style={{ color: colors.textSec, marginBottom: 2 }}>Desktop</div>
                  <div style={{ color: colors.textMuted }}>{page.desktop.load_time}s / {Math.round(page.desktop.size_bytes / 1024)}KB</div>
                </div>
              </div>
            )}
            {page.issues.length > 0 && (
              <div style={{ marginTop: 8 }}>
                {page.issues.map((issue, j) => (
                  <div key={j} style={{ display: 'flex', alignItems: 'flex-start', gap: 6, marginTop: 4 }}>
                    <Ionicons name="alert-circle" size={10} color={'var(--app-warning)'} style={{ marginTop: 2 } as any} />
                    <span style={{ fontSize: 10, color: colors.warningText }}>{issue}</span>
                  </div>
                ))}
              </div>
            )}
            {page.parity && page.issues.length === 0 && (
              <div style={{ marginTop: 8, fontSize: 10, color: colors.successText }}>Full mobile-desktop parity</div>
            )}
          </div>
        ))}
      </div>

      {/* Recommendations */}
      {data.recommendations.length > 0 && (
        <div style={{ backgroundColor: colors.surface, borderRadius: 16, padding: 20, border: `1px solid ${colors.border}` }} data-testid="mfi-recommendations">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
            <Ionicons name="bulb" size={16} color={'var(--app-warning)'} />
            <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text }}>{tx('admin.mobileIndexing.recommendations.title', 'Recommendations')}</Text>
          </div>
          {data.recommendations.map((rec, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '8px 0', borderBottom: i < data.recommendations.length - 1 ? '1px solid rgba(255,255,255,0.04)' : 'none' }}>
              <div style={{ backgroundColor: `${priorityColors[rec.priority] || colors.textSec}20`, padding: '2px 8px', borderRadius: 4, flexShrink: 0 }}>
                <span style={{ fontSize: 9, fontWeight: '700', color: priorityColors[rec.priority] || colors.textSec, textTransform: 'uppercase' }}>{rec.priority}</span>
              </div>
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
