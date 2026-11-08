import { createHash } from 'node:crypto';
import type { PaymentProvider } from './config';
import { publicAppUrl, requireLiveProvider } from './config';
export { verifyClickSignature, parseClickAmount } from './click-core.mjs';

export function createClickCheckout(orderId: string, amountUZS: number) {
  requireLiveProvider('click' satisfies PaymentProvider);
  const serviceId = process.env.CLICK_SERVICE_ID!;
  const merchantId = process.env.CLICK_MERCHANT_ID!;
  const url = new URL('https://my.click.uz/services/pay');
  url.searchParams.set('service_id', serviceId);
  url.searchParams.set('merchant_id', merchantId);
  url.searchParams.set('amount', String(amountUZS));
  url.searchParams.set('transaction_param', orderId);
  url.searchParams.set('return_url', `${publicAppUrl()}/payments?order=${encodeURIComponent(orderId)}`);
  return url.toString();
}

export async function reverseClickPayment(paymentId: string) {
  requireLiveProvider('click');
  const userId = process.env.CLICK_USER_ID;
  if (!userId) throw new Error('CLICK_USER_ID is required for Click payment reversals.');
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const auth = `${userId}:${createHash('sha1').update(timestamp + process.env.CLICK_SECRET_KEY!).digest('hex')}:${timestamp}`;
  const response = await fetch(`https://api.click.uz/v2/merchant/payment/reversal/${encodeURIComponent(process.env.CLICK_SERVICE_ID!)}/${encodeURIComponent(paymentId)}`, {
    method: 'DELETE', headers: { Accept: 'application/json', Auth: auth }, signal: AbortSignal.timeout(10_000),
  });
  const result = await response.json().catch(() => null) as { error_code?: number; error_note?: string } | null;
  if (!response.ok || result?.error_code !== 0) throw new Error('Click reversal was rejected or could not be verified.');
  return true;
}

export async function checkClickPayment(paymentId: string) {
  requireLiveProvider('click');
  const userId = process.env.CLICK_USER_ID;
  if (!userId) throw new Error('CLICK_USER_ID is required for Click payment status checks.');
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const auth = `${userId}:${createHash('sha1').update(timestamp + process.env.CLICK_SECRET_KEY!).digest('hex')}:${timestamp}`;
  const response = await fetch(`https://api.click.uz/v2/merchant/payment/status/${encodeURIComponent(process.env.CLICK_SERVICE_ID!)}/${encodeURIComponent(paymentId)}`, {
    method: 'GET', headers: { Accept: 'application/json', Auth: auth }, signal: AbortSignal.timeout(10_000),
  });
  const result = await response.json().catch(() => null) as { error_code?: number; status?: number } | null;
  if (!response.ok || !result || result.error_code !== 0 || !Number.isInteger(result.status)) throw new Error('Click payment status could not be verified.');
  return result.status;
}
