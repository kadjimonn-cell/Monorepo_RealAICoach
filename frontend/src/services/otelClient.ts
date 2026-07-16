import { WebTracerProvider } from '@opentelemetry/sdk-trace-web';
import { registerInstrumentations } from '@opentelemetry/instrumentation';
import { FetchInstrumentation } from '@opentelemetry/instrumentation-fetch';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

let initialized = false;

function resolveOtelHttpEndpoint(): string {
  const envEndpoint = String((process.env as any).REACT_APP_OTEL_EXPORTER_OTLP_HTTP || '').trim();
  if (envEndpoint) return envEndpoint;
  return '';
}

export function initializeBrowserObservability(): void {
  if (initialized) return;
  if (typeof window === 'undefined') return;

  try {
    const provider = new WebTracerProvider();
    const exporterEndpoint = resolveOtelHttpEndpoint();
    if (exporterEndpoint) {
      console.info('[otel] exporter endpoint configured; browser trace export is deferred to server bridge in web-runtime.');
    }

    provider.register();

    registerInstrumentations({
      instrumentations: [
        new FetchInstrumentation({
          propagateTraceHeaderCorsUrls: [],  // Security: Don't leak internal trace headers to external APIs
          clearTimingResources: true,
        }),
      ],
    });

    initialized = true;
  } catch (error) { handleAppRecoverableError({ scope: 'src/services/otelClient.ts#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
}
