import { NextRequest, NextResponse } from 'next/server';
import { clearSessionCookie, dbCall, hashSessionToken, originIsAllowed, SESSION_COOKIE } from '../../../../lib/auth';
export async function POST(request: NextRequest) {
  if (!originIsAllowed(request)) return NextResponse.json({ error: 'So‘rov manbasi tekshiruvdan o‘tmadi.' }, { status: 403 });
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (token) { try { await dbCall({ op: 'logout', tokenHash: hashSessionToken(token) }); } catch (cause) { console.error('Logout session revoke failed:', cause instanceof Error ? cause.message : 'unknown error'); } }
  const response = NextResponse.json({ ok: true }); clearSessionCookie(response); return response;
}
