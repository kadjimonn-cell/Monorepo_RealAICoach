import React, { useMemo } from 'react';
import { Platform, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { withAlpha } from '../../utils/colorAlpha';

type ProofItem = {
  id: string;
  icon: string;
  label: string;
  value: string;
};

type WelcomeCapabilityProofRailProps = {
  colors: any;
  isDark: boolean;
  width: number;
  wideLayout: boolean;
  items: ProofItem[];
  title: string;
};

export function WelcomeCapabilityProofRail({ colors, isDark, width, wideLayout, items, title }: WelcomeCapabilityProofRailProps) {
  const s = useMemo(() => makeStyles(colors, isDark), [colors, isDark]);
  const renderWebMarquee = Platform.OS === 'web' && wideLayout;
  const compactGridColumns = width < 560 ? 1 : width < 980 ? 2 : 3;

  return (
    <View style={s.wrap} data-testid="welcome-capability-proof-rail" testID="welcome-capability-proof-rail">
      {renderWebMarquee ? (
        <style dangerouslySetInnerHTML={{ __html: `
          .capability-proof-track {
            display: flex;
            gap: 12px;
            min-width: max-content;
            animation: capability-proof-marquee 28s linear infinite;
            will-change: transform;
          }
          .capability-proof-track:hover {
            animation-play-state: paused;
          }
          @keyframes capability-proof-marquee {
            0% { transform: translateX(0); }
            100% { transform: translateX(-50%); }
          }
        ` }} />
      ) : null}

      <Text style={s.title} data-testid="welcome-capability-proof-title" testID="welcome-capability-proof-title">
        {title}
      </Text>

      {renderWebMarquee ? (
        <div style={{ overflow: 'hidden', width: '100%' }}>
          <div className="capability-proof-track" data-testid="welcome-capability-proof-marquee-track">
            {[...items, ...items].map((item, idx) => (
              <div
                key={`${item.id}-${idx}`}
                style={{
                  minWidth: 220,
                  borderRadius: 16,
                  border: `1px solid ${colors.border}`,
                  background: withAlpha(colors.surface, isDark ? 'E8' : 'F2'),
                  padding: '14px 16px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                }}
                data-testid={`welcome-capability-proof-item-${idx}`}
              >
                <div style={{ width: 36, height: 36, borderRadius: 12, background: withAlpha(colors.accent, '18'), border: `1px solid ${withAlpha(colors.accent, '30')}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name={item.icon as any} size={18} color={colors.accent} />
                </div>
                <div style={{ display: 'grid', gap: 2 }}>
                  <span style={{ color: colors.textMuted, fontSize: 10, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase' }}>{item.label}</span>
                  <span style={{ color: colors.text, fontSize: 13, fontWeight: 800 }}>{item.value}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : Platform.OS === 'web' ? (
        <div
          data-testid="welcome-capability-proof-static-grid"
          style={{
            display: 'grid',
            gridTemplateColumns: `repeat(${compactGridColumns}, minmax(0, 1fr))`,
            gap: '12px',
            width: '100%',
          }}
        >
          {items.map((item, idx) => (
            <div
              key={item.id}
              style={{
                minWidth: 0,
                borderRadius: 16,
                border: `1px solid ${colors.border}`,
                background: withAlpha(colors.surface, isDark ? 'E8' : 'F2'),
                padding: '14px 16px',
                display: 'flex',
                alignItems: 'center',
                gap: 12,
              }}
              data-testid={`welcome-capability-proof-item-${idx}`}
            >
              <div style={{ width: 36, height: 36, borderRadius: 12, background: withAlpha(colors.accent, '18'), border: `1px solid ${withAlpha(colors.accent, '30')}`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <Ionicons name={item.icon as any} size={18} color={colors.accent} />
              </div>
              <div style={{ display: 'grid', gap: 2, minWidth: 0 }}>
                <span style={{ color: colors.textMuted, fontSize: 10, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase' }}>{item.label}</span>
                <span style={{ color: colors.text, fontSize: 13, fontWeight: 800, lineHeight: 1.35 }}>{item.value}</span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <View style={s.nativeTrack}>
          {items.map((item, idx) => (
            <View key={item.id} style={s.nativeItem} data-testid={`welcome-capability-proof-item-${idx}`} testID={`welcome-capability-proof-item-${idx}`}>
              <View style={s.iconShell}><Ionicons name={item.icon as any} size={18} color={colors.accent} /></View>
              <View style={{ gap: 2, flex: 1 }}>
                <Text style={s.itemLabel}>{item.label}</Text>
                <Text style={s.itemValue}>{item.value}</Text>
              </View>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

function makeStyles(colors: any, isDark: boolean) {
  return StyleSheet.create({
    wrap: {
      borderRadius: 20,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: withAlpha(colors.surface, isDark ? 'F2' : 'F6'),
      padding: 18,
      gap: 12,
      overflow: 'hidden',
    },
    title: {
      color: colors.textMuted,
      fontSize: 11,
      fontWeight: '800',
      letterSpacing: 1.6,
      textTransform: 'uppercase',
    },
    nativeTrack: {
      gap: 10,
    },
    nativeItem: {
      borderRadius: 16,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: withAlpha(colors.surface, isDark ? 'E8' : 'F1'),
      padding: 14,
      flexDirection: 'row',
      alignItems: 'center',
      gap: 12,
    },
    iconShell: {
      width: 36,
      height: 36,
      borderRadius: 12,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: withAlpha(colors.accent, '18'),
      borderWidth: 1,
      borderColor: withAlpha(colors.accent, '30'),
    },
    itemLabel: {
      color: colors.textMuted,
      fontSize: 10,
      fontWeight: '800',
      letterSpacing: 1.2,
      textTransform: 'uppercase',
    },
    itemValue: {
      color: colors.text,
      fontSize: 13,
      fontWeight: '800',
    },
  });
}
