import AISearchScreen from '../../src/components/AISearchScreen';
import FeatureLayout from '../../src/components/FeatureLayout';
import { useTranslation } from '../../src/hooks/useTranslation';

const AISearchFeature = () => {
  const { t } = useTranslation();
  t('i18n.route.features.ai-search.probe');

  return (
    <FeatureLayout
      feature="ai-search"
      title="Deep Research Navigator"
      subtitle="Research with multi-agent synthesis, reliable summaries, and actionable follow-ups"
      icon="search"
    >
      <AISearchScreen />
    </FeatureLayout>
  );
};

export default AISearchFeature;