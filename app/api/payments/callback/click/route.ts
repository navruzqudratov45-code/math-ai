import { createHash } from 'node:crypto';
import { NextRequest, NextResponse } from 'next/server';
import { dbCall } from '../../../../../lib/auth';
import { verifyClickSignature, parseClickAmount } from '../../../../../lib/payments/click';

export const runtime = 'nodejs';
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
function reply(fields: Record<string, string>, error: number, note: string, extra: Record<string, unknown> = {}) {
  return NextResponse.json({ click_trans_id: fields.click_trans_id ?? '', merchant_trans_id: fields.merchant_trans_id ?? '', ...extra, error, error_note: note });
}

export async function POST(request: NextRequest) {
  let fields: Record<string, string>;
  try { fields = Object.fromEntries(new URLSearchParams(await readBounded(request, 8192))); }
  catch { return NextResponse.json({ error: -8, error_note: 'Error in request from click' }, { status: 400 }); }
  const action = fields.action;
  if (!verifyClickSignature(fields) || fields.service_id !== process.env.CLICK_SERVICE_ID) return reply(fields, -1, 'SIGN CHECK FAILED!');
  if (!fields.click_paydoc_id || typeof fields.error !== 'string' || !Number.isSafeInteger(Number(fields.error)) || Number(fields.error) > 0 || typeof fields.error_note !== 'string') return reply(fields, -8, 'Error in request from click');
  const amountMinor = parseClickAmount(fields.amount ?? '');
  if (amountMinor === null) return reply(fields, -2, 'Incorrect parameter amount');
  const amountUZS = amountMinor / 100;
  const payloadHash = createHash('sha256').update(JSON.stringify(fields)).digest('hex');
  try {
    if (action === '0') {
      if (!fields.click_paydoc_id) return reply(fields, -8, 'Error in request from click');
      const result = await dbCall<{ ok: boolean; reason?: string; prepareId?: string; duplicate?: boolean }>({ op: 'payment_click_prepare',
        orderId: fields.merchant_trans_id, transactionId: fields.click_trans_id, paymentId: fields.click_paydoc_id, amountUZS, amountMinor, payloadHash });
      if (!result.ok) return reply(fields, result.reason === 'amount' ? -2 : result.reason === 'paid' ? -4 : result.reason === 'state' ? -8 : -5,
        result.reason === 'amount' ? 'Incorrect parameter amount' : result.reason === 'paid' ? 'Already paid' : result.reason === 'state' ? 'Error in request from click' : 'User does not exist');
      return reply(fields, 0, 'Success', { merchant_prepare_id: Number(result.prepareId) });
    }
    if (action === '1') {
      const result = await dbCall<{ ok: boolean; canceled?: boolean; reason?: string }>({ op: 'payment_click_complete', orderId: fields.merchant_trans_id,
        transactionId: fields.click_trans_id, prepareId: fields.merchant_prepare_id, amountUZS, amountMinor,
        providerError: Number(fields.error) });
      if (!result.ok) {
        const mapped = result.reason === 'amount' ? [-2, 'Incorrect parameter amount']
          : result.reason === 'paid' ? [-4, 'Already paid']
          : result.reason === 'canceled' ? [-9, 'Transaction cancelled']
          : [-6, 'Transaction does not exist'];
        return reply(fields, mapped[0] as number, mapped[1] as string);
      }
      if (result.canceled) return reply(fields, -9, 'Transaction cancelled', { merchant_confirm_id: 0 });
      return reply(fields, 0, 'Success', { merchant_confirm_id: Number(fields.merchant_prepare_id) });
    }
    return reply(fields, -3, 'Action not found');
  } catch (cause) {
    console.error('Click callback processing failed:', cause instanceof Error ? cause.message : 'unknown error');
    return reply(fields, -7, 'Failed to update user');
  }
}
