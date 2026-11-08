import { notFound } from 'next/navigation';
import { getCurrentUser, isOwnerAdmin } from '../../lib/auth';
import AdminClient from './admin-client';
export const dynamic = 'force-dynamic';
export default async function AdminPage() {
  const user = await getCurrentUser(); if (!isOwnerAdmin(user)) notFound();
  return <AdminClient administrator={user}/>;
}
