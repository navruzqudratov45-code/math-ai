import { NextRequest, NextResponse } from 'next/server';
import { dbCall, originIsAllowed, readJson, requireRequestUser } from '../../../../lib/auth';
export async function GET(request: NextRequest) {
  const user = await requireRequestUser(request, 'admin');
  if (!user) return NextResponse.json({ error: 'Topilmadi.' }, { status: 404 });
  return NextResponse.json(await dbCall({ op: 'settings' }));
}
export async function PATCH(request: NextRequest) {
  if (!originIsAllowed(request)) return NextResponse.json({ error: 'So‘rov manbasi tekshiruvdan o‘tmadi.' }, { status: 403 });
  const user = await requireRequestUser(request, 'admin');
  if (!user) return NextResponse.json({ error: 'Topilmadi.' }, { status: 404 });
  if (Number(request.headers.get('content-length') ?? 0) > 4096) return NextResponse.json({ error: 'So‘rov hajmi juda katta.' }, { status: 413 });
  let data: Record<string, unknown>; try { data = await readJson(request); } catch (cause) { return NextResponse.json({ error: (cause as Error).message }, { status: (cause as {status?:number}).status ?? 400 }); }
  const values: Record<string, unknown> = {};
  for (const key of ['freeDailyLimit', 'premiumDailyLimit', 'freeSavedCapacity', 'premiumSavedCapacity']) if (key in data) {
    if (!Number.isInteger(data[key]) || Number(data[key]) < 0 || Number(data[key]) > 10000) return NextResponse.json({ error: 'Limit 0 dan 10 000 gacha butun son bo‘lishi kerak.' }, { status: 400 });
    values[key] = data[key];
  }
  if ('registrationEnabled' in data) { if (typeof data.registrationEnabled !== 'boolean') return NextResponse.json({ error: 'Ro‘yxatdan o‘tish sozlamasi noto‘g‘ri.' }, { status: 400 }); values.registrationEnabled = data.registrationEnabled; }
  for (const key of ['premiumExtendedExplanations', 'premiumPriorityRouting']) if (key in data) {
    if (typeof data[key] !== 'boolean') return NextResponse.json({ error: 'Premium xususiyati true yoki false bo‘lishi kerak.' }, { status: 400 });
    values[key] = data[key];
  }
  for (const key of ['freePlanFeatures', 'premiumPlanFeatures']) if (key in data) {
    const features = data[key];
    if (!Array.isArray(features) || features.length > 12 || features.some(item => typeof item !== 'string' || item.trim().length < 2 || item.length > 120)) {
      return NextResponse.json({ error: 'Reja xususiyatlari 12 tagacha, har biri 2–120 belgidan iborat matn bo‘lishi kerak.' }, { status: 400 });
    }
    values[key] = features.map(item => (item as string).trim());
  }
  return NextResponse.json(await dbCall({ op: 'settings', values }));
}
