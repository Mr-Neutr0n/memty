import LegacyPage from '@/components/legacy-page';
import { loginMarkup } from '@/lib/legacy-markup';

export const metadata = { title: "Memty — Sign In" };
export const dynamic = 'force-dynamic';

export default function Page() {
  return <LegacyPage page="login" markup={loginMarkup} />;
}
