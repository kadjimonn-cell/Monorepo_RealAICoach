import { useEffect, useRef, useState, useCallback } from 'react';
import { getFeatureDraft, setFeatureDraft } from '../utils/featureDrafts';

export function useFeatureDraft(featureId: string, initialValue = '') {
  const [value, setValue] = useState(initialValue);
  const hasUserEdited = useRef(false);

  useEffect(() => {
    let active = true;
    const hydrate = async () => {
      const stored = await getFeatureDraft(featureId);
      if (!active) return;
      if (!hasUserEdited.current) {
        setValue(stored || initialValue);
      }
    };
    hydrate();
    return () => {
      active = false;
    };
  }, [featureId, initialValue]);

  const updateValue = useCallback((text: string) => {
    hasUserEdited.current = true;
    setValue(text);
    setFeatureDraft(featureId, text);
  }, [featureId]);

  return [value, updateValue] as const;
}
