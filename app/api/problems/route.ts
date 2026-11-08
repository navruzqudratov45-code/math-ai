import { NextRequest, NextResponse } from 'next/server';
import { dbCall, originIsAllowed, readJson, requireRequestUser } from '../../../lib/auth';
export async function GET(request: NextRequest) {
  const user = await requireRequestUser(request); if (!user) return NextResponse.json({ error: 'Tizimga kiring.' }, { status: 401 });
  return NextResponse.json(await dbCall({ op: 'history', userId: user.id }));
}
export async function PATCH(request: NextRequest) {
  if (!originIsAllowed(request)) return NextResponse.json({ error: 'So‘rov manbasi tekshiruvdan o‘tmadi.' }, { status: 403 });
  const user = await requireRequestUser(request); if (!user) return NextResponse.json({ error: 'Tizimga kiring.' }, { status: 401 });
  let data: { id?: unknown; saved?: unknown }; try { data = await readJson(request); } catch (cause) { return NextResponse.json({ error: (cause as Error).message }, { status: (cause as {status?:number}).status ?? 400 }); }
  if (!Number.isSafeInteger(data.id) || typeof data.saved !== 'boolean') return NextResponse.json({ error: 'Masala identifikatori noto‘g‘ri.' }, { status: 400 });
  const found = await dbCall<{ ok: boolean; reason?: string; capacity?: number }>({ op: 'toggle_saved', problemId: data.id, userId: user.id });
  if (!found.ok && found.reason === 'capacity') return NextResponse.json({ error: `Saqlangan masalalar limiti (${found.capacity}) tugadi. Tarifni ko‘rib chiqing.`, reason: 'saved_capacity' }, { status: 409 });
  if (!found.ok) return NextResponse.json({ error: 'Masala topilmadi.' }, { status: 404 });
  return NextResponse.json({ ok: true });
}
export async function DELETE(request: NextRequest) {
  if (!originIsAllowed(request)) return NextResponse.json({ error: 'So‘rov manbasi tekshiruvdan o‘tmadi.' }, { status: 403 });
  const user = await requireRequestUser(request); if (!user) return NextResponse.json({ error: 'Tizimga kiring.' }, { status: 401 });
  let data: { id?: unknown }; try { data = await readJson(request); } catch (cause) { return NextResponse.json({ error: (cause as Error).message }, { status: (cause as {status?:number}).status ?? 400 }); }
  if (!Number.isSafeInteger(data.id)) return NextResponse.json({ error: 'Masala identifikatori noto‘g‘ri.' }, { status: 400 });
  const deleted = await dbCall<boolean>({ op: 'delete_problem', problemId: data.id, userId: user.id });
  return deleted ? NextResponse.json({ ok: true }) : NextResponse.json({ error: 'Masala topilmadi.' }, { status: 404 });
}
