export const revokeObjectUrl = (objectUrl?: string) => {
  if (typeof window === 'undefined' || !objectUrl) return;
  window.URL.revokeObjectURL(objectUrl);
};

export const fetchPdfAsset = async ({ fallbackFilename, token, url }: { fallbackFilename: string; token?: string; url: string }) => {
  const response = await fetch(url, {
    method: 'GET',
    headers: {
      Accept: 'application/pdf',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`PDF request failed (${response.status})`);
  }

  const blob = await response.blob();
  const pdfBlob = blob.type === 'application/pdf' ? blob : new Blob([blob], { type: 'application/pdf' });
  const objectUrl = window.URL.createObjectURL(pdfBlob);
  const disposition = response.headers.get('content-disposition') || '';
  const filenameMatch = disposition.match(/filename\*?=(?:UTF-8''|"?)([^";]+)/i);

  return {
    blob,
    filename: filenameMatch?.[1] ? decodeURIComponent(filenameMatch[1].replace(/"/g, '').trim()) : fallbackFilename,
    objectUrl,
  };
};

export const saveBlobWithBrowserFallback = async ({ blob, filename }: { blob: Blob; filename: string }) => {
  const anyWindow = window as any;
  if (typeof anyWindow.showSaveFilePicker === 'function') {
    const handle = await anyWindow.showSaveFilePicker({
      suggestedName: filename,
      types: [{ description: 'PDF file', accept: { 'application/pdf': ['.pdf'] } }],
    });
    const writable = await handle.createWritable();
    await writable.write(blob);
    await writable.close();
    return 'saved' as const;
  }

  const nav = navigator as any;
  const file = new File([blob], filename, { type: 'application/pdf' });
  if (nav.canShare?.({ files: [file] })) {
    await nav.share({ files: [file], title: filename });
    return 'shared' as const;
  }

  const objectUrl = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.rel = 'noopener';
  anchor.style.display = 'none';
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 60000);
  return 'downloaded' as const;
};