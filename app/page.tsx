import LegacyPage from '@/components/legacy-page';
import { landingMarkup } from '@/lib/legacy-markup';

export const metadata = { title: 'NexorAI | All Intelligence in One Universe' };

export default function Page() {
  return <LegacyPage page="landing" markup={landingMarkup} />;
}
