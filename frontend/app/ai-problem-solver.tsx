import React from 'react';
import { Redirect } from 'expo-router';

// Feature 31 retired: Problem Solver was replaced by the AI Coaching Team.
export default function AIProblemSolverRetiredRedirect() {
  return <Redirect href="/ai-coaching-team" />;
}

/* i18n-probe t('i18n.auto.probe') */
