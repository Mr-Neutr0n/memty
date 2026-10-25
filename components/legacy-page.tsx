import LegacyPageScripts, { type LegacyPageName } from './legacy-page-scripts';

type LegacyPageProps = { page: LegacyPageName; markup: string };

/**
 * Render the legacy HTML only on the server. Keeping the large markup string
 * out of a Client Component prevents server/client copies from drifting during
 * hydration (for example, while Next.js is rebuilding in development).
 */
export default function LegacyPage({ page, markup }: LegacyPageProps) {
  return <>
    <div
      data-legacy-page={page}
      className={`legacy-page legacy-page-${page} min-h-screen`}
      dangerouslySetInnerHTML={{ __html: markup }}
    />
    <LegacyPageScripts page={page} />
  </>;
}
