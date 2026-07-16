import React from 'react';
import { Platform } from 'react-native';
// Static import so Metro can resolve it at bundle time. On web this ships
// with Expo/react-native-web anyway (ReactDOM renders the tree). A runtime
// Platform check short-circuits on native so createPortal is never invoked
// there — the helper just returns children inline.
import { createPortal } from 'react-dom';

/**
 * WebPortal
 *
 * Escapes every ancestor on web by portaling its children directly to
 * `document.body`. Critical for full-screen modals because react-native-web's
 * `ScrollView` renders as a `<div>` with `transform: matrix(1,0,0,1,0,0)`
 * (non-`none`) — per CSS spec, any ancestor with `transform !== 'none'`
 * becomes the containing block for `position: fixed` descendants, so the
 * modal gets pinned to the ScrollView instead of the viewport. When the
 * user has scrolled inside the ScrollView, the modal appears *above* the
 * visible area and the user sees nothing happen. Portaling to
 * `document.body` side-steps the entire ancestor chain.
 *
 * No-op on native — children render in-place.
 */
export default function WebPortal({ children }: { children: React.ReactNode }) {
  if (Platform.OS !== 'web' || typeof document === 'undefined') {
    return <>{children}</>;
  }
  return createPortal(children, document.body) as any;
}

/* i18n-probe t('i18n.auto.probe') */
