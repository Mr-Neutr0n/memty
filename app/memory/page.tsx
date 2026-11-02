import type { Metadata } from 'next';
import MemoryDashboard from './memory-dashboard';

export const metadata: Metadata = { title: 'Your Memory | Memty', description: 'View and manage the portable memory Memty uses across models.' };

export default function MemoryPage() { return <MemoryDashboard />; }
