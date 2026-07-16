import { Redirect } from 'expo-router';

// Feature 26 replacement: the legacy Jobs Portal route now redirects to Job Search.
export default function JobPlatformRedirect() {
  return <Redirect href="/job-search" />;
}
