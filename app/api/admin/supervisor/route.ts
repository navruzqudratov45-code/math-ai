import { NextRequest, NextResponse } from 'next/server';
import { originIsAllowed, requireRequestUser } from '../../../../lib/auth';
import { runSupervisorCheck } from '../../../../lib/supervisor';

export const runtime = 'nodejs';

export async function GET(request: NextRequest) {
  if (!await requireRequestUser(request, 'admin')) return NextResponse.json({ error: 'Topilmadi.' }, { status: 404 });
  try { return NextResponse.json(await runSupervisorCheck({ runAutoFix: false, probeSympy: true })); }
  catch (cause) {
    console.error('Supervisor health check failed:', cause instanceof Error ? cause.message.slice(0, 160) : 'unknown error');
    return NextResponse.json({ error: 'Supervisor tekshiruvi bajarilmadi.' }, { status: 503 });
  }
}

export async function POST(request: NextRequest) {
  if (!originIsAllowed(request)) return NextResponse.json({ error: 'So‘rov manbasi tasdiqlanmadi.' }, { status: 403 });
  if (!await requireRequestUser(request, 'admin')) return NextResponse.json({ error: 'Topilmadi.' }, { status: 404 });
  try { return NextResponse.json(await runSupervisorCheck({ runAutoFix: true, probeSympy: true })); }
  catch (cause) {
    console.error('Supervisor remediation failed:', cause instanceof Error ? cause.message.slice(0, 160) : 'unknown error');
    return NextResponse.json({ error: 'Tekshiruv yoki xavfsiz tuzatish bajarilmadi.' }, { status: 503 });
  }
}

