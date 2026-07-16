const FEMALE_VOICE_HINTS = [
  'female', 'woman', 'samantha', 'victoria', 'ava', 'allison', 'susan', 'karen',
  'moira', 'tessa', 'zira', 'aria', 'jenny', 'emma', 'serena', 'salli', 'joanna',
  'ivy', 'bella', 'lily', 'sara', 'sophia', 'olivia', 'mia', 'rachel', 'nova',
];

const MALE_VOICE_HINTS = [
  'male', 'man', 'david', 'daniel', 'alex', 'fred', 'jorge', 'thomas', 'arthur',
  'tom', 'matthew', 'michael', 'paul', 'richard', 'george', 'guy', 'rishi',
];

const normalize = (value: string) => String(value || '').trim().toLowerCase();

const scoreVoice = (voice: SpeechSynthesisVoice, preferredLang: string) => {
  const name = normalize(voice.name);
  const lang = normalize(voice.lang);
  let score = 0;

  if (lang === preferredLang) score += 70;
  else if (preferredLang && lang.startsWith(preferredLang.split('-')[0])) score += 40;
  else if (lang.startsWith('en')) score += 22;

  if (voice.localService) score += 8;
  if (voice.default) score += 4;
  if (FEMALE_VOICE_HINTS.some((hint) => name.includes(hint))) score += 120;
  if (MALE_VOICE_HINTS.some((hint) => name.includes(hint))) score -= 30;

  return score;
};

const readVoices = () => {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) return [] as SpeechSynthesisVoice[];
  return window.speechSynthesis.getVoices?.() || [];
};

export const getSpeechSynthesisSupport = () => {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) return null;
  return window.speechSynthesis;
};

export const loadPreferredNovaVoice = async (preferredLang = 'en-US') => {
  const speech = getSpeechSynthesisSupport();
  if (!speech) return null;

  let voices = readVoices();
  if (voices.length === 0) {
    voices = await new Promise<SpeechSynthesisVoice[]>((resolve) => {
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        speech.removeEventListener?.('voiceschanged', onVoicesChanged as EventListener);
        resolve(readVoices());
      };
      const onVoicesChanged = () => finish();
      speech.addEventListener?.('voiceschanged', onVoicesChanged as EventListener);
      setTimeout(finish, 450);
    });
  }

  if (voices.length === 0) return null;

  const targetLang = normalize(preferredLang || 'en-US');
  return [...voices].sort((a, b) => scoreVoice(b, targetLang) - scoreVoice(a, targetLang))[0] || null;
};