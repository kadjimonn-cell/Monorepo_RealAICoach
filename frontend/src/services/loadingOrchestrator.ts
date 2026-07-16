import { handleAppRecoverableError } from '../utils/appRecoverableError';
type LoadingListener = (activeCount: number) => void;

const activeTickets = new Set<symbol>();
const listeners = new Set<LoadingListener>();

function emit() {
  const count = activeTickets.size;
  listeners.forEach((listener) => {
    try {
      listener(count);
    } catch (error) { handleAppRecoverableError({ scope: 'src/services/loadingOrchestrator.ts#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  });
}

export function beginGlobalLoading(source = 'request'): symbol {
  const ticket = Symbol(source);
  activeTickets.add(ticket);
  emit();
  return ticket;
}

export function endGlobalLoading(ticket?: symbol | null) {
  if (!ticket) return;
  activeTickets.delete(ticket);
  emit();
}

export function subscribeGlobalLoading(listener: LoadingListener) {
  listeners.add(listener);
  listener(activeTickets.size);
  return () => {
    listeners.delete(listener);
  };
}

export function resetGlobalLoading() {
  activeTickets.clear();
  emit();
}
