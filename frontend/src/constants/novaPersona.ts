export const NOVA_PORTRAIT_URL = 'https://images.unsplash.com/photo-1689600944138-da3b150d9cb8?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NTYxODl8MHwxfHNlYXJjaHwxfHxwcm9mZXNzaW9uYWwlMjB3b21hbiUyMHBvcnRyYWl0JTIwYnVzaW5lc3MlMjBoZWFkc2hvdHxlbnwwfHx8fDE3Nzc5MjM5OTZ8MA&ixlib=rb-4.1.0&q=85';

export const NOVA_INTRO_FALLBACK = "I’m Nova, your on-demand AI guide for platform questions, workflow clarity, and next-step decisions.";

export const NOVA_QUICK_QUESTION_FALLBACKS: { key: string; fallback: string }[] = [
  { key: 'help.nova.quickQ1', fallback: 'What can you help me with?' },
  { key: 'help.nova.quickQ2', fallback: 'How does AI coaching work?' },
  { key: 'help.nova.quickQ3', fallback: 'How do I upgrade or manage my plan?' },
];

export const buildNovaQuickQuestionFallbacks = (t: (key: string) => string): string[] =>
  NOVA_QUICK_QUESTION_FALLBACKS.map(({ key, fallback }) => {
    const value = t(key);
    return !value || value === key ? fallback : value;
  });
