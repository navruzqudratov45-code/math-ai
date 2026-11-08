import { randomBytes } from 'node:crypto';
import { NextRequest, NextResponse } from 'next/server';
import { authRateLimited, dbCall, hashSessionToken, originIsAllowed, readJson } from '../../../../../lib/auth';
export async function POST(request: NextRequest) {
  if (!originIsAllowed(request)) return NextResponse.json({ error: 'So‘rov manbasi tekshiruvdan o‘tmadi.' }, { status: 403 });
  if (Number(request.headers.get('content-length') ?? 0) > 4096) return NextResponse.json({ error: 'So‘rov hajmi juda katta.' }, { status: 413 });
  const ip = request.headers.get('x-forwarded-for')?.split(',')[0]?.trim() || 'unknown';
  if (authRateLimited(`reset:${ip}`, 4)) return NextResponse.json({ error: 'Ko‘p urinish bo‘ldi. Keyinroq qayta urinib ko‘ring.' }, { status: 429 });
  let data: { email?: unknown }; try { data = await readJson(request); } catch (cause) { return NextResponse.json({ error: (cause as Error).message }, { status: (cause as {status?:number}).status ?? 400 }); }
  if (typeof data.email !== 'string' || data.email.length > 254) return NextResponse.json({ error: 'Email manzili noto‘g‘ri.' }, { status: 400 });
  const apiKey = process.env.RESEND_API_KEY, from = process.env.AUTH_FROM_EMAIL, appUrl = process.env.APP_URL;
  if (!apiKey || !from || !appUrl) {
    console.error('Password reset delivery is not configured:', JSON.stringify({ resendKeyPresent: !!apiKey, fromPresent: !!from, appUrlPresent: !!appUrl }));
    return NextResponse.json({ error: 'Parolni tiklash email xizmati sozlanmagan. Administrator bilan bog‘laning.' }, { status: 503 });
  }
  const token = randomBytes(32).toString('base64url');
  try {
    const created = await dbCall<boolean>({ op: 'create_reset', email: data.email, tokenHash: hashSessionToken(token), expiresAt: Math.floor(Date.now() / 1000) + 30 * 60 });
    if (created) {
      try {
        const response = await fetch('https://api.resend.com/emails', { method: 'POST', headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ from, to: [data.email], subject: 'MathAI parolini yangilash', text: `Parolni yangilash uchun 30 daqiqa ichida ushbu sahifani oching: ${appUrl.replace(/\/$/, '')}/reset-password?token=${token}` }), signal: AbortSignal.timeout(10_000) });
        if (!response.ok) console.error('Password reset email delivery failed:', JSON.stringify({ status: response.status }));
      } catch (cause) { console.error('Password reset email delivery failed:', JSON.stringify({ code: (cause as { cause?: { code?: string } }).cause?.code ?? (cause as Error).name })); }
    }
    return NextResponse.json({ message: 'Agar bu email hisobga tegishli bo‘lsa, parolni yangilash havolasi yuboriladi.' });
  } catch (cause) { console.error('Password reset request failed:', cause instanceof Error ? cause.message : 'unknown error'); return NextResponse.json({ error: 'So‘rov bajarilmadi. Qayta urinib ko‘ring.' }, { status: 500 }); }
}
