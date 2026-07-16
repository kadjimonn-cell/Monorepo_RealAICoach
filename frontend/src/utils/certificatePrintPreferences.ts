import AsyncStorage from '@react-native-async-storage/async-storage';

import api from '../services/api';
import { normalizeCertificatePrintLayout } from './certificatePrint';

const CERTIFICATE_PRINT_LAYOUT_KEY = 'certificate_print_layout_preference';

export const getLocalCertificatePrintLayoutPreference = async () => {
  try {
    const stored = await AsyncStorage.getItem(CERTIFICATE_PRINT_LAYOUT_KEY);
    return normalizeCertificatePrintLayout(stored);
  } catch {
    return 'portrait';
  }
};

export const setLocalCertificatePrintLayoutPreference = async (layout) => {
  const normalized = normalizeCertificatePrintLayout(layout);
  try {
    await AsyncStorage.setItem(CERTIFICATE_PRINT_LAYOUT_KEY, normalized);
  } catch {
    return normalized;
  }
  return normalized;
};

export const fetchCertificatePrintLayoutPreference = async () => {
  try {
    const { data } = await api.get('/ai-learn/certificates/print-layout-preference');
    const normalized = normalizeCertificatePrintLayout(data?.layout);
    await setLocalCertificatePrintLayoutPreference(normalized);
    return normalized;
  } catch {
    return null;
  }
};

export const saveCertificatePrintLayoutPreference = async (layout) => {
  const normalized = await setLocalCertificatePrintLayoutPreference(layout);
  try {
    await api.put('/ai-learn/certificates/print-layout-preference', { layout: normalized });
  } catch {
    return normalized;
  }
  return normalized;
};