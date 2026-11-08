import { NextResponse } from 'next/server';
import { dbCall } from '../../../lib/auth';
import { computeWithSympy } from '../../../lib/math-engine';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET() {
  const timestamp = new Date().toISOString();
  const [databaseResult, sympyResult] = await Promise.allSettled([
    dbCall<boolean>({ op: 'health_check' }),
    computeWithSympy('2*x + 3*x'),
  ]);
  const database = databaseResult.status === 'fulfilled' && databaseResult.value === true ? 'ok' : 'degraded';
  const sympy = sympyResult.status === 'fulfilled' && sympyResult.value.supported && sympyResult.value.result === '5*x' ? 'ok' : 'degraded';
  const status = database === 'ok' && sympy === 'ok' ? 'ok' : 'degraded';
  return NextResponse.json({ status, database, sympy, timestamp }, { status: status === 'ok' ? 200 : 503 });
}
