import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdtempSync, readFileSync, rmSync, existsSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { parseClickAmount, verifyClickSignature } from '../lib/payments/click-core.mjs';
import { verifyPaymeAuthorization } from '../lib/payments/payme-core.mjs';

const python = process.platform === 'win32' ? path.resolve('.venv/Scripts/python.exe') : path.resolve('.venv/bin/python');
assert.ok(existsSync(python), 'Create .venv and install requirements.txt before running launch tests.');
const root = process.cwd();
function tempDb() { const dir = mkdtempSync(path.join(os.tmpdir(), 'mathai-launch-')); return { dir, db: path.join(dir, 'test.sqlite') }; }
function invoke(script, payload, db) {
  const result = spawnSync(python, [path.join(root, 'solver', script)], { cwd: root, env: { ...process.env, MATHAI_DB_PATH: db }, input: JSON.stringify(payload), encoding: 'utf8', timeout: 10_000, windowsHide: true, maxBuffer: 1_000_000 });
  if (result.error) throw result.error;
  assert.equal(result.status, 0, result.stderr || `${script} process failed`);
  return JSON.parse(result.stdout);
}
function store(db, data) { return invoke('auth_store.py', data, db); }
function engine(problem, db = path.join(os.tmpdir(), 'mathai-no-db.sqlite')) {
  const result = spawnSync(python, [path.join(root, 'solver', 'math_engine.py')], { cwd: root, env: { ...process.env, MATHAI_DB_PATH: db }, input: JSON.stringify({ problem }), encoding: 'utf8', timeout: 10_000, windowsHide: true });
  if (result.error) throw result.error;
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}
function invokeAsync(payload, db) {
  return new Promise((resolve, reject) => {
    const child = spawn(python, [path.join(root, 'solver', 'auth_store.py')], { cwd: root, env: { ...process.env, MATHAI_DB_PATH: db }, windowsHide: true, shell: false, stdio: ['pipe', 'pipe', 'pipe'] });
    let out = '', err = '';
    child.stdout.setEncoding('utf8'); child.stderr.setEncoding('utf8');
    child.stdout.on('data', chunk => { out += chunk; }); child.stderr.on('data', chunk => { err += chunk; });
    child.on('error', reject); child.on('close', code => {
      if (code !== 0) return reject(new Error(err || `auth_store exited ${code}`));
      try { resolve(JSON.parse(out)); } catch (cause) { reject(cause); }
    });
    child.stdin.end(JSON.stringify(payload));
  });
}
function signedClick(action, overrides = {}) {
  const actionString=String(action);
  const fields = { click_trans_id: 'launch-click-transaction', service_id: 'launch-service', merchant_trans_id: 'launch-order', ...(actionString === '1' ? { merchant_prepare_id: '19' } : {}), amount: '12500.00', action: actionString, sign_time: '2026-11-05 12:00:00', ...overrides };
  fields.sign_string = createHash('md5').update(fields.click_trans_id + fields.service_id + 'launch-secret' + fields.merchant_trans_id + (actionString === '1' ? fields.merchant_prepare_id : '') + fields.amount + fields.action + fields.sign_time).digest('hex');
  return fields;
}

test('math AST rejects code execution, attributes, huge exponents, oversized input, and non-whitelisted functions', () => {
  for (const problem of ["simplify __import__('os')", 'simplify x.__class__', 'simplify x**1000', 'simplify gamma(x)', `simplify ${'x+'.repeat(510)}x`]) {
    assert.equal(engine(problem).ok, false, `Expected rejection: ${problem.slice(0, 55)}`);
  }
  assert.equal(engine('simplify x**3').ok, true);
});

test('auth store rejects injection, validates passwords, hashes credentials, and blocks privilege escalation/last-admin removal', () => {
  const { dir, db } = tempDb();
  try {
    assert.equal(store(db, { op: 'register', name: 'Bad', email: "' OR 1=1 --", password: 'secure-password' }).ok, false);
    assert.equal(store(db, { op: 'register', name: 'Valid User', email: 'sql@example.test', password: 'short' }).ok, false);
    const created = store(db, { op: 'register', name: 'Valid User', email: 'secure@example.test', password: 'secure-password-123', role: 'admin', plan: 'premium' });
    assert.equal(created.ok, true); assert.equal(created.result.role, 'user'); assert.equal(created.result.plan, 'free');
    const session = store(db, { op: 'login', email: created.result.email, password: 'secure-password-123', tokenHash: 'launch-session', expiresAt: Math.floor(Date.now()/1000)+3600 });
    assert.equal(session.ok, true);
    const unsafeLookup = store(db, { op: 'history', userId: '1 OR 1=1' });
    assert.equal(unsafeLookup.ok, true); assert.equal(unsafeLookup.result.total, 0);
    const admin = store(db, { op: 'provision_admin', email: 'navruzqudratov45@gmail.com', name: 'Root Admin', password: 'long-admin-password-123' });
    assert.equal(admin.ok, true);
    const adminSession = store(db, { op: 'login', email: 'navruzqudratov45@gmail.com', password: 'long-admin-password-123', tokenHash: 'root-session', expiresAt: Math.floor(Date.now()/1000)+3600 });
    assert.equal(adminSession.ok, true);
    assert.equal(store(db, { op: 'admin_user', actorId: adminSession.result.id, targetId: adminSession.result.id, status: 'disabled' }).ok, false);
    const row = spawnSync(python, ['-c', "import os,sqlite3; c=sqlite3.connect(os.environ['MATHAI_DB_PATH']); print('|'.join(map(str,c.execute('select password_hash,password_salt,role,plan from users where email=?',('secure@example.test',)).fetchone())))"], { cwd: root, env: { ...process.env, MATHAI_DB_PATH: db }, encoding: 'utf8', timeout: 5000 });
    assert.equal(row.status, 0); const [hash, salt, role, plan] = row.stdout.trim().split('|');
    assert.notEqual(hash, 'secure-password-123'); assert.equal(hash.length, 128); assert.equal(salt.length, 32); assert.equal(role, 'user'); assert.equal(plan, 'free');
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

test('Click and Payme reject tampered, mismatched, and malformed authentication data', () => {
  const valid = signedClick(1);
  assert.equal(verifyClickSignature(valid, 'launch-secret'), true);
  assert.equal(verifyClickSignature({ ...valid, amount: '1.00' }, 'launch-secret'), false);
  assert.equal(verifyClickSignature({ ...valid, sign_string: 'not-a-signature' }, 'launch-secret'), false);
  assert.equal(verifyClickSignature({ ...valid, merchant_prepare_id: '' }, 'launch-secret'), false);
  assert.equal(parseClickAmount('12500.001'), null);
  const payme = `Basic ${Buffer.from('merchant:secret').toString('base64')}`;
  assert.equal(verifyPaymeAuthorization(payme, 'merchant', 'secret'), true);
  assert.equal(verifyPaymeAuthorization(payme, 'merchant', 'wrong'), false);
  assert.equal(verifyPaymeAuthorization('Basic !!!!', 'merchant', 'secret'), false);
  assert.equal(verifyPaymeAuthorization('Bearer token', 'merchant', 'secret'), false);
});

test('SQLite session and usage calls stay within the startup latency budget', () => {
  const { dir, db } = tempDb();
  try {
    const user = store(db, { op: 'register', name: 'Latency User', email: 'latency@example.test', password: 'latency-password-123' }).result;
    store(db, { op: 'register_session', userId: user.id, tokenHash: 'latency-session', expiresAt: Math.floor(Date.now()/1000)+3600 });
    const started = performance.now(); assert.equal(store(db, { op: 'session', tokenHash: 'latency-session' }).result.id, user.id);
    assert.ok(performance.now()-started < 3000, 'session lookup exceeded 3s');
    const usageStarted = performance.now(); assert.equal(store(db, { op: 'usage', userId: user.id }).ok, true);
    assert.ok(performance.now()-usageStarted < 3000, 'usage lookup exceeded 3s');
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

test('SymPy algebra and geometry operations stay within the compute latency budget', () => {
  for (const [problem, expected] of [['simplify 2*x+3*x', '5*x'], ['Find the area of a circle with radius 3', null]]) {
    const started = performance.now(), result = engine(problem);
    assert.ok(performance.now()-started < 5000, `${problem} exceeded 5s`);
    assert.equal(result.ok, true); if (expected) assert.equal(result.data.result, expected);
  }
});

test('concurrent quota reservations have no SQLite busy errors or limit overrun', async () => {
  const { dir, db } = tempDb();
  try {
    const user = store(db, { op: 'register', name: 'Parallel User', email: 'parallel@example.test', password: 'parallel-password-123' }).result;
    const results = await Promise.all(Array.from({ length: 10 }, () => invokeAsync({ op: 'reserve_usage', userId: user.id, hasText: true }, db)));
    assert.ok(results.every(result => result.ok), 'a concurrent SQLite operation failed');
    assert.equal(results.filter(result => result.result.allowed).length, 10);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

test('concurrent Click and Payme settlement callbacks remain idempotent', async () => {
  const { dir, db } = tempDb();
  try {
    const user = store(db, { op: 'register', name: 'Payment User', email: 'payments@example.test', password: 'payments-password-123' }).result;
    const clickOrder = store(db, { op: 'payment_create_order', id: 'launch-click-order', idempotencyKey: 'launch-click-key', userId: user.id, provider: 'click', planCode: 'premium_monthly', amountUZS: 12000 }).result;
    const clickPrep = store(db, { op: 'payment_click_prepare', orderId: clickOrder.id, transactionId: 'launch-click-tx', paymentId: 'launch-click-doc', amountUZS: 12000, amountMinor: 1_200_000 }).result;
    const clickCallbacks = await Promise.all(Array.from({ length: 6 }, () => invokeAsync({ op: 'payment_click_complete', orderId: clickOrder.id, transactionId: 'launch-click-tx', prepareId: clickPrep.prepareId, amountUZS: 12000, amountMinor: 1_200_000, providerError: 0 }, db)));
    assert.ok(clickCallbacks.every(item => item.ok)); assert.ok(clickCallbacks.some(item => item.result.duplicate));
    const paymeOrder = store(db, { op: 'payment_create_order', id: 'launch-payme-order', idempotencyKey: 'launch-payme-key', userId: user.id, provider: 'payme', planCode: 'premium_monthly', amountUZS: 12000 }).result;
    const created = await Promise.all(Array.from({ length: 5 }, () => invokeAsync({ op: 'payment_payme_create', orderId: paymeOrder.id, transactionId: 'launch-payme-tx', providerTime: Date.now(), amountMinor: 1_200_000 }, db)));
    assert.ok(created.every(item => item.ok));
    const performed = await Promise.all(Array.from({ length: 6 }, () => invokeAsync({ op: 'payment_payme_perform', transactionId: 'launch-payme-tx' }, db)));
    assert.ok(performed.every(item => item.ok)); assert.ok(performed.some(item => item.result.duplicate));
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

test('launch configuration includes global security headers and public health route', () => {
  const config = readFileSync(path.join(root, 'next.config.mjs'), 'utf8');
  for (const header of ['X-Content-Type-Options', 'X-Frame-Options', 'Referrer-Policy', 'Permissions-Policy']) assert.ok(config.includes(header));
  assert.ok(existsSync(path.join(root, 'app/api/health/route.ts')));
});
