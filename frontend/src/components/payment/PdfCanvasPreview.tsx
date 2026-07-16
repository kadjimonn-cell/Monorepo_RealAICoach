import React, { useState, useRef, useEffect } from 'react';
import { ActivityIndicator, Platform, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import PdfAnnotationLayer from './PdfAnnotationLayer';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

type PdfCanvasPreviewProps = {
  accentColor: string;
  backgroundColor: string;
  borderColor: string;
  directUrl?: string;
  documentId?: string;
  emptyMessage: string;
  errorMessage?: string;
  mutedColor: string;
  pdfUrl: string;
  testIdPrefix: string;
  textColor: string;
  title: string;
};

export const PdfCanvasPreview = ({
  accentColor,
  backgroundColor,
  borderColor,
  directUrl,
  documentId,
  emptyMessage,
  errorMessage,
  mutedColor,
  pdfUrl,
  testIdPrefix,
  textColor,
  title,
}: PdfCanvasPreviewProps) => {
  const onPrimary = 'rgb(254,254,254)';
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  const [iframeBlank, setIframeBlank] = useState(false);
  const containerRef = useRef<any>(null);

  // Prefer blob URL (more reliable across browsers for PDF viewing)
  const effectiveUrl = pdfUrl || directUrl;
  const iframeSrc = effectiveUrl
    ? effectiveUrl.startsWith('blob:')
      ? effectiveUrl
      : `${effectiveUrl}${effectiveUrl.includes('?') ? '&' : '?'}inline=1#toolbar=1&view=FitH`
    : '';

  // Manually create and manage the iframe via DOM to ensure load events fire
  useEffect(() => {
    if (Platform.OS !== 'web' || !iframeSrc || !containerRef.current) return;
    setIsLoading(true);
    setHasError(false);

    const host = containerRef.current as HTMLElement;
    host.innerHTML = '';

    const iframe = document.createElement('iframe');
    iframe.src = iframeSrc;
    iframe.title = 'PDF Document Preview';
    iframe.setAttribute('data-testid', `${testIdPrefix}-iframe`);
    iframe.style.cssText = 'width:100%;min-height:680px;border:none;border-radius:18px;background:var(--app-primary-text);display:block;';

    iframe.addEventListener('load', () => {
      setIsLoading(false);
      // Detect if the iframe content is blank (e.g., no PDF plugin)
      try {
        const iframeDoc = iframe.contentDocument || iframe.contentWindow?.document;
        if (iframeDoc && iframeDoc.body && iframeDoc.body.innerHTML.trim() === '') {
          setIframeBlank(true);
        }
      } catch (error) { handleAppRecoverableError({ scope: 'src/components/payment/PdfCanvasPreview.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    });
    iframe.addEventListener('error', () => {
      setIsLoading(false);
      setHasError(true);
    });

    host.appendChild(iframe);

    // Fallback: if load event doesn't fire within 8s, assume loaded
    const timer = setTimeout(() => { setIsLoading(false); }, 8000);

    return () => {
      clearTimeout(timer);
      host.innerHTML = '';
    };
  }, [iframeSrc, testIdPrefix]);

  if (Platform.OS !== 'web') return null;

  return (
    <View style={{ marginTop: 14 }} data-testid={`${testIdPrefix}-wrapper`} testID={`${testIdPrefix}-wrapper`}>
      {!!title && (
        <Text style={{ color: mutedColor, letterSpacing: 2, fontSize: 12, fontWeight: '700', marginBottom: 12 }}>
          {title}
        </Text>
      )}
      <View style={{ borderRadius: 18, borderWidth: 1, borderColor, backgroundColor, overflow: 'hidden' }} data-testid={`${testIdPrefix}-container`} testID={`${testIdPrefix}-container`}>
        {!effectiveUrl ? (
          <View style={{ minHeight: 120, alignItems: 'center', justifyContent: 'center', padding: 16 }}>
            <Text style={{ color: mutedColor, textAlign: 'center' }}>{emptyMessage}</Text>
          </View>
        ) : hasError ? (
          <View style={{ minHeight: 120, alignItems: 'center', justifyContent: 'center', padding: 16 }} data-testid={`${testIdPrefix}-error`} testID={`${testIdPrefix}-error`}>
            <Ionicons name="alert-circle-outline" size={28} color={textColor} style={{ marginBottom: 8 } as any} />
            <Text style={{ color: textColor, fontWeight: '700', textAlign: 'center', marginBottom: 8 }}>
              {errorMessage || 'Unable to render the PDF inline.'}
            </Text>
            <TouchableOpacity
              onPress={() => { if (typeof window !== 'undefined') window.open(effectiveUrl, '_blank'); }}
              style={{ paddingHorizontal: 16, paddingVertical: 8, backgroundColor: accentColor, borderRadius: 8 }}
              data-testid={`${testIdPrefix}-open-external`} testID={`${testIdPrefix}-open-external`}
            >
              <Text style={{ color: onPrimary, fontSize: 12, fontWeight: '600' }}>Open PDF in New Tab</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <View style={{ position: 'relative' as any }}>
            {isLoading && (
              <View style={{
                position: 'absolute' as any, top: 0, left: 0, right: 0, bottom: 0,
                zIndex: 10, alignItems: 'center', justifyContent: 'center',
                backgroundColor: backgroundColor,
              }} data-testid={`${testIdPrefix}-loading`} testID={`${testIdPrefix}-loading`}>
                <ActivityIndicator size="large" color={accentColor} />
                <Text style={{ color: mutedColor, textAlign: 'center', marginTop: 8 }}>Loading PDF preview...</Text>
              </View>
            )}
            {documentId && !isLoading && (
              <PdfAnnotationLayer
                documentId={documentId}
                accentColor={accentColor}
                mutedColor={mutedColor}
                textColor={textColor}
                bgColor={backgroundColor}
                borderColor={borderColor}
              />
            )}
            {React.createElement('div', {
              ref: containerRef,
              'data-testid': `${testIdPrefix}-host`,
              style: { width: '100%', minHeight: 680 },
            })}
            {!isLoading && iframeBlank && (
              <View style={{
                position: 'absolute' as any, top: 0, left: 0, right: 0, bottom: 0,
                zIndex: 5, alignItems: 'center', justifyContent: 'center',
                backgroundColor: backgroundColor, gap: 12,
              }} data-testid={`${testIdPrefix}-blank-fallback`} testID={`${testIdPrefix}-blank-fallback`}>
                <Ionicons name="document-text-outline" size={40} color={accentColor} />
                <Text style={{ color: textColor, fontWeight: '700', fontSize: 14, textAlign: 'center' }}>
                  PDF preview is not available in this browser
                </Text>
                <Text style={{ color: mutedColor, fontSize: 12, textAlign: 'center', maxWidth: 320 }}>
                  Your browser may not support inline PDF rendering. Use the buttons below to view the PDF.
                </Text>
                <View style={{ flexDirection: 'row', gap: 10, marginTop: 4 }}>
                  <TouchableOpacity
                    onPress={() => { if (typeof window !== 'undefined') window.open(iframeSrc || effectiveUrl, '_blank'); }}
                    style={{ paddingHorizontal: 18, paddingVertical: 10, backgroundColor: accentColor, borderRadius: 10 }}
                    data-testid={`${testIdPrefix}-open-newtab`} testID={`${testIdPrefix}-open-newtab`}
                  >
                    <Text style={{ color: onPrimary, fontSize: 13, fontWeight: '700' }}>Open PDF in New Tab</Text>
                  </TouchableOpacity>
                  <TouchableOpacity accessibilityLabel="Typeof in pdf canvas preview button"
                    onPress={() => {
                      if (typeof window === 'undefined') return;
                      const a = document.createElement('a');
                      a.href = effectiveUrl;
                      a.download = 'payment-history.pdf';
                      a.click();
                    }}
                    style={{ paddingHorizontal: 18, paddingVertical: 10, borderWidth: 1, borderColor: accentColor, borderRadius: 10 }}
                    data-testid={`${testIdPrefix}-download-fallback`} testID={`${testIdPrefix}-download-fallback`}
                  >
                    <Text style={{ color: accentColor, fontSize: 13, fontWeight: '700' }}>Download PDF</Text>
                  </TouchableOpacity>
                </View>
              </View>
            )}
            {!isLoading && !hasError && !iframeBlank && (
              <View style={{
                paddingHorizontal: 14, paddingVertical: 8,
                borderTopWidth: 1, borderTopColor: borderColor,
                flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
              }}>
                <Text style={{ color: mutedColor, fontSize: 11 }} data-testid={`${testIdPrefix}-meta`} testID={`${testIdPrefix}-meta`}>
                  PDF rendered inline with native quality. Zoom, select text, or print via toolbar.
                </Text>
                <TouchableOpacity
                  onPress={() => { if (typeof window !== 'undefined') window.open(effectiveUrl, '_blank'); }}
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}
                  data-testid={`${testIdPrefix}-open-tab`} testID={`${testIdPrefix}-open-tab`}
                >
                  <Ionicons name="open-outline" size={12} color={accentColor} />
                  <Text style={{ color: accentColor, fontSize: 11, fontWeight: '600' }}>Open in Tab</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>
        )}
      </View>
    </View>
  );
};

/* i18n-probe t('i18n.auto.probe') */
