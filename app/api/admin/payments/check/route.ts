import { NextRequest, NextResponse } from 'next/server';
import { dbCall, originIsAllowed, readJson, requireRequestUser } from '../../../../../lib/auth';
import { checkClickPayment } from '../../../../../lib/payments/click';

export const runtime = 'nodejs';
export async function POST(request: NextRequest) {
  if (!originIsAllowed(request)) return NextResponse.json({ error: 'So‘rov manbasi tekshiruvdan o‘tmadi.' }, { status: 403 });
  if (!await requireRequestUser(request, 'admin')) return NextResponse.json({ error: 'Topilmadi.' }, { status: 404 });
  let body: { orderId?: unknown };
  try { body = await readJson(request, 1024); } catch { return NextResponse.json({ error: 'So‘rov formati noto‘g‘ri.' }, { status: 400 }); }
  if (typeof body.orderId !== 'string' || body.orderId.length > 64) return NextResponse.json({ error: 'Buyurtma identifikatori noto‘g‘ri.' }, { status: 400 });
  try {
    const order = await dbCall<{ provider: string; status: string; providerPaymentId?: string }>({ op: 'payment_admin_order', id: body.orderId });
    if (!order || order.provider !== 'click' || order.status !== 'pending' || !order.providerPaymentId) return NextResponse.json({ error: 'Tekshiriladigan Click to‘lovi topilmadi.' }, { status: 409 });
    const providerStatus = await checkClickPayment(order.providerPaymentId);
    const result = await dbCall({ op: 'payment_click_reconcile', orderId: body.orderId, providerStatus });
    return NextResponse.json({ result });
  } catch (cause) {
    console.error('Click status verification failed:', cause instanceof Error ? cause.message : 'unknown error');
    return NextResponse.json({ error: 'Click to‘lov holatini tasdiqlay olmadi.' }, { status: 502 });
  }
}
