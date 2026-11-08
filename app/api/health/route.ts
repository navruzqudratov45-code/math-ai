import { NextRequest, NextResponse } from 'next/server';
import { dbCall } from '../../../lib/auth';
import { computeWithSympy } from '../../../lib/math-engine';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

let lastHealthyAt = 0;
let cachedPayload: { status: 'ok' | 'degraded'; database: 'ok' | 'degraded'; sympy: 'ok' | 'degraded'; timestamp: string } | null = null;
let inflightCheck: Promise<{ status: 'ok' | 'degraded'; database: 'ok' | 'degraded'; sympy: 'ok' | 'degraded'; timestamp: string }> | null = null;

async function runHealthCheck() {
  const timestamp = new Date().toISOString();
  const [databaseResult, sympyResult] = await Promise.allSettled([
    dbCall<boolean>({ op: 'health_check' }),
    computeWithSympy('2*x + 3*x'),
  ]);
  const database: 'ok' | 'degraded' = databaseResult.status === 'fulfilled' && databaseResult.value === true ? 'ok' : 'degraded';
  const sympy: 'ok' | 'degraded' = sympyResult.status === 'fulfilled' && sympyResult.value.supported && sympyResult.value.result === '5*x' ? 'ok' : 'degraded';
  const status: 'ok' | 'degraded' = database === 'ok' && sympy === 'ok' ? 'ok' : 'degraded';
  const payload = { status, database, sympy, timestamp };
  if (status === 'ok') {
    lastHealthyAt = Date.now();
    cachedPayload = payload;
  }
  return payload;
}

export async function GET(request?: NextRequest) {
  const forceDeep = request?.nextUrl?.searchParams.get('deep') === '1';
  if (!forceDeep && cachedPayload && Date.now() - lastHealthyAt < 600_000) {
    return NextResponse.json({ ...cachedPayload, timestamp: new Date().toISOString() }, { status: 200 });
  }
  if (!inflightCheck) {
    inflightCheck = runHealthCheck().finally(() => { inflightCheck = null; });
  }
  const payload = await inflightCheck;
  return NextResponse.json(payload, { status: payload.status === 'ok' ? 200 : 503 });
}

