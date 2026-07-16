/**
 * Simple event emitter for real-time notification events.
 * Used to bridge WebSocket messages to UI components (NotificationBell, etc.)
 *
 * Also manages global modal state (whatsNew, notificationDropdown) that must
 * survive Expo Web's aggressive mount/unmount cycles.
 */
type Listener = (data: any) => void;

class NotificationEventEmitter {
  private listeners: Map<string, Set<Listener>> = new Map();

  /** Module-level modal visibility — survives React unmount/remount. */
  whatsNewVisible = false;
  notificationDropdownOpen = false;

  on(event: string, listener: Listener) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(listener);
    return () => this.off(event, listener);
  }

  off(event: string, listener: Listener) {
    this.listeners.get(event)?.delete(listener);
  }

  emit(event: string, data?: any) {
    this.listeners.get(event)?.forEach(fn => fn(data));
  }

  openWhatsNew() {
    this.closeNotifications();
    this.whatsNewVisible = true;
    this.emit('whats-new-visibility', true);
    if (typeof document !== 'undefined') {
      document.dispatchEvent(new CustomEvent('ne:whats-new', { detail: true }));
    }
  }

  closeWhatsNew() {
    this.whatsNewVisible = false;
    this.emit('whats-new-visibility', false);
    if (typeof document !== 'undefined') {
      document.dispatchEvent(new CustomEvent('ne:whats-new', { detail: false }));
    }
  }

  openNotifications() {
    this.notificationDropdownOpen = true;
    this.emit('notification-dropdown-visibility', true);
  }

  closeNotifications() {
    this.notificationDropdownOpen = false;
    this.emit('notification-dropdown-visibility', false);
  }
}

export const notificationEvents = (() => {
  // Ensure true singleton across code-split chunks
  if (typeof window !== 'undefined' && (window as any).__notificationEvents) {
    return (window as any).__notificationEvents as NotificationEventEmitter;
  }
  const instance = new NotificationEventEmitter();
  if (typeof window !== 'undefined') {
    (window as any).__notificationEvents = instance;
  }
  return instance;
})();
