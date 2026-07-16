import { useEffect } from 'react';
import { Platform } from 'react-native';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

/**
 * BodyScrollLock
 *
 * Locks page scroll while a full-screen modal/overlay is open on web.
 *
 * Why this is more than `document.body.style.overflow = 'hidden'`:
 * react-native-web's top-level `<ScrollView>` renders as a scrolling `<div>`
 * that owns its own scroll position — the document body itself never
 * scrolls. Locking body overflow alone is a no-op against that container.
 * So we ALSO find every `overflowY: auto|scroll` descendant of `<body>`
 * whose scroll height exceeds its client height and pin it too, plus apply
 * `touchAction: none` on the body to suppress iOS Safari rubber-band.
 *
 * Restores all previous values on unmount so closing the modal never leaves
 * the page frozen. No-op on native platforms.
 */
export default function BodyScrollLock() {
  useEffect(() => {
    if (Platform.OS !== 'web' || typeof document === 'undefined') return;

    const body = document.body;
    const prevBodyOverflow = body.style.overflow;
    const prevTouch = (body.style as any).touchAction as string | undefined;
    body.style.overflow = 'hidden';
    (body.style as any).touchAction = 'none';

    // Also lock every scrollable container inside the body (react-native-web
    // ScrollViews, anything with overflow:auto/scroll). Record prev values so
    // we can restore them verbatim.
    const locked: { el: HTMLElement; prevOverflow: string; prevTouch: string }[] = [];
    try {
      const all = body.querySelectorAll<HTMLElement>('*');
      all.forEach((el) => {
        const cs = getComputedStyle(el);
        const oy = cs.overflowY;
        if ((oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight + 2) {
          locked.push({
            el,
            prevOverflow: el.style.overflow,
            prevTouch: (el.style as any).touchAction || '',
          });
          el.style.overflow = 'hidden';
          (el.style as any).touchAction = 'none';
        }
      });
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/BodyScrollLock.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }

    return () => {
      body.style.overflow = prevBodyOverflow || '';
      (body.style as any).touchAction = prevTouch || '';
      locked.forEach(({ el, prevOverflow, prevTouch: pt }) => {
        el.style.overflow = prevOverflow;
        (el.style as any).touchAction = pt;
      });
    };
  }, []);

  return null;
}

/* i18n-probe t('i18n.auto.probe') */
