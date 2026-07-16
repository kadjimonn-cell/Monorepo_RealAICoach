import React from 'react';
import { Platform } from 'react-native';
import { useTheme } from '../../../context/ThemeContext';

export const WebStyleInjector = () => {
  const { darkMode, colors } = useTheme();
  const T = {
    text: colors.text,
    text3: colors.textMuted,
    cyan: colors.accent,
    neonBlue: colors.primary,
  };

  if (Platform.OS !== 'web') return null;

  return (
    <div
      dangerouslySetInnerHTML={{
        __html: `<style>
@keyframes float { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-18px)} }
@keyframes drift { 0%{transform:translate(0,0)} 50%{transform:translate(25px,-15px)} 100%{transform:translate(0,0)} }
@keyframes pulse-glow { 0%,100%{opacity:.35;transform:scale(1)} 50%{opacity:.7;transform:scale(1.08)} }
@keyframes bar-grow { from{width:0%} }
@keyframes scan-line { 0%{top:0%} 100%{top:100%} }
@keyframes fadeSlideUp { from{opacity:0;transform:translateY(24px)} to{opacity:1;transform:translateY(0)} }
@keyframes border-trace { 0%{background-position:0% 50%} 50%{background-position:100% 50%} 100%{background-position:0% 50%} }
@keyframes counter-tick { 0%{opacity:0;transform:translateY(8px)} 100%{opacity:1;transform:translateY(0)} }
@keyframes shimmer { 0%{background-position:-200% 0} 100%{background-position:200% 0} }
.login-glass-card { animation: fadeSlideUp 0.7s ease-out both; }
.login-glass-card:hover { box-shadow: 0 0 60px rgba(0,240,255,0.06), 0 24px 80px rgba(0,0,0,0.4) !important; }
.login-input-web { background: transparent !important; color: ${T.text} !important; border: none !important; outline: none !important; box-shadow: none !important; -webkit-text-fill-color: ${T.text} !important; }
.login-input-web::placeholder { color: ${T.text3} !important; -webkit-text-fill-color: ${T.text3} !important; }
.login-input-web:focus { border-color: ${T.cyan} !important; box-shadow: 0 0 12px rgba(0,240,255,0.15); }
.login-input-web input { background: transparent !important; color: ${T.text} !important; }
.login-btn-primary { background: linear-gradient(135deg, ${T.cyan}, ${T.neonBlue}); transition: all 0.2s ease; }
.login-btn-primary:hover { filter: brightness(1.15); transform: scale(1.02); }
.login-btn-primary:active { transform: scale(0.98); }
.login-btn-social { transition: all 0.15s ease; }
.login-btn-social:hover { border-color: ${darkMode ? 'rgba(255,255,255,0.25)' : 'rgba(0,0,0,0.15)'} !important; background-color: ${darkMode ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.03)'} !important; }
.login-recovery-card-soft { background: ${darkMode ? 'rgba(10, 28, 48, 0.94)' : 'rgba(241, 245, 249, 0.94)'} !important; border-color: ${darkMode ? 'rgba(34,211,238,0.30)' : 'rgba(14,165,233,0.30)'} !important; }
.intel-bar { animation: bar-grow 1.2s ease-out both; }
.particle { animation: float 6s ease-in-out infinite; }
.particle-2 { animation: drift 8s ease-in-out infinite; }
.particle-3 { animation: pulse-glow 4s ease-in-out infinite; }
.scan-line { animation: scan-line 4s linear infinite; }
</style>`,
      }}
    />
  );
};

/* i18n-probe t('i18n.auto.probe') */
