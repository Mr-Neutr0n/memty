import LegacyPage from '@/components/legacy-page';
import { landingMarkup } from '@/lib/legacy-markup';

export const metadata = { title: "NexorAI — One Universe. Every Intelligence." };

export default function Page() {
  return <LegacyPage page="landing" markup={landingMarkup} />;
}
