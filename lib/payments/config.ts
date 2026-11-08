export type PaymentProvider = 'click' | 'payme';

function positiveAmount(name: string) {
  const value = process.env[name];
  if (!value || !/^\d+$/.test(value)) return null;
  const amount = Number(value);
  return Number.isSafeInteger(amount) && amount > 0 ? amount : null;
}

export function publicPaymentConfig() {
  return {
    monthlyAmountUZS: positiveAmount('MATHAI_PREMIUM_MONTHLY_UZS'),
    yearlyAmountUZS: positiveAmount('MATHAI_PREMIUM_YEARLY_UZS'),
    providers: {
      click: Boolean(process.env.CLICK_SERVICE_ID && process.env.CLICK_MERCHANT_ID && process.env.CLICK_SECRET_KEY),
      payme: Boolean(process.env.PAYME_MERCHANT_ID && process.env.PAYME_LOGIN && process.env.PAYME_KEY),
    },
    live: process.env.NODE_ENV === 'production' && process.env.PAYMENT_MODE === 'live' && Boolean(process.env.APP_URL?.startsWith('https://')),
  };
}

export function requireLiveProvider(provider: PaymentProvider) {
  const config = publicPaymentConfig();
  if (!config.live) throw new Error('Live payments require production mode, PAYMENT_MODE=live, and an HTTPS APP_URL.');
  if (!config.providers[provider]) throw new Error(`${provider} merchant credentials are incomplete.`);
}

export function amountForPlan(planCode: 'premium_monthly' | 'premium_yearly') {
  return planCode === 'premium_monthly' ? positiveAmount('MATHAI_PREMIUM_MONTHLY_UZS') : positiveAmount('MATHAI_PREMIUM_YEARLY_UZS');
}

export function publicAppUrl() {
  const url = process.env.APP_URL;
  if (!url) throw new Error('APP_URL is required for merchant checkout and callbacks.');
  const parsed = new URL(url);
  if (process.env.NODE_ENV === 'production' && parsed.protocol !== 'https:') throw new Error('APP_URL must use HTTPS in production.');
  return parsed.origin;
}
