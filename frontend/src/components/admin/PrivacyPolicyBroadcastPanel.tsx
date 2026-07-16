// Privacy Policy Broadcast — dedicated Operations tab that locks the
// underlying LegalNoticeBroadcastPanel to policy_type="Privacy Policy".
// The `terms_policy_update` email template handles the actual send —
// this wrapper just gives the admin a direct, unambiguous entry point
// so they can't accidentally dispatch a Privacy Policy notice under a
// ToS subject line, and deep-links like
// /admin-console?tab=privacy-policy-broadcast always land in the right
// composer state.
import React from 'react';
import LegalNoticeBroadcastPanel from './LegalNoticeBroadcastPanel';
import { useTranslation } from '../../hooks/useTranslation';

export default function PrivacyPolicyBroadcastPanel() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  return (
    <LegalNoticeBroadcastPanel
      lockedPolicyType="Privacy Policy"
      headingLabel={tx('admin.privacyPolicyBroadcast.heading', 'Privacy Policy Broadcast')}
      headingSubtitle={
        tx('admin.privacyPolicyBroadcast.subtitle',
          'Send a Privacy Policy update email to every user. Uses the same terms_policy_update email template as the Legal Notice Broadcast tab — this tab simply locks the policy type so the subject line and CTA always say "Privacy Policy". Dry-run → type "SEND" → audited.')
      }
    />
  );
}
