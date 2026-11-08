import { NextRequest, NextResponse } from 'next/server';
import { requireRequestUser } from '../../../../lib/auth';
export async function GET(request: NextRequest) {
  const user = await requireRequestUser(request);
  return user ? NextResponse.json({ user }) : NextResponse.json({ error: 'Tizimga kiring.' }, { status: 401 });
}
