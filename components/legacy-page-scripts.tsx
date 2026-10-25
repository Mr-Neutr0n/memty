'use client';

import { useEffect } from 'react';

export type LegacyPageName = 'landing' | 'login' | 'chat';

const pageScripts: Record<LegacyPageName, string[]> = {
  landing: [
    '/legacy/landing-1.mjs',
    '/legacy/landing-2.js',
    '/legacy/landing-demo.js',
  ],
  login: [
    '/legacy/login-1.mjs',
    '/legacy/login-2.js',
  ],
  chat: [
    '/legacy/index-1.mjs',
  ],
};

export default function LegacyPageScripts({ page }: { page: LegacyPageName }) {
  useEffect(() => {
    const host = document.querySelector<HTMLElement>(`[data-legacy-page="${page}"]`);
    if (!host) return;

    const loaded: HTMLScriptElement[] = [];
    for (const src of pageScripts[page]) {
      const script = document.createElement('script');
      script.src = src;
      script.type = src.endsWith('.mjs') ? 'module' : 'text/javascript';
      script.defer = true;
      host.appendChild(script);
      loaded.push(script);
    }

    return () => loaded.forEach(script => script.remove());
  }, [page]);

  return null;
}
