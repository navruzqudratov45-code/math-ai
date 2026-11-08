import { redirect } from 'next/navigation';
import { getCurrentUser } from '../../lib/auth';
import DashboardClient from './dashboard-client';
export const dynamic = 'force-dynamic';
export default async function DashboardPage() {
  const user = await getCurrentUser(); if (!user) redirect('/login?next=/dashboard');
  return <DashboardClient initialUser={user}/>;
}
