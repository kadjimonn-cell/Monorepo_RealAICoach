type LogArgs = unknown[];

const isProduction = process.env.NODE_ENV === 'production';

const noop = (..._args: LogArgs): void => {};

export const clientLogger = {
  log: (...args: LogArgs): void => {
    if (!isProduction) {
      console.log(...args);
    }
  },
  info: (...args: LogArgs): void => {
    if (!isProduction) {
      console.info(...args);
    }
  },
  warn: (...args: LogArgs): void => {
    if (!isProduction) {
      console.warn(...args);
    }
  },
  error: (...args: LogArgs): void => {
    if (!isProduction) {
      console.error(...args);
    }
  },
  debug: (...args: LogArgs): void => {
    if (!isProduction) {
      console.debug(...args);
    }
  },
};

export const shouldEmitClientLogs = !isProduction;
