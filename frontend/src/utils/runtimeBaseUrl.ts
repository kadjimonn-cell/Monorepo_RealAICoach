const PREVIEW_HOST_SUFFIX = '.preview.emergentagent.com';
const PREVIEW_HOST_SUFFIX_CF = '.preview.emergentcf.cloud';

export type BackendOriginConsistency = {
  ok: boolean;
  canonicalBase: string;
  reactBase: string;
  expoBase: string;
  runtimeBase: string;
  issues: string[];
};

export function normalizeBaseUrl(raw?: string | null): string {
  const trimmed = String(raw || '').trim().replace(/\/+$/, '');
  
  // Preserve HTTP for localhost/127.0.0.1 to avoid SSL errors in local development
  if (trimmed.match(/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i)) {
    return trimmed;
  }
  
  // Force HTTPS for all other HTTP URLs (production/preview environments)
  return trimmed.replace(/^http:\/\//i, 'https://');
}

function getHost(raw?: string | null): string {
  try {
    return new URL(normalizeBaseUrl(raw)).host.toLowerCase();
  } catch {
    return '';
  }
}

function getEnvBases(explicitEnvBase?: string | null) {
  const reactBase = normalizeBaseUrl(process.env.REACT_APP_BACKEND_URL || '');
  const expoBase = normalizeBaseUrl((process.env as any)['EXPO_PUBLIC_BACKEND_URL'] || '');
  const explicit = normalizeBaseUrl(explicitEnvBase || '');
  const canonical = explicit || reactBase || expoBase;
  return { reactBase, expoBase, canonical };
}

function isLocalHost(host: string): boolean {
  return host === 'localhost' || host === '127.0.0.1' || host.endsWith('.localhost');
}

function isTrustedRuntimeShell(host: string): boolean {
  return (
    host === 'app.emergent.sh'
    || host.endsWith('.emergent.sh')
    || host === 'app.emergentagent.com'
    || host.endsWith('.emergentagent.com')
  );
}

function isPreviewHost(host: string): boolean {
  return host.endsWith(PREVIEW_HOST_SUFFIX) || host.endsWith(PREVIEW_HOST_SUFFIX_CF);
}

export function shouldPreferRuntimeOrigin(envBase?: string | null, runtimeOrigin?: string | null): boolean {
  const envHost = getHost(envBase);
  const runtimeHost = getHost(runtimeOrigin);

  if (!runtimeHost || envHost === runtimeHost) {
    return false;
  }

  if (isLocalHost(runtimeHost)) {
    return true;
  }

  // Global platform shell continuity:
  // When the app is rendered inside trusted shell hosts, prefer same-origin API
  // over a configured preview host to avoid cross-origin credentialed CORS failures.
  if (isTrustedRuntimeShell(runtimeHost)) {
    if (!envHost) {
      return true;
    }
    if (isPreviewHost(envHost)) {
      return true;
    }
    return false;
  }

  // Locked auth continuity rule:
  // If canonical backend env is configured, it is always the source of truth.
  if (envHost) {
    return false;
  }

  // If env host is a preview host, treat it as canonical backend by default
  // for non-shell runtime contexts.
  if (isPreviewHost(envHost)) {
    return false;
  }

  // For non-preview deployments, prefer configured env base by default.
  return false;
}

export function getBackendOriginConsistency(
  explicitEnvBase?: string | null,
  explicitRuntimeOrigin?: string | null,
): BackendOriginConsistency {
  const { reactBase, expoBase, canonical } = getEnvBases(explicitEnvBase);
  const runtimeBase = normalizeBaseUrl(
    explicitRuntimeOrigin || (typeof window !== 'undefined' && window.location?.origin ? window.location.origin : ''),
  );

  const issues: string[] = [];
  const reactHost = getHost(reactBase);
  const expoHost = getHost(expoBase);

  if (reactHost && expoHost && reactHost !== expoHost) {
    issues.push(
      `REACT_APP_BACKEND_URL host (${reactHost}) does not match EXPO_PUBLIC_BACKEND_URL host (${expoHost}).`,
    );
  }

  const canonicalHost = getHost(canonical);
  const runtimeHost = getHost(runtimeBase);
  const runtimePreferred = shouldPreferRuntimeOrigin(canonical, runtimeBase);
  if (
    canonicalHost
    && runtimeHost
    && !runtimePreferred
    && canonicalHost.endsWith(PREVIEW_HOST_SUFFIX)
    && runtimeHost.endsWith(PREVIEW_HOST_SUFFIX)
    && canonicalHost !== runtimeHost
  ) {
    issues.push(
      `Runtime host (${runtimeHost}) does not match canonical backend host (${canonicalHost}).`,
    );
  }

  if (!canonical && !runtimeBase) {
    issues.push('No backend origin could be resolved from env or runtime origin.');
  }

  return {
    ok: issues.length === 0,
    canonicalBase: canonical,
    reactBase,
    expoBase,
    runtimeBase,
    issues,
  };
}

export function resolveRuntimeBaseUrl(explicitEnvBase?: string | null, explicitRuntimeOrigin?: string | null): string {
  const consistency = getBackendOriginConsistency(explicitEnvBase, explicitRuntimeOrigin);
  const envBase = normalizeBaseUrl(consistency.canonicalBase);
  const runtimeOrigin = normalizeBaseUrl(
    explicitRuntimeOrigin || (typeof window !== 'undefined' && window.location?.origin ? window.location.origin : '')
  );

  if (shouldPreferRuntimeOrigin(envBase, runtimeOrigin) && runtimeOrigin) {
    return runtimeOrigin;
  }

  // Enforce single canonical backend origin from env to preserve cookie/session continuity.
  if (envBase) {
    return envBase;
  }

  return runtimeOrigin;
}

export function getRuntimeBackendUrl(): string {
  return resolveRuntimeBaseUrl();
}