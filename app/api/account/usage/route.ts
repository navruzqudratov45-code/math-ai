import { NextRequest, NextResponse } from 'next/server';
import { dbCall, requireRequestUser } from '../../../../lib/auth';
export async function GET(request: NextRequest) {
  const user = await requireRequestUser(request); if (!user) return NextResponse.json({ error: 'Tizimga kiring.' }, { status: 401 });
  return NextResponse.json(await dbCall({ op: 'usage', userId: user.id }));
}
