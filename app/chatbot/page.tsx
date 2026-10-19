import LegacyPage from '@/components/legacy-page';
import { indexMarkup } from '@/lib/legacy-markup';

export const metadata = { title: "NexorAI Workspace" };
export const dynamic = 'force-dynamic';

export default function Page() {
  return <LegacyPage page="chat" markup={indexMarkup} />;
}
