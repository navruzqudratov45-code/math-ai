import { createHash } from 'node:crypto';
import { NextRequest, NextResponse } from 'next/server';
import { dbCall } from '../../../../../lib/auth';
import { verifyPaymeAuthorization } from '../../../../../lib/payments/payme';

export const runtime = 'nodejs';
type Rpc = { id?: string | number | null; method?: string; params?: Record<string, unknown> };
const errorMessage = (uz: string, ru: string, en: string) => ({ uz, ru, en });
function rpcError(id: Rpc['id'], code: number, message: { uz: string; ru: string; en: string }, data?: unknown) {
  return NextResponse.json({ error: { code, message, ...(data === undefined ? {} : { data }) }, id: id ?? null });
}
function badInput(id: Rpc['id']) { return rpcError(id, -32600, errorMessage('So‘rov formati noto‘g‘ri', 'Неверный формат запроса', 'Invalid request format')); }
async function readBounded(request: Request, maxBytes: number): Promise<string> {
  const declared = Number(request.headers.get('content-length') ?? 0);
  if (declared > maxBytes) throw new Error('body_too_large');
  const reader = request.body?.getReader();
  if (!reader) return '';
  const chunks: Uint8Array[] = [];
  let size = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > maxBytes) { await reader.cancel(); throw new Error('body_too_large'); }
    chunks.push(value);
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  return new TextDecoder().decode(bytes);
}

export async function POST(request: NextRequest) {
  let rawBody: string;
  try { rawBody = await readBounded(request, 32768); }
  catch { return badInput(null); }
  if (!verifyPaymeAuthorization(request.headers.get('authorization'))) return rpcError(null, -32504, errorMessage('Ruxsat yo‘q', 'Недостаточно привилегий', 'Insufficient privileges'));
  let body: Rpc;
  try { body = JSON.parse(rawBody) as Rpc; } catch { return rpcError(null, -32700, errorMessage('JSON o‘qilmadi', 'Ошибка парсинга JSON', 'JSON parse error')); }
  if (!body || (typeof body.id !== 'number' && typeof body.id !== 'string') || typeof body.method !== 'string' || !body.params || typeof body.params !== 'object') return badInput(body?.id);
  const { id, method, params } = body;
  const digest = createHash('sha256').update(JSON.stringify(body)).digest('hex');
  try {
    if (method === 'CheckPerformTransaction') {
      const account = params.account as Record<string, unknown> | undefined;
      const orderId = typeof account?.order_id === 'string' ? account.order_id : '';
      const amount = params.amount;
      if (!orderId || !Number.isSafeInteger(amount) || Number(amount) <= 0) return badInput(id);
      const order = await dbCall<{ amountMinor: number; status: string; expiresAt: number } | null>({ op: 'payment_check_order', id: orderId, provider: 'payme' });
      if (!order) return rpcError(id, -31050, errorMessage('Buyurtma topilmadi', 'Счёт не найден', 'Order not found'), 'order_id');
      if (Number(amount) !== order.amountMinor) return rpcError(id, -31001, errorMessage('Summa noto‘g‘ri', 'Неверная сумма', 'Incorrect amount'));
      if (order.status !== 'pending' || order.expiresAt <= Date.now() / 1000) return rpcError(id, -31008, errorMessage('Buyurtma uchun to‘lovni amalga oshirib bo‘lmaydi', 'Невозможно выполнить операцию', 'Cannot perform the operation'));
      return NextResponse.json({ result: { allow: true }, id });
    }
    if (method === 'CreateTransaction') {
      const txId = typeof params.id === 'string' ? params.id : '';
      const time = params.time, amount = params.amount;
      const account = params.account as Record<string, unknown> | undefined;
      const orderId = typeof account?.order_id === 'string' ? account.order_id : '';
      if (!txId || txId.length > 128 || !Number.isSafeInteger(time) || Number(time) > Date.now() + 300000 || !Number.isSafeInteger(amount) || !orderId) return badInput(id);
      const order = await dbCall<{ amountMinor: number; status: string; expiresAt: number } | null>({ op: 'payment_check_order', id: orderId, provider: 'payme' });
      if (!order) return rpcError(id, -31050, errorMessage('Buyurtma topilmadi', 'Счёт не найден', 'Order not found'), 'order_id');
      if (Number(amount) !== order.amountMinor) return rpcError(id, -31001, errorMessage('Summa noto‘g‘ri', 'Неверная сумма', 'Incorrect amount'));
      const result = await dbCall<{ ok: boolean; reason?: string; transaction?: number; status?: string; createdAt?: number }>({ op: 'payment_payme_create', orderId,
        transactionId: txId, providerTime: Number(time), amountMinor: Number(amount), payloadHash: digest });
      if (!result.ok) return rpcError(id, result.reason === 'timeout' ? -31008 : -31001, errorMessage('Tranzaksiyani yaratib bo‘lmadi', 'Невозможно выполнить операцию', 'Cannot create transaction'));
      if (result.status === 'paid') return rpcError(id, -31008, errorMessage('Buyurtma allaqachon to‘langan', 'Невозможно выполнить операцию', 'Order already paid'));
      return NextResponse.json({ result: { create_time: result.createdAt, transaction: String(result.transaction), state: 1 }, id });
    }
    if (method === 'PerformTransaction') {
      const txId = typeof params.id === 'string' ? params.id : '';
      if (!txId) return badInput(id);
      const result = await dbCall<{ ok: boolean; reason?: string; transaction?: number; performTime?: number }>({ op: 'payment_payme_perform', transactionId: txId });
      if (!result.ok) return rpcError(id, result.reason === 'not_found' ? -31003 : -31008, errorMessage('Tranzaksiyani o‘tkazib bo‘lmadi', 'Невозможно выполнить операцию', 'Cannot perform transaction'));
      return NextResponse.json({ result: { transaction: String(result.transaction), perform_time: result.performTime, state: 2 }, id });
    }
    if (method === 'CancelTransaction') {
      const txId = typeof params.id === 'string' ? params.id : '';
      const reason = params.reason;
      if (!txId || !Number.isSafeInteger(reason)) return badInput(id);
      const result = await dbCall<{ ok: boolean; reason?: string; transaction?: number; cancelTime?: number; state?: number }>({ op: 'payment_payme_cancel', transactionId: txId, providerReason: Number(reason) });
      if (!result.ok) return rpcError(id, result.reason === 'not_found' ? -31003 : -31007, errorMessage('Tranzaksiyani bekor qilib bo‘lmadi', 'Невозможно отменить транзакцию', 'Cannot cancel transaction'));
      return NextResponse.json({ result: { transaction: String(result.transaction), cancel_time: result.cancelTime, state: result.state }, id });
    }
    if (method === 'CheckTransaction') {
      const txId = typeof params.id === 'string' ? params.id : '';
      if (!txId) return badInput(id);
      const tx = await dbCall<{ transaction: string; createTime: number; performTime: number; cancelTime: number; state: number; reason: number | null } | null>({ op: 'payment_payme_check', transactionId: txId });
      if (!tx) return rpcError(id, -31003, errorMessage('Tranzaksiya topilmadi', 'Транзакция не найдена', 'Transaction not found'));
      return NextResponse.json({ result: { transaction: tx.transaction, create_time: tx.createTime, perform_time: tx.performTime, cancel_time: tx.cancelTime, state: tx.state, reason: tx.reason }, id });
    }
    if (method === 'GetStatement') {
      const from = params.from, to = params.to;
      if (!Number.isSafeInteger(from) || !Number.isSafeInteger(to) || Number(from) > Number(to)) return badInput(id);
      const transactions = await dbCall({ op: 'payment_payme_statement', from: Number(from), to: Number(to) });
      return NextResponse.json({ result: { transactions }, id });
    }
    return rpcError(id, -32601, errorMessage('Metod topilmadi', 'Метод не найден', 'Method not found'), method);
  } catch (cause) {
    console.error('Payme callback processing failed:', method, cause instanceof Error ? cause.message : 'unknown error');
    return rpcError(id, -32400, errorMessage('Ichki tizim xatosi', 'Системная ошибка', 'System error'));
  }
}
