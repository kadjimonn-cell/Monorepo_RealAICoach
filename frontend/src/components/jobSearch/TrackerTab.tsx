import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { BillingSectionCard } from '../paymentHistory/BillingRoutePrimitives';

type Application = {
  application_id: string;
  job_id: string;
  job_title: string;
  department: string;
  location: string;
  status: string;
  updated_at: string;
};

type Props = {
  colors: any;
  tx: (key: string, fallback: string) => string;
  refreshSignal: number;
  onChanged: () => void;
};

const STATUS_FLOW = ['saved', 'applied', 'interview', 'offer', 'rejected'] as const;

export const TrackerTab = ({ colors, tx, refreshSignal, onChanged }: Props) => {
  const [applications, setApplications] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  const statusLabel = (status: string) => {
    if (status === 'saved') return tx('jobSearch.tracker.status.saved', 'Saved');
    if (status === 'applied') return tx('jobSearch.tracker.status.applied', 'Applied');
    if (status === 'interview') return tx('jobSearch.tracker.status.interview', 'Interview');
    if (status === 'offer') return tx('jobSearch.tracker.status.offer', 'Offer');
    return tx('jobSearch.tracker.status.rejected', 'Rejected');
  };

  const statusColor = (status: string) => {
    if (status === 'offer') return colors.successText;
    if (status === 'interview') return colors.info;
    if (status === 'rejected') return colors.error;
    if (status === 'applied') return colors.primary;
    return colors.textSecondary;
  };

  const load = useCallback(async () => {
    try {
      const resp = await api.get('/job-search/applications', { silentLoading: true });
      setApplications(resp?.data?.applications || []);
    } catch {
      setErrorMsg(tx('jobSearch.tracker.loadFailed', 'Could not load your tracker right now.'));
    } finally {
      setLoading(false);
    }
  }, [tx]);

  useEffect(() => { load(); }, [load, refreshSignal]);

  const setStatus = async (app: Application, status: string) => {
    setBusyId(app.application_id);
    setErrorMsg('');
    try {
      await api.patch(`/job-search/applications/${app.application_id}`, { status });
      setApplications((prev) => prev.map((a) => (a.application_id === app.application_id ? { ...a, status } : a)));
      onChanged();
    } catch {
      setErrorMsg(tx('jobSearch.tracker.updateFailed', 'Could not update the application status.'));
    } finally {
      setBusyId('');
    }
  };

  const removeApp = async (app: Application) => {
    setBusyId(app.application_id);
    setErrorMsg('');
    try {
      await api.delete(`/job-search/applications/${app.application_id}`);
      setApplications((prev) => prev.filter((a) => a.application_id !== app.application_id));
      onChanged();
    } catch {
      setErrorMsg(tx('jobSearch.tracker.removeFailed', 'Could not remove the application.'));
    } finally {
      setBusyId('');
    }
  };

  return (
    <View style={{ gap: 14 }}>
      <BillingSectionCard colors={colors} testId="job-search-tracker-header">
        <Text style={{ color: colors.text, fontSize: 17, fontWeight: '800' }}>{tx('jobSearch.tracker.title', 'Application tracker')}</Text>
        <Text style={{ color: colors.textSecondary, fontSize: 12, lineHeight: 18, marginTop: 4 }}>
          {tx('jobSearch.tracker.subtitle', 'Record what happens to every application — saved, applied, interview, offer, or rejected.')}
        </Text>
        {errorMsg ? <Text style={{ color: colors.error, fontSize: 12, marginTop: 8 }} data-testid="job-search-tracker-error" testID="job-search-tracker-error">{errorMsg}</Text> : null}
      </BillingSectionCard>

      {loading ? (
        <BillingSectionCard colors={colors} testId="job-search-tracker-loading"><ActivityIndicator color={colors.primary} /></BillingSectionCard>
      ) : applications.length === 0 ? (
        <BillingSectionCard colors={colors} testId="job-search-tracker-empty">
          <Text style={{ color: colors.textSecondary, fontSize: 13 }}>{tx('jobSearch.tracker.empty', 'Nothing tracked yet. Add jobs from the Find Jobs tab.')}</Text>
        </BillingSectionCard>
      ) : (
        applications.map((app, idx) => (
          <BillingSectionCard key={app.application_id} colors={colors} testId={`job-search-tracker-row-${idx}`}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
              <View style={{ flex: 1, minWidth: 180 }}>
                <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid={`job-search-tracker-title-${idx}`} testID={`job-search-tracker-title-${idx}`}>{app.job_title}</Text>
                <Text style={{ color: colors.textSecondary, fontSize: 12, marginTop: 2 }}>{app.department} · {app.location}</Text>
              </View>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <View style={{ borderWidth: 1, borderColor: statusColor(app.status), borderRadius: 999, paddingHorizontal: 12, paddingVertical: 5 }}>
                  <Text style={{ color: statusColor(app.status), fontSize: 11, fontWeight: '800', textTransform: 'uppercase' }} data-testid={`job-search-tracker-status-${idx}`} testID={`job-search-tracker-status-${idx}`}>
                    {statusLabel(app.status)}
                  </Text>
                </View>
                <TouchableOpacity onPress={() => removeApp(app)} disabled={busyId === app.application_id} data-testid={`job-search-tracker-remove-${idx}`} testID={`job-search-tracker-remove-${idx}`} accessibilityRole="button" accessibilityLabel={tx('jobSearch.tracker.remove', 'Remove from tracker')}>
                  <Ionicons name="trash-outline" size={17} color={colors.textSecondary} />
                </TouchableOpacity>
              </View>
            </View>
            <View style={{ flexDirection: 'row', gap: 6, marginTop: 12, flexWrap: 'wrap' }}>
              {STATUS_FLOW.filter((s) => s !== app.status).map((status) => (
                <TouchableOpacity
                  key={status}
                  onPress={() => setStatus(app, status)}
                  disabled={busyId === app.application_id}
                  style={{ backgroundColor: colors.background, borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 6 }}
                  data-testid={`job-search-tracker-set-${status}-${idx}`}
                  testID={`job-search-tracker-set-${status}-${idx}`}
                  accessibilityRole="button"
                  accessibilityLabel={statusLabel(status)}
                >
                  <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{statusLabel(status)}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </BillingSectionCard>
        ))
      )}
    </View>
  );
};
