import React, { useEffect, useState } from 'react';
import { Platform, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

const CHECKLIST_CSS = `
@keyframes cl-slide-in { from { opacity:0; transform:translateY(16px); } to { opacity:1; transform:translateY(0); } }
@keyframes cl-check-pop { 0% { transform:scale(0); } 50% { transform:scale(1.2); } 100% { transform:scale(1); } }
@keyframes cl-confetti { 0% { opacity:1; transform:translateY(0) rotate(0deg); } 100% { opacity:0; transform:translateY(-60px) rotate(360deg); } }
@keyframes cl-ring-fill { from { stroke-dashoffset:283; } }
@keyframes cl-celebrate { 0%,100% { transform:scale(1); } 50% { transform:scale(1.03); } }
.cl-widget { animation:cl-slide-in .5s ease both; }
.cl-item { transition: background .2s ease, transform .15s ease; cursor:pointer; }
.cl-item:hover { background:rgba(255,255,255,.04) !important; transform:translateX(4px); }
.cl-dismiss-btn { transition: transform .15s ease, box-shadow .15s ease; }
.cl-dismiss-btn:hover { transform:translateY(-1px); box-shadow:0 6px 16px rgba(16,185,129,.3); }
@keyframes cl-start-pulse { 0%,100% { opacity:1; } 50% { opacity:.55; } }
.cl-start-here { animation: cl-start-pulse 2s ease-in-out infinite; }
`;

interface ChecklistItem {
  id: string;
  label: string;
  route: string;
  completed: boolean;
}

interface Props {
  onNavigate?: (route: string) => void;
  responsiveWidth?: number;
}

export default function HomeChecklist({ onNavigate, responsiveWidth }: Props) {
  const { width: windowWidth } = useWindowDimensions();
  const width = responsiveWidth || windowWidth;
  const isDesktop = width >= 768;
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _isTablet = width >= 768 && width < 1024;
  const { colors, darkMode } = useTheme();
  const { t, tx } = useTranslation();
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { data: checklistData, loading: checklistLoading, refetch: _loadChecklist } = useLiveQuery('/home/checklist-status', { entity: 'checklist', pollInterval: 30000 });
  const [items, setItems] = useState<ChecklistItem[]>([]);
  const [dismissed, setDismissed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [celebrating, setCelebrating] = useState(false);
  const [justCompleted, setJustCompleted] = useState<string | null>(null);

  useEffect(() => {
    if (Platform.OS === 'web') {
      const id = 'cl-css';
      if (!document.getElementById(id)) {
        const s = document.createElement('style');
        s.id = id;
        s.textContent = CHECKLIST_CSS;
        document.head.appendChild(s);
      }
    }
  }, []);

  useEffect(() => {
    if (checklistData) {
      setItems(checklistData.items || []);
      setDismissed(checklistData.dismissed || false);
      setLoading(false);
    }
    if (!checklistLoading && !checklistData) setLoading(false);
  }, [checklistData, checklistLoading]);

  const handleItemClick = async (item: ChecklistItem) => {
    if (!item.completed) {
      // Mark as completed
      try {
        await api.post(`/home/checklist-complete/${item.id}`);
        setJustCompleted(item.id);
        setTimeout(() => setJustCompleted(null), 600);
        setItems(prev => prev.map(i => i.id === item.id ? { ...i, completed: true } : i));
      } catch (error) { handleAppRecoverableError({ scope: 'src/components/home/HomeChecklist.tsx#catch1', error, message: tx('home.checklist.errorGeneric', 'Something went wrong. Please retry.'),
        notifyMode: 'silent',
      }); }
    }
    // Navigate
    if (onNavigate) onNavigate(item.route);
    else router.push(item.route as any);
  };

  const handleDismiss = async () => {
    setCelebrating(true);
    try {
      await api.post('/home/checklist-dismiss');
      setTimeout(() => setDismissed(true), 800);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/home/HomeChecklist.tsx#catch2', error, message: tx('home.checklist.errorGeneric', 'Something went wrong. Please retry.'),
        notifyMode: 'silent',
      }); }
  };

  if (loading || dismissed || Platform.OS !== 'web') return null;

  const completedCount = items.filter(i => i.completed).length;
  const total = items.length;
  const percent = total > 0 ? Math.round((completedCount / total) * 100) : 0;
  const allDone = completedCount === total;
  const firstIncompleteId = items.find(i => !i.completed)?.id || null;

  // SVG ring parameters
  const ringR = 36;
  const ringC = 2 * Math.PI * ringR; // ~226
  const ringOffset = ringC - (percent / 100) * ringC;

  const ITEM_ICONS: Record<string, string> = {
    complete_profile: 'person-outline',
    first_ai_session: 'chatbubble-ellipses-outline',
    set_goal: 'flag-outline',
    explore_tools: 'compass-outline',
    complete_tour: 'map-outline',
  };

  const ITEM_COLORS: Record<string, string> = {
    complete_profile: 'var(--app-primary)', // @theme-ok brand/role/state identifier
    first_ai_session: 'var(--app-primary)', // @theme-ok brand/role/state identifier
    set_goal: 'var(--app-warning)', // @theme-ok brand/role/state identifier
    explore_tools: 'var(--app-success)', // @theme-ok brand/role/state identifier
    complete_tour: 'var(--app-primary)', // @theme-ok brand/role/state identifier
  };

  return (
    <div
      className="cl-widget"
      data-testid="getting-started-checklist"
      style={{
        margin: isDesktop ? '0 40px 24px' : '0 20px 24px',
        padding: 24,
        borderRadius: 20,
        background: allDone && celebrating
          ? `linear-gradient(135deg, ${colors.successSoft} 0%, ${colors.primarySoft} 100%)`
          : colors.card,
        border: `1px solid ${allDone ? colors.success : colors.border}`,
        boxShadow: darkMode ? 'none' : '0 12px 30px rgba(15,23,42,0.08)',
        animation: celebrating ? 'cl-celebrate .6s ease' : undefined,
        transition: 'border-color .3s ease, background .3s ease',
      } as any}
    >
      <div style={{ display: 'flex', alignItems: isDesktop ? 'center' : 'flex-start', gap: 20, flexDirection: isDesktop ? 'row' : 'column' } as any}>
        {/* Progress Ring */}
        <div data-testid="checklist-progress-ring" style={{ position: 'relative', flexShrink: 0, width: 88, height: 88, alignSelf: isDesktop ? 'flex-start' : 'center' } as any}>
          <svg width="88" height="88" viewBox="0 0 88 88" style={{ transform: 'rotate(-90deg)' }}>
            {/* Background ring */}
            <circle cx="44" cy="44" r={ringR} fill="none" stroke={colors.border} strokeWidth="5" />
            {/* Progress ring */}
            <circle
              cx="44" cy="44" r={ringR} fill="none"
              stroke={allDone ? colors.success : colors.primary}
              strokeWidth="5"
              strokeLinecap="round"
              strokeDasharray={ringC}
              strokeDashoffset={ringOffset}
              style={{ transition: 'stroke-dashoffset 0.6s cubic-bezier(0.4, 0, 0.2, 1), stroke 0.3s ease' } as any}
            />
          </svg>
          {/* Center text */}
          <div style={{
            position: 'absolute', inset: 0,
            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          } as any}>
            <span style={{
              color: allDone ? colors.success : colors.text,
              fontSize: 22, fontWeight: 900, letterSpacing: -1,
              fontFamily: "'Inter', system-ui, sans-serif",
            } as any}>{percent}%</span>
            {allDone && (
              <Ionicons name="checkmark-circle" size={14} color={colors.successText} />
            )}
          </div>
        </div>

        {/* Content */}
        <div style={{ flex: 1, width: '100%' } as any}>
          {/* Header */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 } as any}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 } as any}>
              <span style={{
                color: colors.text, fontSize: 16, fontWeight: 800, letterSpacing: -0.3,
                fontFamily: "'Inter', system-ui, sans-serif",
              } as any}>
                {allDone ? t('home.checklist.allDone') : t('home.checklist.title')}
              </span>
              {!allDone && (
                <span style={{
                  color: colors.textMuted, fontSize: 12, fontWeight: 600,
                  padding: '2px 8px', borderRadius: 6,
                  background: colors.bgSoft,
                } as any}>{completedCount}/{total}</span>
              )}
            </div>
          </div>
          <div style={{
            color: colors.textMuted, fontSize: 13, lineHeight: '20px', marginBottom: 16,
            fontFamily: "'Inter', system-ui, sans-serif",
          } as any}>
            {allDone
              ? t('home.checklist.allDoneDesc')
              : t('home.checklist.desc')}
          </div>

          {/* Checklist items */}
          {!allDone && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 } as any}>
              {items.map((item) => {
                const icon = ITEM_ICONS[item.id] || 'ellipse-outline';
                const color = ITEM_COLORS[item.id] || colors.primary;
                const isJust = justCompleted === item.id;
                const isStartHere = !item.completed && item.id === firstIncompleteId;
                return (
                  <div
                    key={item.id}
                    className="cl-item"
                    data-testid={`checklist-item-${item.id}`}
                    onClick={() => handleItemClick(item)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 12,
                      padding: '10px 14px', borderRadius: 12,
                      background: darkMode ? colors.surface : colors.bgSoft,
                      border: isStartHere ? `1px solid ${colors.primary}45` : '1px solid transparent',
                    } as any}
                  >
                    {/* Check circle */}
                    <div style={{
                      width: 28, height: 28, borderRadius: 8, flexShrink: 0,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      background: item.completed ? `${color}20` : (darkMode ? colors.cardMuted : colors.card),
                      border: `1.5px solid ${item.completed ? color : colors.border}`,
                      transition: 'all .3s ease',
                      animation: isJust ? 'cl-check-pop .4s cubic-bezier(.34,1.56,.64,1)' : undefined,
                    } as any}>
                      {item.completed ? (
                        <Ionicons name="checkmark" size={14} color={color} />
                      ) : (
                        <Ionicons name={icon as any} size={13} color={isStartHere ? colors.primary : colors.textMuted} />
                      )}
                    </div>
                    {/* Label */}
                    <span style={{
                      flex: 1, fontSize: 14, fontWeight: 600,
                      color: item.completed ? colors.textMuted : colors.textSecondary,
                      textDecoration: item.completed ? 'line-through' : 'none',
                      transition: 'color .3s ease',
                      fontFamily: "'Inter', system-ui, sans-serif",
                    } as any}>{tx(`home.checklist.item.${item.id}`, item.label)}</span>
                    {isStartHere && (
                      <span className="cl-start-here" data-testid="checklist-start-here" style={{
                        display: 'inline-flex', alignItems: 'center', gap: 4,
                        padding: '3px 10px', borderRadius: 999, flexShrink: 0,
                        background: `${colors.primary}16`, border: `1px solid ${colors.primary}35`,
                        color: colors.primary, fontSize: 10, fontWeight: 800, letterSpacing: 0.5, textTransform: 'uppercase',
                      } as any}>
                        <Ionicons name="play" size={9} color={colors.primary} />
                        {tx('home.checklist.startHere', 'Start here')}
                      </span>
                    )}
                    {!item.completed && (
                      <span data-testid={`checklist-eta-${item.id}`} style={{
                        color: colors.textMuted, fontSize: 10, fontWeight: 700, flexShrink: 0,
                        padding: '2px 8px', borderRadius: 999, background: darkMode ? colors.cardMuted : colors.card,
                        border: `1px solid ${colors.border}`,
                      } as any}>{tx('home.checklist.eta', '~2 min')}</span>
                    )}
                    {/* Arrow */}
                    {!item.completed && (
                      <Ionicons name="chevron-forward" size={14} color={colors.textMuted} />
                    )}
                  </div>
                );
              })}
              <div data-testid="checklist-reward-hint" style={{
                display: 'flex', alignItems: 'center', gap: 8, marginTop: 4,
                padding: '9px 14px', borderRadius: 12,
                background: `${colors.warning}0F`, border: `1px dashed ${colors.warning}40`,
              } as any}>
                <Ionicons name="trophy" size={13} color={colors.warningText} />
                <span style={{ color: colors.warningText, fontSize: 11.5, fontWeight: 700, fontFamily: "'Inter', system-ui, sans-serif" } as any}>
                  {tx('home.checklist.rewardHint', 'Completing all steps unlocks the Champion badge')}
                </span>
              </div>
            </div>
          )}

          {/* All done - dismiss button */}
          {allDone && !celebrating && (
            <div
              className="cl-dismiss-btn"
              data-testid="checklist-dismiss-btn"
              onClick={handleDismiss}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 8,
                padding: '12px 24px', borderRadius: 12, cursor: 'pointer',
                background: `linear-gradient(135deg, ${colors.success} 0%, ${colors.primary} 100%)`,
                boxShadow: `0 4px 12px ${colors.primary}40`,
              } as any}
            >
              <span style={{ color: colors.primaryText, fontSize: 14, fontWeight: 700 } as any}>{t('home.checklist.dismiss')}</span>
              <Ionicons name="arrow-forward" size={14} color={colors.primaryText} />
            </div>
          )}

          {/* Celebrating animation */}
          {celebrating && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: 8, padding: 12 } as any}>
              {[colors.primary, colors.success, colors.warning, colors.accent, colors.indigo].map((c, i) => (
                <div key={i} style={{
                  width: 8, height: 8, borderRadius: '50%', backgroundColor: c,
                  animation: `cl-confetti .8s ease ${i * 0.1}s both`,
                } as any} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
