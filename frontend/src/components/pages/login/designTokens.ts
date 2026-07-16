import { Platform } from 'react-native';

export const blur = Platform.select({
  web: { backdropFilter: 'blur(32px)', WebkitBackdropFilter: 'blur(32px)' } as any,
  default: {},
});
