import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { parseClickAmount, verifyClickSignature } from '../lib/payments/click-core.mjs';
import { verifyPaymeAuthorization } from '../lib/payments/payme-core.mjs';

function signedClick(action) {
  const actionString = String(action);
  const fields = { click_trans_id: 'test-click-transaction', service_id: 'test-service', merchant_trans_id: 'test-order',
    ...(actionString === '1' ? { merchant_prepare_id: '14' } : {}), amount: '12500.00', action: actionString, sign_time: '2026-11-05 12:00:00' };
  fields.sign_string = createHash('md5').update(fields.click_trans_id + fields.service_id + 'mock-secret' + fields.merchant_trans_id +
    (actionString === '1' ? fields.merchant_prepare_id : '') + fields.amount + fields.action + fields.sign_time).digest('hex');
  return fields;
}

test('Click prepare and complete signatures match the provider formula', () => {
  assert.equal(verifyClickSignature(signedClick(0), 'mock-secret'), true);
  assert.equal(verifyClickSignature(signedClick(1), 'mock-secret'), true);
});

test('Click rejects tampered values, missing prepare ID, and bad signatures', () => {
  const tampered = signedClick(1); tampered.amount = '1.00';
  assert.equal(verifyClickSignature(tampered, 'mock-secret'), false);
  const missing = signedClick(1); delete missing.merchant_prepare_id;
  assert.equal(verifyClickSignature(missing, 'mock-secret'), false);
  assert.equal(verifyClickSignature(signedClick(0), 'wrong-secret'), false);
});

test('Click amount parsing rejects malformed or overprecision amounts', () => {
  assert.equal(parseClickAmount('12000'), 1_200_000);
  assert.equal(parseClickAmount('12000.5'), 1_200_050);
  assert.equal(parseClickAmount('-1'), null);
  assert.equal(parseClickAmount('1.001'), null);
  assert.equal(parseClickAmount('NaN'), null);
});

test('Payme Basic authorization accepts configured credentials only', () => {
  const good = `Basic ${Buffer.from('merchant-login:mock-key').toString('base64')}`;
  const bad = `Basic ${Buffer.from('merchant-login:wrong-key').toString('base64')}`;
  assert.equal(verifyPaymeAuthorization(good, 'merchant-login', 'mock-key'), true);
  assert.equal(verifyPaymeAuthorization(bad, 'merchant-login', 'mock-key'), false);
  assert.equal(verifyPaymeAuthorization(null, 'merchant-login', 'mock-key'), false);
});
