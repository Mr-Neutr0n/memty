'use client';

import { useEffect } from 'react';

type LegacyPageName = 'landing' | 'login' | 'chat';
type LegacyPageProps = { page: LegacyPageName; markup: string };

const pageScripts: Record<LegacyPageName, string[]> = {
  "landing": [
    "/legacy/landing-1.mjs",
    "/legacy/landing-2.js"
  ],
  "login": [
    "/legacy/login-1.mjs",
    "/legacy/login-2.js"
  ],
  "chat": [
    "/legacy/index-1.mjs"
  ]
};

export default function LegacyPage({ page, markup }: LegacyPageProps) {
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

  return <div data-legacy-page={page} className={`legacy-page legacy-page-${page} min-h-screen`} dangerouslySetInnerHTML={{ __html: markup }} />;
}
