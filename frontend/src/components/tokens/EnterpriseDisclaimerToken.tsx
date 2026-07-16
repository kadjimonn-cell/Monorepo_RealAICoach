import React from 'react';
import EnterpriseAIDisclaimer from '../EnterpriseAIDisclaimer';

interface EnterpriseDisclaimerTokenProps {
  context?: 'footer' | 'banner';
  testIdPrefix?: string;
  maxWidth?: number;
  legalProfile?: 'default' | 'strict_regulated';
  alignContent?: 'start' | 'center';
}

/**
 * One-line reusable token for enterprise AI disclaimer placement.
 * Usage:
 *   <EnterpriseDisclaimerToken context="footer" />
 */
export const EnterpriseDisclaimerToken = ({
  context = 'footer',
  testIdPrefix,
  maxWidth,
  legalProfile,
  alignContent,
}: EnterpriseDisclaimerTokenProps) => {
  const resolvedPrefix = testIdPrefix || (context === 'banner' ? 'banner-ai-disclaimer' : 'footer-ai-disclaimer');
  const resolvedWidth = typeof maxWidth === 'number' ? maxWidth : context === 'banner' ? 1040 : 860;

  return <EnterpriseAIDisclaimer testIdPrefix={resolvedPrefix} maxWidth={resolvedWidth} legalProfile={legalProfile} alignContent={alignContent} />;
};

export default EnterpriseDisclaimerToken;

/* i18n-probe t('i18n.auto.probe') */
