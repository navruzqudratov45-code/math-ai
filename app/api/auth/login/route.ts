import { NextRequest, NextResponse } from 'next/server';
import { authRateLimited, dbCall, hashSessionToken, newSessionToken, originIsAllowed, readJson, setSessionCookie, type User } from '../../../../lib/auth';
const fail = (message: string, status: number) => NextResponse.json({ error: message }, { status });
export async function POST(request: NextRequest) {
  if (!originIsAllowed(request)) return fail('So‘rov manbasi tekshiruvdan o‘tmadi.', 403);
  if (Number(request.headers.get('content-length') ?? 0) > 4096) return fail('So‘rov hajmi juda katta.', 413);
  const ip = request.headers.get('x-forwarded-for')?.split(',')[0]?.trim() || 'unknown';
  if (authRateLimited(`login:${ip}`, 10)) return fail('Ko‘p urinish bo‘ldi. 15 daqiqadan so‘ng qayta urinib ko‘ring.', 429);
  let data: Record<string, unknown>;
  try { data = await readJson(request); } catch (cause) { return fail((cause as Error).message, (cause as {status?:number}).status ?? 400); }
  if (typeof data.email !== 'string' || data.email.length > 254 || typeof data.password !== 'string' || data.password.length > 256) return fail('Email yoki parol noto‘g‘ri.', 400);
  const token = newSessionToken();
  try {
    const user = await dbCall<User>({ op: 'login', email: data.email, password: data.password, tokenHash: hashSessionToken(token), expiresAt: Math.floor(Date.now() / 1000) + 7 * 86400 });
    const response = NextResponse.json({ user }); setSessionCookie(response, token); return response;
  } catch (cause) {
    const kind = (cause as Error & { kind?: string }).kind;
    return fail(kind === 'permission' ? 'Email yoki parol noto‘g‘ri.' : kind === 'database' ? 'Hisobga kirib bo‘lmadi. Qayta urinib ko‘ring.' : (cause as Error).message, kind === 'permission' ? 401 : 500);
  }
}
