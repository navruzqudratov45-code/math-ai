import { timingSafeEqual } from 'node:crypto';

export function verifyPaymeAuthorization(header, login = process.env.PAYME_LOGIN ?? '', key = process.env.PAYME_KEY ?? '') {
  if (typeof header !== 'string' || !header.startsWith('Basic ') || !login || !key) return false;
  let decoded;
  try { decoded = Buffer.from(header.slice(6), 'base64').toString('utf8'); } catch { return false; }
  const split = decoded.indexOf(':');
  if (split < 0) return false;
  const actualLogin = Buffer.from(decoded.slice(0, split));
  const actualKey = Buffer.from(decoded.slice(split + 1));
  const expectedLogin = Buffer.from(login);
  const expectedKey = Buffer.from(key);
  return actualLogin.length === expectedLogin.length && actualKey.length === expectedKey.length &&
    timingSafeEqual(actualLogin, expectedLogin) && timingSafeEqual(actualKey, expectedKey);
}
