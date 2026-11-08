import { publicAppUrl, requireLiveProvider } from './config';
export { verifyPaymeAuthorization } from './payme-core.mjs';

export function createPaymeCheckout(orderId: string, amountUZS: number) {
  requireLiveProvider('payme');
  const url = new URL('https://checkout.paycom.uz/');
  const appUrl = publicAppUrl();
  const fields = new URLSearchParams({ merchant: process.env.PAYME_MERCHANT_ID!, 'account[order_id]': orderId,
    amount: String(amountUZS * 100), lang: 'uz', callback: `${appUrl}/payments?order=${encodeURIComponent(orderId)}` });
  return { url: url.toString(), fields: Object.fromEntries(fields) };
}
