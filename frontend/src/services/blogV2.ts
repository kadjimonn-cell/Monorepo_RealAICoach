import api from './api';

export interface BlogCard {
  post_id: string;
  slug: string;
  title: string;
  excerpt: string;
  cover_image?: string;
  category: string;
  tags: string[];
  author_name: string;
  author_slug: string;
  author_role: string;
  published_at: string;
  date_display: string;
  read_time_minutes: number;
  premium_required: boolean;
  premium_locked: boolean;
  bookmarked: boolean;
  metrics?: {
    views?: number;
    bookmarks?: number;
    shares?: number;
  };
  history?: {
    progress_percent?: number;
    dwell_seconds?: number;
    updated_at?: string;
  };
}

export interface BlogAuthor {
  author_slug: string;
  name: string;
  role: string;
  bio: string;
  avatar_url?: string;
  focus_areas: string[];
  stats?: { posts?: number; total_views?: number };
  social?: { linkedin?: string; x?: string };
}

export interface BlogHomePayload {
  featured: BlogCard | null;
  trending: BlogCard[];
  latest: BlogCard[];
  categories: { name: string; count: number }[];
  authors: BlogAuthor[];
  stats: {
    total_posts: number;
    total_views: number;
    total_bookmarks: number;
    last_refreshed_at: string;
  };
  engagement_loop?: BlogEngagementLoop;
  viewer_plan: string;
}

export interface BlogEngagementLoop {
  streak: {
    current: number;
    longest: number;
    last_read_date: string;
    days_to_keep_streak: number;
    badges?: string[];
    next_milestone?: {
      threshold: number;
      remaining: number;
    } | null;
  };
  reminder: {
    enabled: boolean;
    mode: 'adaptive' | 'daily' | 'three_per_week' | string;
    status: string;
    message: string;
    next_reminder_at: string;
    snoozed_until: string;
    recommended_action: string;
    digest?: {
      in_app_enabled: boolean;
      email_enabled: boolean;
      last_digest_at: string;
      last_email_digest_at: string;
    };
  };
  conversion_trigger: {
    show_upgrade_nudge: boolean;
    reason: string;
    streak_threshold: number;
    locked_premium_available: boolean;
  };
  rewards?: {
    unlock_tokens: number;
    premium_preview_unlocks_used: number;
    referral_bonus_days_total: number;
    invite_code: string;
    invite_link: string;
    referrals_count: number;
  };
}

export interface BlogNextBestItem {
  post_id: string;
  slug: string;
  title: string;
  excerpt: string;
  cover_image?: string;
  category: string;
  author_name: string;
  read_time_minutes: number;
  premium_required: boolean;
  sequence_reason: string;
}

export interface BlogShareVariantOptimizerChannel {
  recommended_variant: 'short' | 'long' | 'benefit';
  recommended_label: string;
  winner_variant: 'short' | 'long' | 'benefit';
  winner_label: string;
  winner_share_pct: number;
  sample_size: number;
  strategy: string;
  exploration_rate: number;
  confidence_hint?: number;
  variant_metrics: Record<'short' | 'long' | 'benefit', {
    shares: number;
    unique_owners: number;
    surface_count: number;
    weighted_engagement: number;
    share_pct: number;
    draw: number;
  }>;
}

export interface BlogShareVariantOptimizer {
  window_days: number;
  generated_at: string;
  default_mode: 'auto';
  global_top_variant: 'short' | 'long' | 'benefit';
  global_top_variant_label: string;
  exploration_rate: number;
  channels: Record<string, BlogShareVariantOptimizerChannel>;
}

export interface BlogListPayload {
  items: BlogCard[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
  viewer_plan: string;
}

export interface BlogDetailPayload extends BlogCard {
  preview_blocks: { type: string; text: string }[];
  content_blocks: { type: string; text: string }[];
  premium_sections: { heading: string; content: string }[];
  premium_preview: { heading: string; content: string }[];
  premium_gate: {
    required: boolean;
    unlocked: boolean;
    cta: string;
  };
  author?: BlogAuthor;
  related_posts: BlogCard[];
  token_unlocked?: boolean;
  viewer_plan: string;
}

export interface BlogAuthorPayload {
  author: BlogAuthor;
  posts: BlogCard[];
  viewer_plan: string;
}

const normalizeError = (error: any) => {
  const status = error?.response?.status ?? error?.status ?? 500;
  const message =
    error?.response?.data?.detail ||
    error?.response?.data?.message ||
    error?.message ||
    'Request failed';
  return { status, message };
};

export const isUnauthorized = (error: any) => normalizeError(error).status === 401;

export const getBlogHome = async (): Promise<BlogHomePayload> => {
  const response = await api.get('/blog/v2/home');
  return response.data as BlogHomePayload;
};

export const getBlogPosts = async (params: {
  q?: string;
  category?: string;
  tag?: string;
  author_slug?: string;
  page?: number;
  page_size?: number;
  sort?: string;
}): Promise<BlogListPayload> => {
  const response = await api.get('/blog/v2/posts', { params });
  return response.data as BlogListPayload;
};

export const searchBlogPosts = async (q: string, page = 1, page_size = 12): Promise<BlogListPayload> => {
  const response = await api.get('/blog/v2/search', { params: { q, page, page_size } });
  return response.data as BlogListPayload;
};

export const getBlogPost = async (slug: string): Promise<BlogDetailPayload> => {
  const response = await api.get(`/blog/v2/posts/${encodeURIComponent(slug)}`);
  return response.data as BlogDetailPayload;
};

export const getBlogAuthor = async (authorSlug: string): Promise<BlogAuthorPayload> => {
  const response = await api.get(`/blog/v2/authors/${encodeURIComponent(authorSlug)}`);
  return response.data as BlogAuthorPayload;
};

export const getBlogRecommendations = async (limit = 8): Promise<{ items: BlogCard[]; viewer_plan: string }> => {
  const response = await api.get('/blog/v2/recommendations', { params: { limit } });
  return response.data;
};

export const getAiSummary = async (slug: string): Promise<{
  ok: boolean;
  summary: string;
  key_takeaways: string[];
  action_plan: string[];
  model: string;
  cached: boolean;
  upgrade_required?: boolean;
}> => {
  const response = await api.post('/blog/v2/ai/summary', { slug });
  return response.data;
};

export const writeBlogHistory = async (post_id: string, progress_percent: number, dwell_seconds: number) => {
  const response = await api.post('/blog/v2/me/history', {
    post_id,
    progress_percent,
    dwell_seconds,
  });
  return response.data;
};

export const getBlogEngagementLoop = async (): Promise<{ engagement_loop: BlogEngagementLoop; viewer_plan: string }> => {
  const response = await api.get('/blog/v2/engagement-loop');
  return response.data;
};

export const updateBlogReminderSettings = async (payload: {
  enabled?: boolean;
  mode?: 'adaptive' | 'daily' | 'three_per_week';
  digest_in_app_enabled?: boolean;
  digest_email_enabled?: boolean;
}) => {
  const response = await api.patch('/blog/v2/me/reminder-settings', payload);
  return response.data as { ok: boolean; engagement_loop: BlogEngagementLoop };
};

export const sendBlogReminderAction = async (action: 'snooze_24h' | 'dismiss' | 'trigger_now') => {
  const response = await api.post('/blog/v2/me/reminder-action', { action });
  return response.data as { ok: boolean; engagement_loop: BlogEngagementLoop };
};

export const getBlogNextBest = async (limit = 5, refresh = false): Promise<{
  week_key: string;
  strategy: string;
  source: string;
  generated_at: string;
  items: BlogNextBestItem[];
}> => {
  const response = await api.get('/blog/v2/next-best', { params: { limit, refresh } });
  return response.data;
};

export const getBlogWeeklyDigest = async (refresh = false, send_email = false): Promise<{
  digest: {
    week_key: string;
    generated_at: string;
    headline: string;
    highlights: string[];
    email_sent_at: string;
    next_best: {
      items: BlogNextBestItem[];
    };
  };
  email_result?: {
    ok: boolean;
    status: string;
    reason?: string;
  } | null;
}> => {
  const response = await api.get('/blog/v2/weekly-digest', { params: { refresh, send_email } });
  return response.data;
};

export const getBlogRewards = async (): Promise<{
  streak: BlogEngagementLoop['streak'];
  rewards: NonNullable<BlogEngagementLoop['rewards']>;
  conversion_trigger: BlogEngagementLoop['conversion_trigger'];
  unlockables: {
    premium_preview_tokens: number;
    available: boolean;
  };
  referral: {
    invite_code: string;
    invite_link: string;
    referrals_count: number;
    bonus_days_total: number;
  };
  weekly_digest: {
    week_key: string;
    generated_at: string;
    email_sent_at: string;
    headline: string;
  };
  next_best: {
    week_key: string;
    generated_at: string;
    strategy: string;
    items: BlogNextBestItem[];
  };
  channel_attribution?: {
    window_days: number;
    top_channel: string;
    totals: {
      clicks: number;
      unique_clicks: number;
      claim_attributed_clicks: number;
    };
    channels: Record<string, {
      clicks: number;
      unique_clicks: number;
      claim_attributed_clicks: number;
    }>;
    trend: { date: string; clicks: number }[];
  };
  share_variant_optimizer?: BlogShareVariantOptimizer;
}> => {
  const response = await api.get('/blog/v2/me/rewards');
  return response.data;
};

export const claimBlogReferralBonus = async (invite_code: string): Promise<{
  ok: boolean;
  boost_days: number;
  reason: string;
  rewards: ReturnType<typeof getBlogRewards> extends Promise<infer T> ? T : never;
}> => {
  const response = await api.post('/blog/v2/me/referral-claim', { invite_code });
  return response.data;
};

export const unlockBlogPremiumWithToken = async (post_id: string): Promise<{
  ok: boolean;
  status: 'unlocked' | 'already_unlocked';
  post_id: string;
  remaining_tokens: number;
}> => {
  const response = await api.post(`/blog/v2/me/unlock-premium/${encodeURIComponent(post_id)}`);
  return response.data;
};

export const trackBlogFunnelEvent = async (event_name: string, context: Record<string, any> = {}) => {
  const response = await api.post('/blog/v2/me/funnel-event', { event_name, context });
  return response.data;
};

export const getBlogHistory = async (): Promise<{ items: BlogCard[] }> => {
  const response = await api.get('/blog/v2/me/history');
  return response.data;
};

export const getBlogBookmarks = async (): Promise<{ items: BlogCard[] }> => {
  const response = await api.get('/blog/v2/me/bookmarks');
  return response.data;
};

export const addBlogBookmark = async (postId: string) => {
  const response = await api.post(`/blog/v2/me/bookmarks/${encodeURIComponent(postId)}`);
  return response.data;
};

export const removeBlogBookmark = async (postId: string) => {
  const response = await api.delete(`/blog/v2/me/bookmarks/${encodeURIComponent(postId)}`);
  return response.data;
};

export const parseBlogError = normalizeError;
