import { NextRequest, NextResponse } from 'next/server';
import { authRateLimited, dbCall, hashSessionToken, newSessionToken, originIsAllowed, readJson, setSessionCookie, type User } from '../../../../lib/auth';
const fail = (message: string, status: number) => NextResponse.json({ error: message }, { status });
export async function POST(request: NextRequest) {
  if (!originIsAllowed(request)) return fail('So‘rov manbasi tekshiruvdan o‘tmadi.', 403);
  if (Number(request.headers.get('content-length') ?? 0) > 4096) return fail('So‘rov hajmi juda katta.', 413);
  const ip = request.headers.get('x-forwarded-for')?.split(',')[0]?.trim() || 'unknown';
  if (authRateLimited(`register:${ip}`, 5)) return fail('Ko‘p urinish bo‘ldi. Keyinroq qayta urinib ko‘ring.', 429);
  let data: Record<string, unknown>;
  try { data = await readJson(request); } catch (cause) { return fail((cause as Error).message, (cause as {status?:number}).status ?? 400); }
  if (typeof data.email !== 'string' || data.email.length > 254 || typeof data.name !== 'string' || data.name.length > 80 || typeof data.password !== 'string' || data.password.length > 256) return fail('Ism, email yoki parol noto‘g‘ri.', 400);
  try {
    const settings = await dbCall<{ registrationEnabled: boolean }>({ op: 'settings' });
    if (!settings.registrationEnabled) return fail('Hozirda yangi ro‘yxatdan o‘tish yopiq.', 403);
    const user = await dbCall<User>({ op: 'register', email: data.email, name: data.name, password: data.password });
    const token = newSessionToken();
    await dbCall({ op: 'register_session', userId: user.id, tokenHash: hashSessionToken(token), expiresAt: Math.floor(Date.now() / 1000) + 7 * 86400 });
    const response = NextResponse.json({ user }, { status: 201 }); setSessionCookie(response, token); return response;
  } catch (cause) {
    const kind = (cause as Error & { kind?: string }).kind;
    return fail(cause instanceof Error ? cause.message : 'Hisob yaratilmadi.', kind === 'validation' ? 400 : kind === 'permission' ? 409 : 500);
  }
}
