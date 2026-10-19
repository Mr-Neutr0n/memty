import type { Metadata } from 'next';
import MemoryDashboard from './memory-dashboard';

export const metadata: Metadata = { title: 'Your Memory | NexorAI', description: 'View and manage the portable memory NexorAI uses across models.' };

export default function MemoryPage() { return <MemoryDashboard />; }
