import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { useTranslation } from '../../hooks/useTranslation';

type Props = { colors: any };

type EditorialPost = {
  post_id: string;
  slug: string;
  title: string;
  excerpt?: string;
  category?: string;
  status: string;
  premium_required?: boolean;
  author_name?: string;
  published_at?: string | null;
  scheduled_publish_at?: string | null;
  updated_at?: string;
};

const STATUS_FILTERS = ['all', 'draft', 'in_review', 'scheduled', 'published'];

const statusTone = (colors: any, status: string): string => ({
  draft: colors.textMuted,
  in_review: colors.warningText,
  scheduled: colors.purpleText || colors.purple,
  published: colors.successText,
}[status] || colors.textSec);

const ACTIONS_BY_STATUS: Record<string, { action: string; label: string }[]> = {
  draft: [{ action: 'submit_review', label: 'Submit for review' }],
  in_review: [
    { action: 'approve_publish', label: 'Publish now' },
    { action: 'schedule', label: 'Schedule' },
    { action: 'revert_draft', label: 'Back to draft' },
  ],
  scheduled: [
    { action: 'approve_publish', label: 'Publish now' },
    { action: 'revert_draft', label: 'Back to draft' },
  ],
  published: [{ action: 'unpublish', label: 'Unpublish' }],
};

export const BlogEditorialPanel = ({ colors }: Props) => {
  const { t } = useTranslation();
  t('i18n.route.admin.blog.editorial.probe');
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [posts, setPosts] = useState<EditorialPost[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [statusFilter, setStatusFilter] = useState('all');
  const [showCreate, setShowCreate] = useState(false);
  const [draftTitle, setDraftTitle] = useState('');
  const [draftExcerpt, setDraftExcerpt] = useState('');
  const [draftCategory, setDraftCategory] = useState('General');
  const [draftContent, setDraftContent] = useState('');
  const [scheduleTarget, setScheduleTarget] = useState<string | null>(null);
  const [scheduleAt, setScheduleAt] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async (status: string) => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get(`/admin/blog-editorial/posts?status=${status}`);
      setPosts(Array.isArray(res.data?.posts) ? res.data.posts : []);
      setCounts(res.data?.counts || {});
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load editorial posts.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(statusFilter);
  }, [load, statusFilter]);

  const createDraft = async () => {
    if (draftTitle.trim().length < 3) {
      setError('Title must be at least 3 characters.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await api.post('/admin/blog-editorial/posts', {
        title: draftTitle.trim(),
        excerpt: draftExcerpt.trim(),
        category: draftCategory.trim() || 'General',
        content: draftContent,
      });
      setDraftTitle('');
      setDraftExcerpt('');
      setDraftContent('');
      setShowCreate(false);
      await load(statusFilter);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to create draft.');
    } finally {
      setBusy(false);
    }
  };

  const runTransition = async (postId: string, action: string, publishAt?: string) => {
    setBusy(true);
    setError('');
    try {
      await api.post(`/admin/blog-editorial/posts/${postId}/transition`, {
        action,
        publish_at: publishAt || undefined,
      });
      setScheduleTarget(null);
      setScheduleAt('');
      await load(statusFilter);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Transition failed.');
    } finally {
      setBusy(false);
    }
  };

  if (!user?.is_admin) {
    return (
      <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 14, backgroundColor: colors.card }} data-testid="blog-editorial-access-denied" testID="blog-editorial-access-denied">
        <Text style={{ color: colors.errorText, fontWeight: '700' }}>Admin access required.</Text>
      </View>
    );
  }

  const inputStyle = {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 8,
    color: colors.text,
    backgroundColor: colors.bgSoft,
  } as any;

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ gap: 10, paddingBottom: 24 }} data-testid="blog-editorial-panel" testID="blog-editorial-panel">
      <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 12, backgroundColor: colors.card, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <View style={{ minWidth: 220 }}>
          <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800' }}>Blog Editorial Workflow</Text>
          <Text style={{ color: colors.textSec, marginTop: 4 }}>Draft → Review → Publish → Schedule pipeline for Blog v2.</Text>
        </View>
        <TouchableOpacity
          onPress={() => setShowCreate((v) => !v)}
          data-testid="blog-editorial-new-draft-button"
          testID="blog-editorial-new-draft-button"
          style={{ backgroundColor: colors.primary, borderRadius: 999, paddingHorizontal: 16, paddingVertical: 9 }}
        >
          <Text style={{ color: colors.primaryText, fontWeight: '800' }}>{showCreate ? 'Close editor' : 'New draft'}</Text>
        </TouchableOpacity>
      </View>

      {error ? (
        <View style={{ borderWidth: 1, borderColor: colors.errorText, borderRadius: 10, padding: 10, backgroundColor: colors.card }} data-testid="blog-editorial-error" testID="blog-editorial-error">
          <Text style={{ color: colors.errorText, fontWeight: '700' }}>{error}</Text>
        </View>
      ) : null}

      {showCreate ? (
        <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 12, backgroundColor: colors.card, gap: 8 }} data-testid="blog-editorial-create-form" testID="blog-editorial-create-form">
          <TextInput value={draftTitle} onChangeText={setDraftTitle} placeholder="Post title" placeholderTextColor={colors.textMuted} style={inputStyle} data-testid="blog-editorial-title-input" testID="blog-editorial-title-input" />
          <TextInput value={draftExcerpt} onChangeText={setDraftExcerpt} placeholder="Excerpt (short summary)" placeholderTextColor={colors.textMuted} style={inputStyle} data-testid="blog-editorial-excerpt-input" testID="blog-editorial-excerpt-input" />
          <TextInput value={draftCategory} onChangeText={setDraftCategory} placeholder="Category" placeholderTextColor={colors.textMuted} style={inputStyle} data-testid="blog-editorial-category-input" testID="blog-editorial-category-input" />
          <TextInput value={draftContent} onChangeText={setDraftContent} placeholder="Post content (paragraphs separated by blank lines)" placeholderTextColor={colors.textMuted} multiline numberOfLines={6} style={[inputStyle, { minHeight: 120, textAlignVertical: 'top' }]} data-testid="blog-editorial-content-input" testID="blog-editorial-content-input" />
          <TouchableOpacity onPress={() => void createDraft()} disabled={busy} data-testid="blog-editorial-create-submit" testID="blog-editorial-create-submit" style={{ backgroundColor: colors.primary, borderRadius: 10, paddingVertical: 10, alignItems: 'center', opacity: busy ? 0.6 : 1 }}>
            <Text style={{ color: colors.primaryText, fontWeight: '800' }}>Create draft</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="blog-editorial-status-filters" testID="blog-editorial-status-filters">
        {STATUS_FILTERS.map((s) => (
          <TouchableOpacity
            key={s}
            onPress={() => setStatusFilter(s)}
            data-testid={`blog-editorial-filter-${s}`}
            testID={`blog-editorial-filter-${s}`}
            style={{
              borderRadius: 999,
              paddingHorizontal: 12,
              paddingVertical: 7,
              borderWidth: 1,
              borderColor: statusFilter === s ? colors.primary : colors.border,
              backgroundColor: statusFilter === s ? `${colors.primary}18` : colors.card,
            }}
          >
            <Text style={{ color: statusFilter === s ? colors.primary : colors.textSec, fontWeight: '800', fontSize: 12 }}>
              {s.replace('_', ' ')}{s !== 'all' && counts[s] != null ? ` (${counts[s]})` : ''}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading ? (
        <View style={{ alignItems: 'center', padding: 28 }} data-testid="blog-editorial-loading" testID="blog-editorial-loading">
          <ActivityIndicator color={colors.primary} />
        </View>
      ) : posts.length === 0 ? (
        <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 16, backgroundColor: colors.card, alignItems: 'center' }} data-testid="blog-editorial-empty" testID="blog-editorial-empty">
          <Text style={{ color: colors.textSec }}>No posts in this workflow stage.</Text>
        </View>
      ) : (
        posts.map((post) => {
          const tone = statusTone(colors, post.status);
          const actions = ACTIONS_BY_STATUS[post.status] || [];
          return (
            <View key={post.post_id} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 12, backgroundColor: colors.card, gap: 8 }} data-testid={`blog-editorial-post-${post.post_id}`} testID={`blog-editorial-post-${post.post_id}`}>
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                <Text style={{ color: colors.text, fontWeight: '800', flex: 1, minWidth: 180 }} numberOfLines={1}>{post.title}</Text>
                <View style={{ borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4, backgroundColor: `${tone}18`, borderWidth: 1, borderColor: `${tone}40` }}>
                  <Text style={{ color: tone, fontWeight: '800', fontSize: 11, textTransform: 'uppercase' }} data-testid={`blog-editorial-status-${post.post_id}`} testID={`blog-editorial-status-${post.post_id}`}>{post.status.replace('_', ' ')}</Text>
                </View>
              </View>
              <Text style={{ color: colors.textSec, fontSize: 12 }} numberOfLines={2}>{post.excerpt || post.slug}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 11 }}>
                {post.category || 'General'} • {post.author_name || 'Editorial'}
                {post.status === 'scheduled' && post.scheduled_publish_at ? ` • Goes live ${new Date(post.scheduled_publish_at).toLocaleString()}` : ''}
                {post.status === 'published' && post.published_at ? ` • Published ${new Date(post.published_at).toLocaleDateString()}` : ''}
              </Text>

              {scheduleTarget === post.post_id ? (
                <View style={{ gap: 8 }}>
                  <TextInput
                    value={scheduleAt}
                    onChangeText={setScheduleAt}
                    placeholder="Publish at (ISO, e.g. 2026-07-15T09:00:00Z)"
                    placeholderTextColor={colors.textMuted}
                    style={inputStyle}
                    data-testid="blog-editorial-schedule-input"
                    testID="blog-editorial-schedule-input"
                  />
                  <View style={{ flexDirection: 'row', gap: 8 }}>
                    <TouchableOpacity onPress={() => void runTransition(post.post_id, 'schedule', scheduleAt)} disabled={busy || !scheduleAt.trim()} data-testid="blog-editorial-schedule-confirm" testID="blog-editorial-schedule-confirm" style={{ backgroundColor: colors.primary, borderRadius: 999, paddingHorizontal: 14, paddingVertical: 8, opacity: busy || !scheduleAt.trim() ? 0.6 : 1 }}>
                      <Text style={{ color: colors.primaryText, fontWeight: '800', fontSize: 12 }}>Confirm schedule</Text>
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => { setScheduleTarget(null); setScheduleAt(''); }} data-testid="blog-editorial-schedule-cancel" testID="blog-editorial-schedule-cancel" style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 999, paddingHorizontal: 14, paddingVertical: 8 }}>
                      <Text style={{ color: colors.textSec, fontWeight: '800', fontSize: 12 }}>Cancel</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              ) : (
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                  {actions.map(({ action, label }) => (
                    <TouchableOpacity
                      key={action}
                      onPress={() => {
                        if (action === 'schedule') {
                          setScheduleTarget(post.post_id);
                          setScheduleAt('');
                          return;
                        }
                        void runTransition(post.post_id, action);
                      }}
                      disabled={busy}
                      data-testid={`blog-editorial-action-${action}-${post.post_id}`}
                      testID={`blog-editorial-action-${action}-${post.post_id}`}
                      style={{ borderWidth: 1, borderColor: colors.primary, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 7, opacity: busy ? 0.6 : 1 }}
                    >
                      <Text style={{ color: colors.primary, fontWeight: '800', fontSize: 12 }}>{label}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              )}
            </View>
          );
        })
      )}
    </ScrollView>
  );
};
