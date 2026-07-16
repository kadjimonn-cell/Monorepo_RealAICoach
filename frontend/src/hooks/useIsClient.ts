import { useState, useEffect } from 'react';

/**
 * Returns false during SSR and the first client render (hydration),
 * then true after hydration is complete.
 * Use this to guard any rendering that depends on browser-only APIs
 * (window dimensions, Platform.OS, localStorage, etc.)
 */
export function useIsClient(): boolean {
  const [isClient, setIsClient] = useState(false);
  useEffect(() => {
    setIsClient(true);
  }, []);
  return isClient;
}
