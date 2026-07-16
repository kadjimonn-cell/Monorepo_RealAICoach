export interface RecoverableErrorOptions {
  scope: string;
  fallbackMessage: string;
  setMessage?: (message: string) => void;
}

export const getRecoverableErrorMessage = (error: any, fallbackMessage: string) => (
  error?.response?.data?.detail
  || error?.message
  || fallbackMessage
);

export const handleRecoverableError = (error: any, options: RecoverableErrorOptions) => {
  const message = getRecoverableErrorMessage(error, options.fallbackMessage);
  console.warn(`[recoverable:${options.scope}]`, error);
  options.setMessage?.(message);
  return message;
};
