import { NextRequest, NextResponse } from 'next/server';
import { dbCall, originIsAllowed, readJson, requireRequestUser } from '../../../../../lib/auth';
import { reverseClickPayment } from '../../../../../lib/payments/click';

export const runtime = 'nodejs';
export async function POST(request: NextRequest) {
  if (!originIsAllowed(request)) return NextResponse.json({ error: 'So‘rov manbasi tekshiruvdan o‘tmadi.' }, { status: 403 });
  if (!await requireRequestUser(request, 'admin')) return NextResponse.json({ error: 'Topilmadi.' }, { status: 404 });
  let body: { orderId?: unknown };
  try { body = await readJson(request, 1024); } catch { return NextResponse.json({ error: 'So‘rov formati noto‘g‘ri.' }, { status: 400 }); }
  if (typeof body.orderId !== 'string' || body.orderId.length > 64) return NextResponse.json({ error: 'Buyurtma identifikatori noto‘g‘ri.' }, { status: 400 });
  const reservation = await dbCall<{ ok: boolean; paymentId?: string }>({ op: 'payment_click_refund_prepare', orderId: body.orderId });
  if (!reservation.ok || !reservation.paymentId) return NextResponse.json({ error: 'Click uchun to‘langan, qaytarilmagan buyurtma topilmadi.' }, { status: 409 });
  try {
    await reverseClickPayment(reservation.paymentId);
    const refunded = await dbCall({ op: 'payment_click_refund_finish', orderId: body.orderId, success: true });
    return NextResponse.json({ refunded: Boolean(refunded) });
  } catch (cause) {
    await dbCall({ op: 'payment_click_refund_finish', orderId: body.orderId, success: false }).catch(() => false);
    console.error('Click reversal failed:', cause instanceof Error ? cause.message : 'unknown error');
    return NextResponse.json({ error: 'Click pulni qaytarishni tasdiqlamadi. Merchant kabinetidagi holatni tekshiring.' }, { status: 502 });
  }
}
