import { NextRequest, NextResponse } from 'next/server';
import { dbCall, hashSessionToken, originIsAllowed, readJson } from '../../../../../lib/auth';
export async function POST(request: NextRequest) {
  if (!originIsAllowed(request)) return NextResponse.json({ error: 'So‘rov manbasi tekshiruvdan o‘tmadi.' }, { status: 403 });
  if (Number(request.headers.get('content-length') ?? 0) > 4096) return NextResponse.json({ error: 'So‘rov hajmi juda katta.' }, { status: 413 });
  let data: Record<string, unknown>; try { data = await readJson(request); } catch (cause) { return NextResponse.json({ error: (cause as Error).message }, { status: (cause as {status?:number}).status ?? 400 }); }
  if (typeof data.token !== 'string' || typeof data.password !== 'string' || data.token.length > 128 || data.password.length > 256) return NextResponse.json({ error: 'Havola yoki parol yaroqsiz.' }, { status: 400 });
  try { await dbCall({ op: 'reset_password', tokenHash: hashSessionToken(data.token), password: data.password }); return NextResponse.json({ ok: true }); }
  catch (cause) { return NextResponse.json({ error: (cause as Error).message }, { status: 400 }); }
}
