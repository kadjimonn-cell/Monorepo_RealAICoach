import api from '../services/api';
import { handleAppRecoverableError } from './appRecoverableError';

export const CERTIFICATE_ASSET_VERSION = 'rac-cert-render-v6-learning-certificate-v15-exempt';

export const formatCertificateDate = (value, empty = '—') => {
  if (!value) return empty;
  try {
    return new Date(value).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  } catch {
    return String(value);
  }
};

export const absoluteCertificateUrl = (value) => {
  const raw = String(value || '').trim();
  if (!raw) return '';
  if (raw.startsWith('http://') || raw.startsWith('https://')) return raw;
  const base = String(process.env.EXPO_PUBLIC_BACKEND_URL || process.env.REACT_APP_BACKEND_URL || '').replace(/\/+$/, '');
  if (raw.startsWith('/')) return base ? `${base}${raw}` : raw;
  return base ? `${base}/${raw}` : raw;
};

export const withCertificateAssetVersion = (value) => {
  const target = absoluteCertificateUrl(value);
  if (!target) return '';
  try {
    const parsed = new URL(target, typeof window !== 'undefined' ? window.location.origin : 'https://realaicoach.app');
    if (!parsed.pathname.includes('/ai-learn/certificates/verify/')) return parsed.toString();
    if (!parsed.pathname.endsWith('/png/file') && !parsed.pathname.endsWith('/pdf/file')) return parsed.toString();
    parsed.searchParams.set('cv', CERTIFICATE_ASSET_VERSION);
    return parsed.toString();
  } catch {
    return target;
  }
};

export const buildCertificateRenderUrl = (verificationId, layout = 'portrait', variant = 'print', version = CERTIFICATE_ASSET_VERSION) => {
  const safeVerificationId = String(verificationId || '').trim();
  if (!safeVerificationId) return '';
  const base = absoluteCertificateUrl(`/api/ai-learn/certificates/verify/${encodeURIComponent(safeVerificationId)}/png/file`);
  if (!base) return '';
  const parsed = new URL(base, typeof window !== 'undefined' ? window.location.origin : 'https://realaicoach.app');
  parsed.searchParams.set('variant', variant);
  parsed.searchParams.set('layout', layout === 'landscape' ? 'landscape' : 'portrait');
  parsed.searchParams.set('cv', version);
  return parsed.toString();
};

export const buildCertificateCompareProofUrl = (verificationId, version = CERTIFICATE_ASSET_VERSION, zoom = false) => {
  const safeVerificationId = String(verificationId || '').trim();
  if (!safeVerificationId) return '';
  const slug = zoom
    ? `/support/certificate-portrait-vs-landscape-zoom-cert_${safeVerificationId}.png`
    : `/support/certificate-portrait-vs-landscape-compare-${safeVerificationId}.png`;
  const target = absoluteCertificateUrl(slug);
  if (!target) return '';
  const parsed = new URL(target, typeof window !== 'undefined' ? window.location.origin : 'https://realaicoach.app');
  parsed.searchParams.set('v', version);
  return parsed.toString();
};

export { normalizeCertificatePrintLayout, withCertificatePrintLayout } from './certificatePrint';

export const getCertificateStatusMeta = (status, darkMode = false) => {
  const normalized = String(status || 'valid').toLowerCase();
  if (normalized === 'expired') {
    return darkMode
      ? { label: 'Expired', color: '#FBBF24', soft: 'rgba(245,158,11,0.16)', border: 'rgba(251,191,36,0.28)' }
      : { label: 'Expired', color: '#D97706', soft: '#FEF3C7', border: '#FCD34D' };
  }
  if (normalized === 'revoked') {
    return darkMode
      ? { label: 'Revoked', color: '#FCA5A5', soft: 'rgba(220,38,38,0.18)', border: 'rgba(248,113,113,0.3)' }
      : { label: 'Revoked', color: '#DC2626', soft: '#FEE2E2', border: '#FECACA' };
  }
  if (normalized === 'invalid') {
    return darkMode
      ? { label: 'Invalid', color: '#FCA5A5', soft: 'rgba(185,28,28,0.2)', border: 'rgba(248,113,113,0.3)' }
      : { label: 'Invalid', color: '#B91C1C', soft: '#FEE2E2', border: '#FECACA' };
  }
  return darkMode
    ? { label: 'Valid', color: '#6EE7B7', soft: 'rgba(16,185,129,0.16)', border: 'rgba(134,239,172,0.25)' }
    : { label: 'Valid', color: '#059669', soft: '#D1FAE5', border: '#A7F3D0' };
};

const CERTIFICATE_ENGAGEMENT_SESSION_KEY = 'rac-certificate-engagement-session-id';

const getCertificateEngagementSessionId = () => {
  if (typeof window === 'undefined') return `native-${Date.now()}`;
  try {
    const existing = window.localStorage.getItem(CERTIFICATE_ENGAGEMENT_SESSION_KEY);
    if (existing) return existing;
    const generated = `certsess-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    window.localStorage.setItem(CERTIFICATE_ENGAGEMENT_SESSION_KEY, generated);
    return generated;
  } catch {
    return `certsess-${Date.now()}`;
  }
};

export const trackCertificateEngagement = async ({ verificationId, eventType, source, metadata = {} }) => {
  if (!verificationId || !eventType) return;
  try {
    await api.post(`/ai-learn/certificates/verify/${encodeURIComponent(verificationId)}/engagement`, {
      event_type: eventType,
      source,
      viewer_session_id: getCertificateEngagementSessionId(),
      metadata: {
        ...metadata,
        pathname: typeof window !== 'undefined' ? window.location.pathname : '',
      },
    });
  } catch (error) { handleAppRecoverableError({ scope: 'src/utils/certificates.ts#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
};