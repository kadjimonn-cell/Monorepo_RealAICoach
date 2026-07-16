// Cookie Policy Broadcast — dedicated Operations tab that locks the
// underlying LegalNoticeBroadcastPanel to policy_type="Cookie Policy".
// The `terms_policy_update` email template handles the actual send —
// this wrapper just gives the admin a direct, unambiguous entry point
// so they can't accidentally dispatch a Cookie Policy notice under a
// ToS subject line, and deep-links like
// /admin-console?tab=cookie-policy-broadcast always land in the right
// composer state.
import React from 'react';
import LegalNoticeBroadcastPanel from './LegalNoticeBroadcastPanel';
import { useTranslation } from '../../hooks/useTranslation';

export default function CookiePolicyBroadcastPanel() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  return (
    <LegalNoticeBroadcastPanel
      lockedPolicyType="Cookie Policy"
      headingLabel={tx('admin.cookiePolicyBroadcast.heading', 'Cookie Policy Broadcast')}
      headingSubtitle={
        tx('admin.cookiePolicyBroadcast.subtitle',
          'Send a Cookie Policy update email to every user. Uses the same terms_policy_update email template as the Legal Notice Broadcast tab — this tab simply locks the policy type so the subject line and CTA always say "Cookie Policy". Dry-run → type "SEND" → audited.')
      }
    />
  );
}
