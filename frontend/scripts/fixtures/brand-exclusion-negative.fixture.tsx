import React from 'react';

// NEGATIVE FIXTURE (intentional anti-pattern):
// This file is NEVER imported by runtime app code.
// It exists only to prove brand-exclusion-gate blocks forbidden composition.
export const BrandExclusionNegativeFixture = ({ t }: { t: (key: string) => string }) => {
  const forbiddenBrand = t('autofix.precision12.real') + 'AI' + t('autofix.precision12.coach');
  return <span>{forbiddenBrand}</span>;
};
