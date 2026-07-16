import React from 'react';
import { Redirect } from 'expo-router';
import { useAuth } from '../src/context/AuthContext';
import { useTranslation } from '../src/hooks/useTranslation';
import ContentLibraryScreen from '../src/components/pages/ContentLibraryEnterprise';

// Top-level route: /content-library
// Renders the Library screen directly for authenticated users.
// Unauthenticated users are redirected to login with return_to.
export default function ContentLibraryRoute() {
  const { t } = useTranslation();
  t('i18n.route.content-library.probe');
  const { isAuthenticated, loading } = useAuth();

  if (loading) return null;

  if (!isAuthenticated) {
    return <Redirect href="/welcome?return_to=%2Fcontent-library&auth_reason=unauthenticated" />;
  }

  // Render the Library screen directly instead of redirecting
  return <ContentLibraryScreen />;
}
