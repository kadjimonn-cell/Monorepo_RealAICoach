/**
 * Explicit admin deep-link shortcut for Talent Network operations.
 *
 * Intended for QA/Ops use:
 *   /talent-network-admin
 *
 * This alias forwards to the canonical admin deep-link route.
 */
import React from 'react';
import { Redirect } from 'expo-router';
import { AdminRouteGate } from '../src/components/auth/AdminRouteGate';

export default function TalentNetworkAdminShortcutRoute() {
  return (
    <AdminRouteGate returnTo="/talent-network-admin">
      <Redirect href="/admin/talent-network" />
    </AdminRouteGate>
  );
}
