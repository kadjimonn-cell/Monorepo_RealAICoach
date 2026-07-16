import { useEffect, useRef } from 'react';
import { Platform } from 'react-native';

/**
 * useFocusTrap — Traps keyboard focus within a modal/dialog.
 * Also handles Escape key to close the dialog.
 *
 * @param active - Whether the focus trap is active
 * @param onClose - Callback to close the dialog
 */
export function useFocusTrap(active: boolean, onClose?: () => void) {
  const containerRef = useRef<HTMLElement | null>(null);
  const prevFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (Platform.OS !== 'web' || !active) return;

    // Store the currently focused element to restore later
    prevFocusRef.current = document.activeElement as HTMLElement;

    const handleKeyDown = (e: KeyboardEvent) => {
      // Escape closes the dialog
      if (e.key === 'Escape' && onClose) {
        e.preventDefault();
        onClose();
        return;
      }

      // Tab traps focus within the container
      if (e.key === 'Tab') {
        const container = containerRef.current;
        if (!container) return;

        const focusable = container.querySelectorAll(
          'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
        );
        if (focusable.length === 0) return;

        const first = focusable[0] as HTMLElement;
        const last = focusable[focusable.length - 1] as HTMLElement;

        if (e.shiftKey) {
          if (document.activeElement === first) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);

    // Auto-focus first focusable element
    requestAnimationFrame(() => {
      const container = containerRef.current;
      if (!container) return;
      const firstFocusable = container.querySelector(
        'button:not([disabled]), [tabindex]:not([tabindex="-1"]), input:not([disabled])'
      ) as HTMLElement;
      firstFocusable?.focus();
    });

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      // Restore focus to previously focused element
      prevFocusRef.current?.focus();
    };
  }, [active, onClose]);

  // Helper to set the container ref on the modal wrapper
  const setRef = (el: any) => {
    if (Platform.OS === 'web' && el) {
      // In React Native Web, el._nativeTag gives us the DOM node
      const node = el instanceof HTMLElement ? el : el?._nativeTag || el;
      containerRef.current = node;
    }
  };

  return { setRef };
}
