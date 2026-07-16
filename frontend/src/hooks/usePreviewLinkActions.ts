import { useRef, useState } from 'react';
import { Platform } from 'react-native';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

type UsePreviewLinkActionsOptions = {
  copyFailureMessage: string;
  copySuccessMessage: string;
  manualUrl: string;
  selectMessage: string;
};

export const usePreviewLinkActions = ({
  copyFailureMessage,
  copySuccessMessage,
  manualUrl,
  selectMessage,
}: UsePreviewLinkActionsOptions) => {
  const [actionNotice, setActionNotice] = useState('');
  const manualLinkInputRef = useRef<any>(null);

  const copyManualLink = async () => {
    if (Platform.OS !== 'web') return;
    try {
      await navigator.clipboard.writeText(manualUrl);
      setActionNotice(copySuccessMessage);
    } catch {
      setActionNotice(copyFailureMessage);
    }
  };

  const selectManualLink = () => {
    if (Platform.OS !== 'web') return;
    setActionNotice(selectMessage);
    window.setTimeout(() => {
      try {
        manualLinkInputRef.current?.focus?.();
        manualLinkInputRef.current?.select?.();
        manualLinkInputRef.current?.setSelectionRange?.(0, manualUrl.length);
      } catch (error) { handleAppRecoverableError({ scope: 'src/hooks/usePreviewLinkActions.ts#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    }, 50);
  };

  return {
    actionNotice,
    copyManualLink,
    manualLinkInputRef,
    selectManualLink,
    setActionNotice,
  };
};