import { useCallback, useEffect, useRef, useState } from 'react';
import type { ChatMessage } from './helpTypes';

const TICK_MS = 40;

export const useNovaTypewriter = (messages: ChatMessage[]) => {
  const [active, setActive] = useState<{ id: string; chars: number } | null>(null);
  const prevIdsRef = useRef<Set<string> | null>(null);
  const prevLastRoleRef = useRef<string>('');
  const timerRef = useRef<any>(null);

  useEffect(() => {
    const ids = new Set(messages.map((m) => m.id));
    if (prevIdsRef.current === null) {
      prevIdsRef.current = ids;
      prevLastRoleRef.current = messages[messages.length - 1]?.role || '';
      return;
    }
    const fresh = messages.filter((m) => !prevIdsRef.current!.has(m.id));
    const prevLastRole = prevLastRoleRef.current;
    prevIdsRef.current = ids;
    prevLastRoleRef.current = messages[messages.length - 1]?.role || '';

    if (fresh.length !== 1) return;
    const msg = fresh[0];
    if (msg.role !== 'assistant' || !msg.content || prevLastRole !== 'user') return;

    if (timerRef.current) clearInterval(timerRef.current);
    const total = msg.content.length;
    const durationMs = Math.min(3500, Math.max(600, total * 12));
    const step = Math.max(1, Math.ceil(total / (durationMs / TICK_MS)));
    setActive({ id: msg.id, chars: step });
    timerRef.current = setInterval(() => {
      setActive((prev) => {
        if (!prev || prev.id !== msg.id) {
          clearInterval(timerRef.current);
          return prev;
        }
        const next = prev.chars + step;
        if (next >= total) {
          clearInterval(timerRef.current);
          return null;
        }
        return { id: prev.id, chars: next };
      });
    }, TICK_MS);
  }, [messages]);

  useEffect(() => () => {
    if (timerRef.current) clearInterval(timerRef.current);
  }, []);

  const skip = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    setActive(null);
  }, []);

  const isAnimating = useCallback(
    (msg: ChatMessage) => !!active && active.id === msg.id,
    [active],
  );

  const getVisibleContent = useCallback(
    (msg: ChatMessage) => (active && active.id === msg.id ? msg.content.slice(0, active.chars) : msg.content),
    [active],
  );

  return { getVisibleContent, isAnimating, skip };
};
