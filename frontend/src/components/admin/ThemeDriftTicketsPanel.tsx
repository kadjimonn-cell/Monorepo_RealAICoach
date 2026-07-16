import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { View, Text, TouchableOpacity, TextInput, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';

type Ticket = {
  ticket_id: string;
  ticket_key: string;
  status: string;
  severity: string;
  message: string;
  file: string;
  rule: string;
  line: number;
  sample_lines: number[];
  occurrence_count: number;
  owner?: string;
  sla_deadline?: string;
  sla_breached?: boolean;
  notes?: string;
  created_at: string;
  updated_at: string;
  first_detected_at: string;
  latest_detected_at: string;
  resolved_at?: string;
};

type Summary = {
  all: number;
  open: number;
  in_progress: number;
  resolved: number;
  closed: number;
};

const STATUS_TABS = [
  { key: 'open', label: 'Open' },
  { key: 'in_progress', label: 'In Progress' },
  { key: 'resolved', label: 'Resolved' },
  { key: 'closed', label: 'Closed' },
  { key: '', label: 'All' },
] as const;

const _SEVERITY_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 };

const fmtDate = (v?: string) => {
  if (!v) return '--';
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return '--';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
};

const fmtDateTime = (v?: string) => {
  if (!v) return '--';
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return '--';
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
};

function SeverityBadge({ severity, colors }: { severity: string; colors: any }) {
  const tone = severity === 'high' ? ('var(--app-error)' || 'var(--app-error)') : severity === 'medium' ? ('var(--app-warning)' || 'var(--app-warning)') : ('var(--app-success)' || 'var(--app-success)');
  return (
    <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, backgroundColor: `${tone}16`, borderWidth: 1, borderColor: `${tone}35` }}>
      <Text style={{ color: tone, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{severity}</Text>
    </View>
  );
}

function StatusBadge({ status, colors }: { status: string; colors: any }) {
  const tones: Record<string, string> = {
    open: 'var(--app-error)' || 'var(--app-error)',
    in_progress: 'var(--app-warning)' || 'var(--app-warning)',
    resolved: 'var(--app-success)' || 'var(--app-success)',
    closed: 'var(--app-text-muted)' || 'var(--app-primary)',
  };
  const tone = tones[status] || 'var(--app-text-muted)';
  const label = status === 'in_progress' ? 'In Progress' : status.charAt(0).toUpperCase() + status.slice(1);
  return (
    <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, backgroundColor: `${tone}16`, borderWidth: 1, borderColor: `${tone}35` }}>
      <Text style={{ color: tone, fontSize: 10, fontWeight: '800' }}>{label}</Text>
    </View>
  );
}

function SLAIndicator({ deadline, breached, colors, noSlaLabel, overdueLabel }: { deadline?: string; breached?: boolean; colors: any; noSlaLabel: string; overdueLabel: string }) {
  if (!deadline) return <Text style={{ color: colors.textMuted, fontSize: 10 }}>{noSlaLabel}</Text>;
  const tone = breached ? ('var(--app-error)' || 'var(--app-error)') : ('var(--app-success)' || 'var(--app-success)');
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
      <Ionicons name={breached ? 'alert-circle' : 'time-outline'} size={12} color={tone} />
      <Text style={{ color: tone, fontSize: 10, fontWeight: '700' }}>{fmtDate(deadline)}</Text>
      {breached && <Text style={{ color: tone, fontSize: 9, fontWeight: '800' }}>{overdueLabel}</Text>}
    </View>
  );
}

export function ThemeDriftTicketsPanel() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [summary, setSummary] = useState<Summary>({ all: 0, open: 0, in_progress: 0, resolved: 0, closed: 0 });
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('open');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState('updated_at');
  const [sortDir, setSortDir] = useState<'desc' | 'asc'>('desc');
  const [editingOwner, setEditingOwner] = useState<string | null>(null);
  const [ownerInput, setOwnerInput] = useState('');
  const [editingSLA, setEditingSLA] = useState<string | null>(null);
  const [slaInput, setSlaInput] = useState('');
  const [editingNotes, setEditingNotes] = useState<string | null>(null);
  const [notesInput, setNotesInput] = useState('');
  const [selectedTickets, setSelectedTickets] = useState<Set<string>>(new Set());
  const [actionMessage, setActionMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [expandedTicket, setExpandedTicket] = useState<string | null>(null);

  const loadTickets = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.set('status_filter', statusFilter);
      params.set('sort_by', sortBy);
      params.set('sort_dir', sortDir);
      params.set('limit', '100');
      const res = await api.get(`/admin/autonomous-engine/theme-drift-tickets/list?${params.toString()}`, { silentLoading: true });
      setTickets(res.data?.tickets || []);
      setSummary(res.data?.summary || { all: 0, open: 0, in_progress: 0, resolved: 0, closed: 0 });
    } catch (e: any) {
      setActionMessage({ type: 'error', text: e?.response?.data?.detail || tx('admin.themeDrift.errors.loadFailed', 'Failed to load drift tickets.') });
    } finally {
      setLoading(false);
    }
  }, [statusFilter, sortBy, sortDir, tx]);

  useEffect(() => {
    setLoading(true);
    loadTickets();
  }, [loadTickets]);

  const filteredTickets = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return tickets;
    return tickets.filter(t => {
      const haystack = `${t.ticket_id} ${t.file} ${t.rule} ${t.message} ${t.owner || ''} ${t.severity}`.toLowerCase();
      return haystack.includes(q);
    });
  }, [tickets, searchQuery]);

  const assignOwner = useCallback(async (ticketId: string) => {
    try {
      await api.patch(`/admin/autonomous-engine/theme-drift-tickets/${ticketId}/assign`, { owner: ownerInput.trim() });
      setEditingOwner(null);
      setOwnerInput('');
      setActionMessage({ type: 'success', text: tx('admin.themeDrift.actions.ownerAssignedWithId', 'Owner assigned to {ticketId}').replace('{ticketId}', ticketId) });
      await loadTickets();
    } catch (e: any) {
      setActionMessage({ type: 'error', text: e?.response?.data?.detail || tx('admin.themeDrift.errors.assignOwnerFailed', 'Failed to assign owner.') });
    }
  }, [ownerInput, loadTickets, tx]);

  const updateStatus = useCallback(async (ticketId: string, newStatus: string) => {
    try {
      await api.patch(`/admin/autonomous-engine/theme-drift-tickets/${ticketId}/status`, { status: newStatus });
      setActionMessage({ type: 'success', text: tx('admin.themeDrift.actions.movedToStatusWithValues', '{ticketId} moved to {status}').replace('{ticketId}', ticketId).replace('{status}', newStatus) });
      await loadTickets();
    } catch (e: any) {
      setActionMessage({ type: 'error', text: e?.response?.data?.detail || tx('admin.themeDrift.errors.updateStatusFailed', 'Failed to update status.') });
    }
  }, [loadTickets, tx]);

  const updateSLA = useCallback(async (ticketId: string) => {
    try {
      await api.patch(`/admin/autonomous-engine/theme-drift-tickets/${ticketId}/sla`, { sla_deadline: slaInput.trim() });
      setEditingSLA(null);
      setSlaInput('');
      setActionMessage({ type: 'success', text: tx('admin.themeDrift.actions.slaUpdatedWithId', 'SLA updated for {ticketId}').replace('{ticketId}', ticketId) });
      await loadTickets();
    } catch (e: any) {
      setActionMessage({ type: 'error', text: e?.response?.data?.detail || tx('admin.themeDrift.errors.updateSlaFailed', 'Failed to update SLA.') });
    }
  }, [slaInput, loadTickets, tx]);

  const updateNotes = useCallback(async (ticketId: string) => {
    try {
      await api.patch(`/admin/autonomous-engine/theme-drift-tickets/${ticketId}/notes`, { notes: notesInput.trim() });
      setEditingNotes(null);
      setNotesInput('');
      setActionMessage({ type: 'success', text: tx('admin.themeDrift.actions.notesUpdatedWithId', 'Notes updated for {ticketId}').replace('{ticketId}', ticketId) });
      await loadTickets();
    } catch (e: any) {
      setActionMessage({ type: 'error', text: e?.response?.data?.detail || tx('admin.themeDrift.errors.updateNotesFailed', 'Failed to update notes.') });
    }
  }, [notesInput, loadTickets, tx]);

  const bulkUpdateStatus = useCallback(async (newStatus: string) => {
    if (selectedTickets.size === 0) return;
    try {
      await api.post('/admin/autonomous-engine/theme-drift-tickets/bulk-status', {
        ticket_ids: Array.from(selectedTickets),
        status: newStatus,
      });
      setSelectedTickets(new Set());
      setActionMessage({ type: 'success', text: tx('admin.themeDrift.actions.bulkMovedWithValues', '{count} ticket(s) moved to {status}').replace('{count}', String(selectedTickets.size)).replace('{status}', newStatus) });
      await loadTickets();
    } catch (e: any) {
      setActionMessage({ type: 'error', text: e?.response?.data?.detail || tx('admin.themeDrift.errors.bulkUpdateFailed', 'Bulk update failed.') });
    }
  }, [selectedTickets, loadTickets, tx]);

  const toggleSelect = (id: string) => {
    setSelectedTickets(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedTickets.size === filteredTickets.length) {
      setSelectedTickets(new Set());
    } else {
      setSelectedTickets(new Set(filteredTickets.map(t => t.ticket_id)));
    }
  };

  const nextStatuses = (current: string): string[] => {
    switch (current) {
      case 'open': return ['in_progress', 'resolved', 'closed'];
      case 'in_progress': return ['resolved', 'closed', 'open'];
      case 'resolved': return ['closed', 'open'];
      case 'closed': return ['open'];
      default: return ['open', 'in_progress', 'resolved', 'closed'];
    }
  };

  if (loading) {
    return (
      <View style={{ padding: 40, alignItems: 'center', justifyContent: 'center' }} data-testid="drift-tickets-loading" testID="drift-tickets-loading">
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 10 }}>{tx('admin.themeDrift.states.loading', 'Loading drift tickets...')}</Text>
      </View>
    );
  }

  return (
    <View style={{ gap: 16 }} data-testid="drift-tickets-panel" testID="drift-tickets-panel">
      {/* Header */}
      <View style={{ backgroundColor: colors.card, borderRadius: 18, borderWidth: 1, borderColor: colors.border, padding: 18, gap: 14 }} data-testid="drift-tickets-header" testID="drift-tickets-header">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
          <View style={{ flex: 1, minWidth: 240 }}>
            <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800' }} data-testid="drift-tickets-title" testID="drift-tickets-title">{tx('admin.themeDrift.header.title', 'Theme Drift Tickets')}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 4 }} data-testid="drift-tickets-subtitle" testID="drift-tickets-subtitle">
              {tx('admin.themeDrift.header.subtitle', 'Triage and manage theme drift findings. Assign owners, set SLA deadlines, track resolution status.')}
            </Text>
          </View>
          <TouchableOpacity
            onPress={() => { setLoading(true); loadTickets(); }}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border }}
            data-testid="drift-tickets-refresh-btn" testID="drift-tickets-refresh-btn"
          >
            <Ionicons name="refresh" size={14} color={colors.text} />
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>{tx('admin.themeDrift.actions.refresh', 'Refresh')}</Text>
          </TouchableOpacity>
        </View>

        {/* Summary counters */}
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="drift-tickets-summary" testID="drift-tickets-summary">
          {[
            { key: 'all', label: tx('admin.themeDrift.summary.total', 'Total'), value: summary.all, tone: colors.primary },
            { key: 'open', label: tx('admin.themeDrift.summary.open', 'Open'), value: summary.open, tone: colors.error || colors.error },
            { key: 'in_progress', label: tx('admin.themeDrift.summary.inProgress', 'In Progress'), value: summary.in_progress, tone: colors.warning || colors.warning },
            { key: 'resolved', label: tx('admin.themeDrift.summary.resolved', 'Resolved'), value: summary.resolved, tone: colors.success || colors.success },
            { key: 'closed', label: tx('admin.themeDrift.summary.closed', 'Closed'), value: summary.closed, tone: colors.textMuted || 'var(--app-primary)' },
          ].map(item => (
            <View key={item.key} style={{ flex: 1, minWidth: 100, backgroundColor: colors.bgSoft, borderRadius: 12, padding: 12, borderWidth: 1, borderColor: colors.border }} data-testid={`drift-tickets-count-${item.key}`} testID={`drift-tickets-count-${item.key}`}>
              <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 }}>{item.label}</Text>
              <Text style={{ color: item.tone, fontSize: 20, fontWeight: '900', marginTop: 4 }}>{item.value}</Text>
            </View>
          ))}
        </View>

        {actionMessage && (
          <View
            style={{ flexDirection: 'row', alignItems: 'center', gap: 8, padding: 12, borderRadius: 10, backgroundColor: actionMessage.type === 'success' ? `${colors.success || colors.success}14` : `${colors.error || colors.error}14`, borderWidth: 1, borderColor: actionMessage.type === 'success' ? `${colors.success || colors.success}35` : `${colors.error || colors.error}35` }}
            data-testid="drift-tickets-action-msg" testID="drift-tickets-action-msg"
          >
            <Ionicons name={actionMessage.type === 'success' ? 'checkmark-circle' : 'alert-circle'} size={14} color={actionMessage.type === 'success' ? colors.success : colors.error} />
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '600', flex: 1 }}>{actionMessage.text}</Text>
            <TouchableOpacity onPress={() => setActionMessage(null)} data-testid="drift-tickets-dismiss-msg" testID="drift-tickets-dismiss-msg">
              <Ionicons name="close" size={14} color={colors.textMuted} />
            </TouchableOpacity>
          </View>
        )}
      </View>

      {/* Filters bar */}
      <View style={{ backgroundColor: colors.card, borderRadius: 18, borderWidth: 1, borderColor: colors.border, padding: 14, gap: 12 }} data-testid="drift-tickets-filters" testID="drift-tickets-filters">
        {/* Status tabs */}
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
          {STATUS_TABS.map(tab => {
            const active = statusFilter === tab.key;
            const count = tab.key === '' ? summary.all : (summary as any)[tab.key] ?? 0;
            return (
              <TouchableOpacity
                key={tab.key}
                onPress={() => setStatusFilter(tab.key)}
                style={{ paddingHorizontal: 12, paddingVertical: 7, borderRadius: 10, borderWidth: 1, borderColor: active ? `${colors.primary}55` : colors.border, backgroundColor: active ? `${colors.primary}14` : colors.bgSoft }}
                data-testid={`drift-tickets-tab-${tab.key || 'all'}`} testID={`drift-tickets-tab-${tab.key || 'all'}`}
              >
                <Text style={{ color: active ? colors.primary : colors.textSec, fontSize: 11, fontWeight: '800' }}>
                  {tx(`admin.themeDrift.statusTab.${tab.key || 'all'}`, tab.label)} ({count})
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>

        {/* Search + Sort */}
        <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <View style={{ flex: 1, minWidth: 200 }}>
            <TextInput
              value={searchQuery}
              onChangeText={setSearchQuery}
              placeholder={tx('admin.themeDrift.search.placeholder', 'Search by ID, file, rule, owner...')}
              placeholderTextColor={colors.textMuted}
              style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 9, color: colors.text, backgroundColor: colors.bgSoft, fontSize: 12 }}
              data-testid="drift-tickets-search" testID="drift-tickets-search"
            />
          </View>
          <View style={{ flexDirection: 'row', gap: 6 }}>
            {[
              { key: 'updated_at', label: tx('admin.themeDrift.sort.recent', 'Recent') },
              { key: 'severity', label: tx('admin.themeDrift.sort.severity', 'Severity') },
              { key: 'occurrence_count', label: tx('admin.themeDrift.sort.hits', 'Hits') },
              { key: 'sla_deadline', label: tx('admin.themeDrift.sort.sla', 'SLA') },
            ].map(opt => (
              <TouchableOpacity accessibilityLabel="Sort by in theme drift tickets panel"
                key={opt.key}
                onPress={() => {
                  if (sortBy === opt.key) setSortDir(prev => prev === 'desc' ? 'asc' : 'desc');
                  else { setSortBy(opt.key); setSortDir('desc'); }
                }}
                style={{ paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, backgroundColor: sortBy === opt.key ? `${colors.primary}14` : colors.bgSoft, borderWidth: 1, borderColor: sortBy === opt.key ? `${colors.primary}40` : colors.border }}
                data-testid={`drift-tickets-sort-${opt.key}`} testID={`drift-tickets-sort-${opt.key}`}
              >
                <Text style={{ color: sortBy === opt.key ? colors.primary : colors.textSec, fontSize: 10, fontWeight: '700' }}>
                  {opt.label} {sortBy === opt.key ? (sortDir === 'desc' ? '\u2193' : '\u2191') : ''}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        {/* Bulk actions */}
        {selectedTickets.size > 0 && (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap', paddingTop: 4 }} data-testid="drift-tickets-bulk-bar" testID="drift-tickets-bulk-bar">
            <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800' }}>{tx('admin.themeDrift.bulk.selectedCount', '{count} selected').replace('{count}', String(selectedTickets.size))}</Text>
            <TouchableOpacity onPress={() => bulkUpdateStatus('in_progress')} style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: `${colors.warning || colors.warning}16`, borderWidth: 1, borderColor: `${colors.warning || colors.warning}35` }} data-testid="drift-tickets-bulk-in-progress" testID="drift-tickets-bulk-in-progress">
              <Text style={{ color: colors.warningText || colors.warning, fontSize: 10, fontWeight: '700' }}>{tx('admin.themeDrift.bulk.markInProgress', 'Mark In Progress')}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => bulkUpdateStatus('resolved')} style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: `${colors.success || colors.success}16`, borderWidth: 1, borderColor: `${colors.success || colors.success}35` }} data-testid="drift-tickets-bulk-resolved" testID="drift-tickets-bulk-resolved">
              <Text style={{ color: colors.successText || colors.success, fontSize: 10, fontWeight: '700' }}>{tx('admin.themeDrift.bulk.resolve', 'Resolve')}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => bulkUpdateStatus('closed')} style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: `${colors.textMuted}16`, borderWidth: 1, borderColor: `${colors.textMuted}35` /* @theme-ok deliberate-high-contrast semi-transparent muted pill */ }} data-testid="drift-tickets-bulk-closed" testID="drift-tickets-bulk-closed">
              <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.themeDrift.bulk.close', 'Close')}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => setSelectedTickets(new Set())} data-testid="drift-tickets-bulk-clear" testID="drift-tickets-bulk-clear">
              <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600', textDecorationLine: 'underline' }}>{tx('admin.themeDrift.bulk.clear', 'Clear')}</Text>
            </TouchableOpacity>
          </View>
        )}
      </View>

      {/* Ticket list */}
      <View style={{ backgroundColor: colors.card, borderRadius: 18, borderWidth: 1, borderColor: colors.border, padding: 14, gap: 10 }} data-testid="drift-tickets-list" testID="drift-tickets-list">
        {/* Select all row */}
        {filteredTickets.length > 0 && (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingBottom: 4 }}>
            <TouchableOpacity onPress={toggleSelectAll} style={{ width: 20, height: 20, borderRadius: 4, borderWidth: 1.5, borderColor: selectedTickets.size === filteredTickets.length ? colors.primary : colors.border, backgroundColor: selectedTickets.size === filteredTickets.length ? `${colors.primary}20` : 'transparent', alignItems: 'center', justifyContent: 'center' }} data-testid="drift-tickets-select-all" testID="drift-tickets-select-all">
              {selectedTickets.size === filteredTickets.length && <Ionicons name="checkmark" size={13} color={colors.primary} />}
            </TouchableOpacity>
            <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700' }}>{tx('admin.themeDrift.list.ticketCountWithPlural', '{count} ticket{plural}').replace('{count}', String(filteredTickets.length)).replace('{plural}', filteredTickets.length !== 1 ? 's' : '')}</Text>
          </View>
        )}

        {filteredTickets.length === 0 ? (
          <View style={{ padding: 24, alignItems: 'center' }} data-testid="drift-tickets-empty" testID="drift-tickets-empty">
            <Ionicons name="checkmark-done-circle-outline" size={32} color={colors.success || colors.success} />
            <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 8 }}>{tx('admin.themeDrift.states.noTicketsMatchFilters', 'No tickets match the current filters.')}</Text>
          </View>
        ) : filteredTickets.map((ticket) => {
          const isExpanded = expandedTicket === ticket.ticket_id;
          const isSelected = selectedTickets.has(ticket.ticket_id);
          return (
            <View
              key={ticket.ticket_id}
              style={{ backgroundColor: colors.bgSoft, borderRadius: 14, borderWidth: 1, borderColor: isSelected ? `${colors.primary}50` : colors.border, overflow: 'hidden' }}
              data-testid={`drift-ticket-${ticket.ticket_id}`} testID={`drift-ticket-${ticket.ticket_id}`}
            >
              {/* Ticket row */}
              <View style={{ padding: 14, gap: 8 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                  <TouchableOpacity onPress={() => toggleSelect(ticket.ticket_id)} style={{ width: 20, height: 20, borderRadius: 4, borderWidth: 1.5, borderColor: isSelected ? colors.primary : colors.border, backgroundColor: isSelected ? `${colors.primary}20` : 'transparent', alignItems: 'center', justifyContent: 'center' }} data-testid={`drift-ticket-select-${ticket.ticket_id}`} testID={`drift-ticket-select-${ticket.ticket_id}`}>
                    {isSelected && <Ionicons name="checkmark" size={13} color={colors.primary} />}
                  </TouchableOpacity>

                  <View style={{ flex: 1 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }} data-testid={`drift-ticket-id-${ticket.ticket_id}`} testID={`drift-ticket-id-${ticket.ticket_id}`}>{ticket.ticket_id}</Text>
                      <SeverityBadge severity={ticket.severity} colors={colors} />
                      <StatusBadge status={ticket.status} colors={colors} />
                      {ticket.sla_breached && (
                        <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 999, backgroundColor: `${colors.error || colors.error}20` }}>
                          <Text style={{ color: colors.error || colors.error, fontSize: 9, fontWeight: '800' }}>{tx('admin.themeDrift.badges.slaBreach', 'SLA BREACH')}</Text>
                        </View>
                      )}
                    </View>
                  </View>

                  <TouchableOpacity
                    onPress={() => setExpandedTicket(isExpanded ? null : ticket.ticket_id)}
                    style={{ padding: 6 }}
                    data-testid={`drift-ticket-expand-${ticket.ticket_id}`} testID={`drift-ticket-expand-${ticket.ticket_id}`}
                  >
                    <Ionicons name={isExpanded ? 'chevron-up' : 'chevron-down'} size={16} color={colors.textMuted} />
                  </TouchableOpacity>
                </View>

                {/* File link + metadata */}
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap', paddingLeft: 30 }}>
                  <Ionicons name="document-text-outline" size={12} color={colors.primary} />
                  <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '600' }} numberOfLines={1} data-testid={`drift-ticket-file-${ticket.ticket_id}`} testID={`drift-ticket-file-${ticket.ticket_id}`}>
                    {ticket.file}
                  </Text>
                  {ticket.line > 0 && <Text style={{ color: colors.textMuted, fontSize: 10 }}>L{ticket.line}</Text>}
                </View>

                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, flexWrap: 'wrap', paddingLeft: 30 }}>
                  <Text style={{ color: colors.textSec, fontSize: 10 }}>{tx('admin.themeDrift.ticket.rule', 'Rule')}: {ticket.rule}</Text>
                  <Text style={{ color: colors.textSec, fontSize: 10 }}>{tx('admin.themeDrift.ticket.hits', 'Hits')}: {ticket.occurrence_count}</Text>
                  <Text style={{ color: colors.textSec, fontSize: 10 }}>{tx('admin.themeDrift.ticket.owner', 'Owner')}: {ticket.owner || tx('admin.themeDrift.ticket.unassigned', 'Unassigned')}</Text>
                  <SLAIndicator
                    deadline={ticket.sla_deadline}
                    breached={ticket.sla_breached}
                    colors={colors}
                    noSlaLabel={tx('admin.themeDrift.labels.noSla', 'No SLA')}
                    overdueLabel={tx('admin.themeDrift.labels.overdue', 'OVERDUE')}
                  />
                </View>
              </View>

              {/* Expanded detail */}
              {isExpanded && (
                <View style={{ borderTopWidth: 1, borderTopColor: colors.border, padding: 14, gap: 12, backgroundColor: `${colors.primary}04` }} data-testid={`drift-ticket-detail-${ticket.ticket_id}`} testID={`drift-ticket-detail-${ticket.ticket_id}`}>
                  <Text style={{ color: colors.textSec, fontSize: 11 }}>{ticket.message}</Text>

                  {ticket.sample_lines?.length > 0 && (
                    <View style={{ flexDirection: 'row', gap: 4, flexWrap: 'wrap', alignItems: 'center' }}>
                      <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.themeDrift.ticket.lines', 'Lines')}:</Text>
                      {ticket.sample_lines.map(l => (
                        <View key={l} style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: `${colors.primary}12` }}>
                          <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '700' }}>L{l}</Text>
                        </View>
                      ))}
                    </View>
                  )}

                  <View style={{ flexDirection: 'row', gap: 16, flexWrap: 'wrap' }}>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>{tx('admin.themeDrift.ticket.created', 'Created')}: {fmtDateTime(ticket.created_at)}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>{tx('admin.themeDrift.ticket.updated', 'Updated')}: {fmtDateTime(ticket.updated_at)}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>{tx('admin.themeDrift.ticket.firstSeen', 'First seen')}: {fmtDateTime(ticket.first_detected_at)}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>{tx('admin.themeDrift.ticket.lastSeen', 'Last seen')}: {fmtDateTime(ticket.latest_detected_at)}</Text>
                    {ticket.resolved_at && <Text style={{ color: colors.successText, fontSize: 10 }}>{tx('admin.themeDrift.ticket.resolved', 'Resolved')}: {fmtDateTime(ticket.resolved_at)}</Text>}
                  </View>

                  {ticket.notes && (
                    <View style={{ backgroundColor: colors.bgSoft, borderRadius: 8, padding: 10, borderWidth: 1, borderColor: colors.border }}>
                      <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', marginBottom: 4 }}>{tx('admin.themeDrift.ticket.notes', 'Notes')}</Text>
                      <Text style={{ color: colors.textSec, fontSize: 11 }}>{ticket.notes}</Text>
                    </View>
                  )}

                  {/* Action buttons */}
                  <View style={{ gap: 10 }}>
                    {/* Status transitions */}
                    <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                      <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.themeDrift.actions.moveTo', 'Move to')}:</Text>
                      {nextStatuses(ticket.status).map(s => (
                        <TouchableOpacity
                          key={s}
                          onPress={() => updateStatus(ticket.ticket_id, s)}
                          style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border }}
                          data-testid={`drift-ticket-move-${ticket.ticket_id}-${s}`} testID={`drift-ticket-move-${ticket.ticket_id}-${s}`}
                        >
                          <Text style={{ color: colors.text, fontSize: 10, fontWeight: '700' }}>{s === 'in_progress' ? tx('admin.themeDrift.summary.inProgress', 'In Progress') : s.charAt(0).toUpperCase() + s.slice(1)}</Text>
                        </TouchableOpacity>
                      ))}
                    </View>

                    {/* Owner assignment */}
                    <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                      <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.themeDrift.ticket.owner', 'Owner')}:</Text>
                      {editingOwner === ticket.ticket_id ? (
                        <>
                          <TextInput
                            value={ownerInput}
                            onChangeText={setOwnerInput}
                            placeholder={tx('admin.themeDrift.placeholders.owner', 'Enter name or email')}
                            placeholderTextColor={colors.textMuted}
                            style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6, color: colors.text, backgroundColor: colors.bgSoft, fontSize: 11, minWidth: 160 }}
                            data-testid={`drift-ticket-owner-input-${ticket.ticket_id}`} testID={`drift-ticket-owner-input-${ticket.ticket_id}`}
                          />
                          <TouchableOpacity onPress={() => assignOwner(ticket.ticket_id)} style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: colors.primary }} data-testid={`drift-ticket-owner-save-${ticket.ticket_id}`} testID={`drift-ticket-owner-save-${ticket.ticket_id}`}>
                            <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '700' }}>{tx('admin.themeDrift.actions.save', 'Save')}</Text>
                          </TouchableOpacity>
                          <TouchableOpacity onPress={() => { setEditingOwner(null); setOwnerInput(''); }} data-testid={`drift-ticket-owner-cancel-${ticket.ticket_id}`} testID={`drift-ticket-owner-cancel-${ticket.ticket_id}`}>
                            <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600' }}>{tx('admin.themeDrift.actions.cancel', 'Cancel')}</Text>
                          </TouchableOpacity>
                        </>
                      ) : (
                        <TouchableOpacity
                          onPress={() => { setEditingOwner(ticket.ticket_id); setOwnerInput(ticket.owner || ''); }}
                          style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border }}
                          data-testid={`drift-ticket-assign-btn-${ticket.ticket_id}`} testID={`drift-ticket-assign-btn-${ticket.ticket_id}`}
                        >
                          <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '700' }}>{ticket.owner || tx('admin.themeDrift.actions.assign', 'Assign')}</Text>
                        </TouchableOpacity>
                      )}
                    </View>

                    {/* SLA deadline */}
                    <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                      <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.themeDrift.ticket.sla', 'SLA')}:</Text>
                      {editingSLA === ticket.ticket_id ? (
                        <>
                          <TextInput
                            value={slaInput}
                            onChangeText={setSlaInput}
                            placeholder={tx('admin.themeDrift.placeholders.slaDate', 'YYYY-MM-DD or ISO date')}
                            placeholderTextColor={colors.textMuted}
                            style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6, color: colors.text, backgroundColor: colors.bgSoft, fontSize: 11, minWidth: 160 }}
                            data-testid={`drift-ticket-sla-input-${ticket.ticket_id}`} testID={`drift-ticket-sla-input-${ticket.ticket_id}`}
                          />
                          <TouchableOpacity onPress={() => updateSLA(ticket.ticket_id)} style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: colors.primary }} data-testid={`drift-ticket-sla-save-${ticket.ticket_id}`} testID={`drift-ticket-sla-save-${ticket.ticket_id}`}>
                            <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '700' }}>{tx('admin.themeDrift.actions.save', 'Save')}</Text>
                          </TouchableOpacity>
                          <TouchableOpacity onPress={() => { setEditingSLA(null); setSlaInput(''); }} data-testid={`drift-ticket-sla-cancel-${ticket.ticket_id}`} testID={`drift-ticket-sla-cancel-${ticket.ticket_id}`}>
                            <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600' }}>{tx('admin.themeDrift.actions.cancel', 'Cancel')}</Text>
                          </TouchableOpacity>
                        </>
                      ) : (
                        <TouchableOpacity
                          onPress={() => { setEditingSLA(ticket.ticket_id); setSlaInput(ticket.sla_deadline || ''); }}
                          style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border }}
                          data-testid={`drift-ticket-sla-btn-${ticket.ticket_id}`} testID={`drift-ticket-sla-btn-${ticket.ticket_id}`}
                        >
                          <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '700' }}>{ticket.sla_deadline ? fmtDate(ticket.sla_deadline) : tx('admin.themeDrift.actions.setSla', 'Set SLA')}</Text>
                        </TouchableOpacity>
                      )}
                    </View>

                    {/* Notes */}
                    <View style={{ gap: 6 }}>
                      <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.themeDrift.ticket.notes', 'Notes')}:</Text>
                      {editingNotes === ticket.ticket_id ? (
                        <View style={{ gap: 6 }}>
                          <TextInput
                            value={notesInput}
                            onChangeText={setNotesInput}
                            placeholder={tx('admin.themeDrift.placeholders.notes', 'Add resolution notes...')}
                            placeholderTextColor={colors.textMuted}
                            multiline
                            numberOfLines={3}
                            style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8, color: colors.text, backgroundColor: colors.bgSoft, fontSize: 11, minHeight: 60 }}
                            data-testid={`drift-ticket-notes-input-${ticket.ticket_id}`} testID={`drift-ticket-notes-input-${ticket.ticket_id}`}
                          />
                          <View style={{ flexDirection: 'row', gap: 6 }}>
                            <TouchableOpacity onPress={() => updateNotes(ticket.ticket_id)} style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: colors.primary }} data-testid={`drift-ticket-notes-save-${ticket.ticket_id}`} testID={`drift-ticket-notes-save-${ticket.ticket_id}`}>
                              <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '700' }}>{tx('admin.themeDrift.actions.save', 'Save')}</Text>
                            </TouchableOpacity>
                            <TouchableOpacity onPress={() => { setEditingNotes(null); setNotesInput(''); }} data-testid={`drift-ticket-notes-cancel-${ticket.ticket_id}`} testID={`drift-ticket-notes-cancel-${ticket.ticket_id}`}>
                              <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600' }}>{tx('admin.themeDrift.actions.cancel', 'Cancel')}</Text>
                            </TouchableOpacity>
                          </View>
                        </View>
                      ) : (
                        <TouchableOpacity
                          onPress={() => { setEditingNotes(ticket.ticket_id); setNotesInput(ticket.notes || ''); }}
                          style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border }}
                          data-testid={`drift-ticket-notes-btn-${ticket.ticket_id}`} testID={`drift-ticket-notes-btn-${ticket.ticket_id}`}
                        >
                          <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '700' }}>{ticket.notes ? tx('admin.themeDrift.actions.editNotes', 'Edit Notes') : tx('admin.themeDrift.actions.addNotes', 'Add Notes')}</Text>
                        </TouchableOpacity>
                      )}
                    </View>
                  </View>
                </View>
              )}
            </View>
          );
        })}
      </View>
    </View>
  );
}
