import { NextRequest, NextResponse } from 'next/server';
import { dbCall, originIsAllowed, readJson, requireRequestUser } from '../../../../lib/auth';
export async function GET(request: NextRequest) {
  const user = await requireRequestUser(request, 'admin');
  if (!user) return NextResponse.json({ error: 'Topilmadi.' }, { status: 404 });
  return NextResponse.json({ users: await dbCall({ op: 'list_users' }) });
}
export async function PATCH(request: NextRequest) {
  if (!originIsAllowed(request)) return NextResponse.json({ error: 'So‘rov manbasi tekshiruvdan o‘tmadi.' }, { status: 403 });
  const user = await requireRequestUser(request, 'admin');
  if (!user) return NextResponse.json({ error: 'Topilmadi.' }, { status: 404 });
  if (Number(request.headers.get('content-length') ?? 0) > 4096) return NextResponse.json({ error: 'So‘rov hajmi juda katta.' }, { status: 413 });
  let data: Record<string, unknown>; try { data = await readJson(request); } catch (cause) { return NextResponse.json({ error: (cause as Error).message }, { status: (cause as {status?:number}).status ?? 400 }); }
  if (!Number.isSafeInteger(data.userId) || typeof data.value !== 'string') return NextResponse.json({ error: 'Yangilash ma’lumoti noto‘g‘ri.' }, { status: 400 });
  const field = data.field;
  const accepted = field === 'subscriptionStatus' ? ['free', 'active', 'suspended', 'expired'] : field === 'status' ? ['active', 'disabled'] : field === 'plan' ? ['free', 'premium'] : field === 'role' ? ['user', 'admin'] : [];
  if (!accepted.includes(data.value)) return NextResponse.json({ error: 'Maydon yoki qiymat ruxsat etilmagan.' }, { status: 400 });
  try { const updated = await dbCall({ op: 'admin_user', actorId: user.id, targetId: data.userId, [String(field)]: data.value }); return NextResponse.json({ user: updated }); }
  catch (cause) { const e = cause as Error & { kind?: string }; return NextResponse.json({ error: e.message }, { status: e.kind === 'validation' ? 400 : 500 }); }
}
