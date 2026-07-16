// Detect web platform using browser APIs (more reliable for Expo Web bundling)
const isWeb = typeof window !== 'undefined' && typeof document !== 'undefined';

export const getTestProps = (id: string): any => {
  // Return both testID and data-testid for maximum compatibility
  if (isWeb) {
    return { testID: id, 'data-testid': id };
  }
  return { testID: id };
};
