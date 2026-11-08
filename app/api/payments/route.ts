import { NextRequest, NextResponse } from 'next/server';
import { dbCall, requireRequestUser } from '../../../lib/auth';

export const runtime = 'nodejs';

export async function GET(request: NextRequest) {
  const user = await requireRequestUser(request);
  if (!user) return NextResponse.json({ error: 'Hisobga kirish talab qilinadi.' }, { status: 401 });
  const orderId = request.nextUrl.searchParams.get('order');
  if (orderId) {
    const order = await dbCall({ op: 'payment_order_status', id: orderId, userId: user.id });
    return order ? NextResponse.json({ order }) : NextResponse.json({ error: 'Buyurtma topilmadi.' }, { status: 404 });
  }
  return NextResponse.json({ orders: await dbCall({ op: 'payment_user_orders', userId: user.id }) });
}

export async function POST() {
  return NextResponse.json({ error: 'MathAI barcha foydalanuvchilar uchun bepul. Yangi to‘lovlar qabul qilinmaydi.' }, { status: 410 });
}
