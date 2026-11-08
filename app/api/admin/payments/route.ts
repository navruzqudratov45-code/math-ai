import { NextRequest, NextResponse } from 'next/server';
import { dbCall, requireRequestUser } from '../../../../lib/auth';

export async function GET(request: NextRequest) {
  const user = await requireRequestUser(request, 'admin');
  if (!user) return NextResponse.json({ error: 'Topilmadi.' }, { status: 404 });
  const provider = request.nextUrl.searchParams.get('provider');
  const status = request.nextUrl.searchParams.get('status');
  return NextResponse.json(await dbCall({ op: 'payment_admin_list', provider, status }));
}
