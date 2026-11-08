import { createHash, timingSafeEqual } from 'node:crypto';

function equalHash(actual, expected) {
  const a = Buffer.from(String(actual).toLowerCase());
  const b = Buffer.from(String(expected).toLowerCase());
  return a.length === b.length && timingSafeEqual(a, b);
}

export function verifyClickSignature(fields, secret = process.env.CLICK_SECRET_KEY ?? '') {
  const action = fields.action;
  const required = ['click_trans_id', 'service_id', 'merchant_trans_id', 'amount', 'action', 'sign_time', 'sign_string'];
  if (required.some(key => typeof fields[key] !== 'string') || !['0', '1'].includes(action)) return false;
  if (action === '1' && !fields.merchant_prepare_id) return false;
  const signatureText = fields.click_trans_id + fields.service_id + secret + fields.merchant_trans_id +
    (action === '1' ? fields.merchant_prepare_id : '') + fields.amount + action + fields.sign_time;
  return equalHash(fields.sign_string, createHash('md5').update(signatureText).digest('hex'));
}

export function parseClickAmount(value) {
  if (typeof value !== 'string' || !/^\d+(?:\.\d{1,2})?$/.test(value)) return null;
  const [units, fraction = ''] = value.split('.');
  const minor = Number(units) * 100 + Number(fraction.padEnd(2, '0'));
  return Number.isSafeInteger(minor) ? minor : null;
}
