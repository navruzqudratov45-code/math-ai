import { createHash, randomBytes } from 'node:crypto';
import { spawn } from 'node:child_process';
import path from 'node:path';
import { cookies } from 'next/headers';
import type { NextRequest, NextResponse } from 'next/server';

export const SESSION_COOKIE = 'mathai_session';
export const OWNER_ADMIN_EMAIL = (process.env.ADMIN_EMAIL || 'navruzqudratov45@gmail.com').toLowerCase();
export type User = { id: number; email: string; name: string; role: 'user' | 'admin'; plan: 'free' | 'premium'; subscriptionStatus: 'free' | 'active' | 'suspended' | 'expired'; subscriptionSource: 'none' | 'admin' | 'payment'; status: 'active' | 'disabled'; createdAt: number };
type StoreReply<T> = { ok: true; result: T } | { ok: false; kind: 'permission' | 'validation' | 'database'; error: string };
export class RequestBodyError extends Error { constructor(public status: number, message: string) { super(message); } }

export async function readJson<T>(request: NextRequest, maxBytes = 4096): Promise<T> {
  const contentType = request.headers.get('content-type') ?? '';
  if (!contentType.toLowerCase().includes('application/json')) throw new RequestBodyError(415, 'JSON so‘rov talab qilinadi.');
  const contentLength = Number(request.headers.get('content-length') ?? 0);
  if (contentLength > maxBytes) throw new RequestBodyError(413, 'So‘rov hajmi juda katta.');
  const reader = request.body?.getReader();
  if (!reader) throw new RequestBodyError(400, 'So‘rov formati noto‘g‘ri.');
  const chunks: Uint8Array[] = []; let size = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read(); if (done) break;
      size += value.byteLength;
      if (size > maxBytes) { await reader.cancel(); throw new RequestBodyError(413, 'So‘rov hajmi juda katta.'); }
      chunks.push(value);
    }
  } catch (cause) { if (cause instanceof RequestBodyError) throw cause; throw new RequestBodyError(400, 'So‘rovni o‘qib bo‘lmadi.'); }
  const body = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.byteLength; }
  try { return JSON.parse(new TextDecoder().decode(body)) as T; }
  catch { throw new RequestBodyError(400, 'So‘rov formati noto‘g‘ri.'); }
}

export function dbCall<T>(data: Record<string, unknown>): Promise<T> {
  const venvPython = process.platform === 'win32'
    ? path.join(process.cwd(), '.venv', 'Scripts', 'python.exe')
    : path.join(process.cwd(), '.venv', 'bin', 'python');
  const interpreter = process.env.SYMPY_PYTHON || venvPython;
  return new Promise((resolve, reject) => {
    const child = spawn(/*turbopackIgnore: true*/ interpreter, [path.join(process.cwd(), 'solver', 'auth_store.py')], { cwd: process.cwd(), windowsHide: true, shell: false, stdio: ['pipe', 'pipe', 'pipe'] });
    let stdout = '', stderr = '', settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      child.kill();
      reject(new Error('Database operation timed out after 10 seconds.'));
    }, 10_000);
    const finish = (callback: () => void) => { if (settled) return; settled = true; clearTimeout(timer); callback(); };
    child.stdout.setEncoding('utf8'); child.stderr.setEncoding('utf8');
    child.stdout.on('data', chunk => { stdout += chunk; if (stdout.length > 1_000_000) { child.kill(); finish(() => reject(new Error('Database response exceeded the allowed size.'))); } });
    child.stderr.on('data', chunk => { stderr += chunk; });
    child.on('error', cause => finish(() => reject(cause)));
    child.on('close', code => {
      if (settled) return;
      if (code !== 0) return finish(() => reject(new Error(stderr.slice(0, 300) || `Database child exited (${code}).`)));
      try {
        const reply = JSON.parse(stdout) as StoreReply<T>;
        if (!reply.ok) {
          const err = new Error(reply.error) as Error & { kind?: string };
          err.kind = reply.kind;
          finish(() => reject(err));
        } else finish(() => resolve(reply.result));
      } catch (cause) { finish(() => reject(cause instanceof Error ? cause : new Error('Database response could not be read.'))); }
    });
    child.stdin.end(JSON.stringify(data));
  });
}

export function newSessionToken() { return randomBytes(32).toString('base64url'); }
export function hashSessionToken(token: string) { return createHash('sha256').update(token).digest('hex'); }
export function sessionCookieOptions() {
  return { httpOnly: true, secure: process.env.NODE_ENV === 'production', sameSite: 'lax' as const, path: '/', maxAge: 60 * 60 * 24 * 7 };
}
export async function getSessionFromToken(token?: string): Promise<User | null> {
  if (!token || token.length > 128) return null;
  try { return await dbCall<User | null>({ op: 'session', tokenHash: hashSessionToken(token) }); }
  catch (cause) { console.error('Auth session lookup failed:', cause instanceof Error ? cause.message : 'unknown error'); return null; }
}
export async function getCurrentUser(): Promise<User | null> {
  const store = await cookies();
  return getSessionFromToken(store.get(SESSION_COOKIE)?.value);
}
export async function requireRequestUser(request: NextRequest, role?: 'admin'): Promise<User | null> {
  const user = await getSessionFromToken(request.cookies.get(SESSION_COOKIE)?.value);
  if (!user || (role === 'admin' && !isOwnerAdmin(user))) return null;
  return user;
}
export function isOwnerAdmin(user: User | null): user is User {
  return !!user && user.role === 'admin' && user.email.toLowerCase() === OWNER_ADMIN_EMAIL;
}
export function setSessionCookie(response: NextResponse, token: string) { response.cookies.set(SESSION_COOKIE, token, sessionCookieOptions()); }
export function clearSessionCookie(response: NextResponse) { response.cookies.set(SESSION_COOKIE, '', { ...sessionCookieOptions(), maxAge: 0 }); }
export function originIsAllowed(request: NextRequest) {
  const origin = request.headers.get('origin');
  return !!origin && origin === request.nextUrl.origin;
}

const attempts = new Map<string, { count: number; resetAt: number }>();
export function authRateLimited(key: string, maximum = 12) {
  const now = Date.now();
  attempts.forEach((value, entry) => { if (value.resetAt <= now) attempts.delete(entry); });
  const current = attempts.get(key);
  if (!current && attempts.size >= 10_000) return true;
  if (!current || current.resetAt <= now) { attempts.set(key, { count: 1, resetAt: now + 15 * 60_000 }); return false; }
  current.count += 1;
  return current.count > maximum;
}
