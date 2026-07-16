import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, TextInput, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';

type Props = { C: any; isCompact: boolean };

const SYNC_TONE: Record<string, string> = { synced: 'success', pending: 'warning', error: 'error' };

export const AgentKnowledgeTab: React.FC<Props> = ({ C, isCompact }) => {
  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState<any>(null);
  const [collections, setCollections] = useState<any[]>([]);
  const [sources, setSources] = useState<any[]>([]);
  const [selectedCollection, setSelectedCollection] = useState<string | null>(null);
  const [newColName, setNewColName] = useState('');
  const [newSourceName, setNewSourceName] = useState('');
  const [newSourceContent, setNewSourceContent] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any>(null);
  const [searchBusy, setSearchBusy] = useState(false);

  const flash = (m: string) => { setMsg(m); setTimeout(() => setMsg(null), 4000); };

  const load = useCallback(async () => {
    try {
      const [ov, cols, srcs] = await Promise.all([
        api.get('/agent-framework/knowledge/overview'),
        api.get('/agent-framework/knowledge/collections'),
        api.get('/agent-framework/knowledge/sources'),
      ]);
      setOverview(ov.data);
      setCollections(cols.data?.collections || []);
      setSources(srcs.data?.sources || []);
    } catch (err: any) {
      flash(err?.response?.data?.detail || err?.message || 'Failed to load knowledge');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const createCollection = async () => {
    const name = newColName.trim();
    if (!name) return;
    setBusy(true);
    try {
      const key = name.toLowerCase().replace(/[^a-z0-9]+/g, '_').slice(0, 60);
      await api.post('/agent-framework/knowledge/collections', { collection_key: key, name });
      setNewColName('');
      flash('Collection created');
      await load();
    } catch (err: any) {
      flash('Create failed: ' + (err?.response?.data?.detail || err?.message));
    } finally {
      setBusy(false);
    }
  };

  const addSource = async () => {
    if (!selectedCollection || !newSourceName.trim() || !newSourceContent.trim()) return;
    setBusy(true);
    try {
      await api.post('/agent-framework/knowledge/sources', {
        collection_key: selectedCollection, name: newSourceName.trim(),
        source_type: 'manual', content: newSourceContent,
      });
      setNewSourceName(''); setNewSourceContent('');
      flash('Source added and indexed');
      await load();
    } catch (err: any) {
      flash('Add failed: ' + (err?.response?.data?.detail || err?.message));
    } finally {
      setBusy(false);
    }
  };

  const syncSource = async (sourceId: string) => {
    setBusy(true);
    try {
      await api.post(`/agent-framework/knowledge/sources/${sourceId}/sync`);
      flash('Source re-synced');
      await load();
    } catch (err: any) {
      flash('Sync failed: ' + (err?.response?.data?.detail || err?.message));
    } finally {
      setBusy(false);
    }
  };

  const runSearch = async () => {
    if (!query.trim()) return;
    setSearchBusy(true); setSearchResults(null);
    try {
      const r = await api.post('/agent-framework/knowledge/search', {
        query, collection_key: selectedCollection || '',
      });
      setSearchResults(r.data);
      const ov = await api.get('/agent-framework/knowledge/overview');
      setOverview(ov.data);
    } catch (err: any) {
      flash('Search failed: ' + (err?.response?.data?.detail || err?.message));
    } finally {
      setSearchBusy(false);
    }
  };

  const s = makeStyles(C, isCompact);

  if (loading) {
    return <View style={s.center} testID="knowledge-loading"><ActivityIndicator size="large" color={C.primary} /></View>;
  }

  const rq = overview?.retrieval_quality || {};
  const visibleSources = selectedCollection ? sources.filter((x) => x.collection_key === selectedCollection) : sources;

  return (
    <View testID="agent-knowledge-tab">
      {msg ? <View style={s.toast}><Text style={s.toastText} testID="knowledge-toast">{msg}</Text></View> : null}

      {/* Stats */}
      <View style={s.statsRow} testID="knowledge-stats">
        {[
          { label: 'Collections', value: overview?.collections_total, icon: 'library' },
          { label: 'Sources', value: overview?.sources_total, icon: 'documents' },
          { label: 'Citations', value: overview?.citations_total, icon: 'link' },
          { label: 'Queries', value: overview?.queries_total, icon: 'search' },
          { label: 'Hit Rate', value: `${rq.hit_rate_percent ?? 0}%`, icon: 'checkmark-done' },
        ].map((card) => (
          <View key={card.label} style={s.statCard} testID={`knowledge-stat-${card.label.toLowerCase().replace(/\s+/g, '-')}`}>
            <Ionicons name={card.icon as any} size={16} color={C.primary} />
            <Text style={s.statValue}>{card.value ?? '—'}</Text>
            <Text style={s.statLabel}>{card.label}</Text>
          </View>
        ))}
      </View>

      {/* Collections */}
      <View style={s.panel} testID="knowledge-collections-panel">
        <Text style={s.panelTitle}>Knowledge Collections ({collections.length})</Text>
        <View style={s.inlineRow}>
          <TextInput
            style={[s.smallInput, { flex: 1 }]}
            value={newColName}
            onChangeText={setNewColName}
            placeholder="New collection name…"
            placeholderTextColor={C.textDim}
            testID="knowledge-new-collection-input"
          />
          <TouchableOpacity onPress={createCollection} disabled={busy} style={s.primaryBtn} testID="knowledge-create-collection-button" accessibilityLabel="Create">
            <Text style={s.primaryBtnText}>Create</Text>
          </TouchableOpacity>
        </View>
        <View style={s.chipsWrap}>
          {collections.map((col) => (
            <TouchableOpacity
              key={col.collection_key}
              onPress={() => setSelectedCollection(selectedCollection === col.collection_key ? null : col.collection_key)}
              style={[s.chip, selectedCollection === col.collection_key && s.chipActive]}
              testID={`knowledge-collection-chip-${col.collection_key}`}
            >
              <Text style={[s.chipText, selectedCollection === col.collection_key && s.chipTextActive]}>
                {col.name} ({col.source_count})
              </Text>
            </TouchableOpacity>
          ))}
        </View>
        {collections.length === 0 ? <Text style={s.meta}>No collections yet — create one to start curating knowledge.</Text> : null}
      </View>

      {/* Sources */}
      <View style={s.panel} testID="knowledge-sources-panel">
        <Text style={s.panelTitle}>Sources {selectedCollection ? `in ${selectedCollection}` : `(${sources.length})`}</Text>
        {selectedCollection ? (
          <View style={{ marginBottom: 10, gap: 8 }}>
            <TextInput
              style={s.smallInput}
              value={newSourceName}
              onChangeText={setNewSourceName}
              placeholder="Source name…"
              placeholderTextColor={C.textDim}
              testID="knowledge-new-source-name"
            />
            <TextInput
              style={[s.smallInput, { minHeight: 60, textAlignVertical: 'top' }]}
              value={newSourceContent}
              onChangeText={setNewSourceContent}
              placeholder="Paste knowledge content…"
              placeholderTextColor={C.textDim}
              multiline
              testID="knowledge-new-source-content"
            />
            <TouchableOpacity onPress={addSource} disabled={busy} style={s.primaryBtn} testID="knowledge-add-source-button" accessibilityLabel="Add source">
              <Text style={s.primaryBtnText}>Add source</Text>
            </TouchableOpacity>
          </View>
        ) : null}
        {visibleSources.length === 0 ? <Text style={s.meta}>No sources{selectedCollection ? ' in this collection' : ''} yet.</Text> : visibleSources.map((src) => (
          <View key={src.source_id} style={s.sourceRow} testID={`knowledge-source-${src.source_id}`}>
            <Ionicons name="document-text" size={14} color={C.primary} />
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={s.lineLabel} numberOfLines={1}>{src.name}</Text>
              <Text style={s.meta}>{src.source_type} · v{src.version} · {src.citations || 0} citations · {src.sync_status}</Text>
            </View>
            <TouchableOpacity onPress={() => syncSource(src.source_id)} disabled={busy} style={s.iconBtn} testID={`knowledge-sync-${src.source_id}`} accessibilityLabel="sync button">
              <Ionicons name="sync" size={14} color={C.primary} />
            </TouchableOpacity>
          </View>
        ))}
      </View>

      {/* Retrieval test */}
      <View style={s.panel} testID="knowledge-search-panel">
        <Text style={s.panelTitle}>Retrieval Test (with citations)</Text>
        <View style={s.inlineRow}>
          <TextInput
            style={[s.smallInput, { flex: 1 }]}
            value={query}
            onChangeText={setQuery}
            placeholder={selectedCollection ? `Search ${selectedCollection}…` : 'Search all collections…'}
            placeholderTextColor={C.textDim}
            testID="knowledge-search-input"
          />
          <TouchableOpacity onPress={runSearch} disabled={searchBusy} style={s.primaryBtn} testID="knowledge-search-button" accessibilityLabel="Search">
            {searchBusy ? <ActivityIndicator size="small" color={C.primaryText} /> : <Text style={s.primaryBtnText}>Search</Text>}
          </TouchableOpacity>
        </View>
        {searchResults ? (
          <View style={{ marginTop: 8 }} testID="knowledge-search-results">
            {(searchResults.results || []).length === 0 ? <Text style={s.meta}>No matches found.</Text> : searchResults.results.map((r: any) => (
              <View key={r.source_id} style={s.resultBox}>
                <Text style={s.lineLabel}>{r.citation} <Text style={s.meta}>score {r.score}</Text></Text>
                {r.snippet ? <Text style={s.snippet}>…{r.snippet}…</Text> : null}
              </View>
            ))}
          </View>
        ) : null}
      </View>
    </View>
  );
};

const makeStyles = (C: any, isCompact: boolean) => StyleSheet.create({
  center: { padding: 40, alignItems: 'center' },
  toast: { backgroundColor: C.infoSoft, borderRadius: 10, padding: 10, marginBottom: 12 },
  toastText: { color: C.infoText, fontSize: 12, fontWeight: '600' },
  statsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 14 },
  statCard: {
    flexGrow: 1, minWidth: isCompact ? 100 : 130, backgroundColor: C.card, borderRadius: 12,
    borderWidth: 1, borderColor: C.border, padding: 12, gap: 4,
  },
  statValue: { fontSize: 18, fontWeight: '800', color: C.text },
  statLabel: { fontSize: 11, color: C.textSecondary },
  panel: {
    backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border,
    padding: 16, marginBottom: 12,
  },
  panelTitle: { fontSize: 14, fontWeight: '700', color: C.text, marginBottom: 8 },
  inlineRow: { flexDirection: 'row', gap: 8, alignItems: 'center', marginBottom: 10 },
  smallInput: {
    borderWidth: 1, borderColor: C.border, borderRadius: 10, padding: 8,
    color: C.text, backgroundColor: C.bgSoft, fontSize: 13,
  },
  primaryBtn: {
    backgroundColor: C.primary, paddingVertical: 8, paddingHorizontal: 16,
    borderRadius: 999, alignSelf: 'flex-start',
  },
  primaryBtnText: { color: C.primaryText, fontSize: 12, fontWeight: '700' },
  chipsWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    paddingVertical: 6, paddingHorizontal: 12, borderRadius: 999,
    backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border,
  },
  chipActive: { backgroundColor: C.primarySoft, borderColor: C.primary },
  chipText: { fontSize: 12, fontWeight: '600', color: C.textSecondary },
  chipTextActive: { color: C.accentText },
  sourceRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.border,
  },
  iconBtn: { padding: 6, borderRadius: 999, backgroundColor: C.primarySoft },
  lineLabel: { fontSize: 12, fontWeight: '600', color: C.text },
  meta: { fontSize: 11, color: C.textDim, marginTop: 2 },
  resultBox: { backgroundColor: C.bgSoft, borderRadius: 10, padding: 10, marginBottom: 8, borderWidth: 1, borderColor: C.border },
  snippet: { fontSize: 12, color: C.textSecondary, marginTop: 4, lineHeight: 18, fontStyle: 'italic' },
});

export default AgentKnowledgeTab;
