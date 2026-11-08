import { NextRequest, NextResponse } from 'next/server';
import { authRateLimited, dbCall, hashSessionToken, originIsAllowed, readJson, requireRequestUser, SESSION_COOKIE } from '../../../../../lib/auth';
export async function POST(request: NextRequest) {
  if (!originIsAllowed(request)) return NextResponse.json({ error: 'So‘rov manbasi tekshiruvdan o‘tmadi.' }, { status: 403 });
  const user = await requireRequestUser(request); if (!user) return NextResponse.json({ error: 'Tizimga kiring.' }, { status: 401 });
  if (Number(request.headers.get('content-length') ?? 0) > 4096) return NextResponse.json({ error: 'So‘rov hajmi juda katta.' }, { status: 413 });
  if (authRateLimited(`password-change:${user.id}`, 5)) return NextResponse.json({ error: 'Ko‘p urinish bo‘ldi. Keyinroq qayta urinib ko‘ring.' }, { status: 429 });
  let data: Record<string, unknown>; try { data = await readJson(request); } catch (cause) { return NextResponse.json({ error: (cause as Error).message }, { status: (cause as {status?:number}).status ?? 400 }); }
  if (typeof data.currentPassword !== 'string' || data.currentPassword.length > 256 || typeof data.newPassword !== 'string' || data.newPassword.length > 256) return NextResponse.json({ error: 'Parollar noto‘g‘ri.' }, { status: 400 });
  try { const token = request.cookies.get(SESSION_COOKIE)?.value ?? ''; await dbCall({ op: 'change_password', userId: user.id, currentPassword: data.currentPassword, newPassword: data.newPassword, currentTokenHash: hashSessionToken(token) }); return NextResponse.json({ ok: true }); }
  catch (cause) { const e = cause as Error & { kind?: string }; return NextResponse.json({ error: e.message }, { status: e.kind === 'permission' ? 403 : 400 }); }
}
