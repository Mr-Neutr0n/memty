import LegacyPage from '@/components/legacy-page';
import { landingMarkup } from '@/lib/legacy-markup';

export const metadata = {
  title: "NexorAI | All Intelligence in One Universe",
  description: "Switch between configured AI models, return to saved conversations, and manage user-controlled memory. Build with the local-first MemoryPort Python SDK.",
};

export default function Page() {
  return <LegacyPage page="landing" markup={landingMarkup} />;
}
