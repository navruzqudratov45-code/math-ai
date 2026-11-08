import { NextRequest, NextResponse } from 'next/server';
import { dbCall, originIsAllowed, readJson, requireRequestUser, type User } from '../../../../lib/auth';
export async function PATCH(request: NextRequest) {
  if (!originIsAllowed(request)) return NextResponse.json({ error: 'So‘rov manbasi tekshiruvdan o‘tmadi.' }, { status: 403 });
  if (Number(request.headers.get('content-length') ?? 0) > 4096) return NextResponse.json({ error: 'So‘rov hajmi juda katta.' }, { status: 413 });
  const user = await requireRequestUser(request); if (!user) return NextResponse.json({ error: 'Tizimga kiring.' }, { status: 401 });
  let data: { name?: unknown }; try { data = await readJson(request); } catch (cause) { return NextResponse.json({ error: (cause as Error).message }, { status: (cause as {status?:number}).status ?? 400 }); }
  if (typeof data.name !== 'string') return NextResponse.json({ error: 'Ism noto‘g‘ri.' }, { status: 400 });
  try { return NextResponse.json({ user: await dbCall<User>({ op: 'profile', userId: user.id, name: data.name }) }); }
  catch (cause) { return NextResponse.json({ error: (cause as Error).message }, { status: 400 }); }
}
