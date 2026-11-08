import { dbCall } from './auth';
import { computeWithSympy } from './math-engine';
import { publicPaymentConfig } from './payments/config';

type Event = { id: number; module: string; severity: 'info' | 'warning' | 'critical'; code: string; message: string; remediation: string | null; autoFixed: boolean; createdAt: number };
type Audit = { healthy: boolean; checkedAt: number; modules: Record<string, { status: 'healthy' | 'warning' | 'critical'; [key: string]: unknown }>; remediations: Record<string, number>; telemetryLastHour: { requests: number; errors: number; errorRate: number; avgLatencyMs: number; timeoutUpstreamFailures?: number; upstreamFailureRate?: number }; events: Event[] };
export type SupervisorReport = Audit & {
  environment: { openrouterConfigured: boolean; resendConfigured: boolean; paymentsLive: boolean };
  modules: Audit['modules'] & { sympy: { status: 'healthy' | 'critical' | 'warning'; latencyMs: number | null; result?: string }; openrouter: { status: 'healthy' | 'warning'; configured: boolean }; payments: Audit['modules'][string] & { live: boolean } };
};

export async function runSupervisorCheck(options: { runAutoFix?: boolean; probeSympy?: boolean } = {}): Promise<SupervisorReport> {
  const audit = await dbCall<Audit>({ op: 'supervisor_audit', runAutoFix: options.runAutoFix ?? false });
  const openrouterConfigured = Boolean(process.env.OPENROUTER_API_KEY && process.env.OPENROUTER_MODEL);
  const resendConfigured = Boolean(process.env.RESEND_API_KEY && process.env.AUTH_FROM_EMAIL && process.env.APP_URL);
  const payments = publicPaymentConfig();
  let sympy: SupervisorReport['modules']['sympy'] = { status: 'warning', latencyMs: null };
  if (options.probeSympy !== false) {
    const started = Date.now();
    let timeout: ReturnType<typeof setTimeout> | undefined;
    try {
      const result = await Promise.race([
        computeWithSympy('2*x + 3*x'),
        new Promise<never>((_, reject) => { timeout = setTimeout(() => reject(new Error('Supervisor SymPy probe timed out.')), 9_000); }),
      ]);
      const latencyMs = Date.now() - started;
      const healthy = result.supported === true && result.result === '5*x';
      sympy = { status: healthy ? 'healthy' : 'critical', latencyMs, ...(result.result ? { result: result.result } : {}) };
      if (!healthy) void dbCall({ op: 'supervisor_log', module: 'sympy', severity: 'critical', code: 'sympy_probe_mismatch', message: 'SymPy nazorat hisobi kutilgan 5*x natijani bermadi.' }).catch(() => {});
    } catch (cause) {
      sympy = { status: 'critical', latencyMs: Date.now() - started };
      void dbCall({ op: 'supervisor_log', module: 'sympy', severity: 'critical', code: 'sympy_probe_failed', message: 'SymPy nazorat tekshiruvi bajarilmadi.', remediation: cause instanceof Error ? cause.message.slice(0, 180) : undefined }).catch(() => {});
    } finally { if (timeout) clearTimeout(timeout); }
  }
  const openrouter = { status: openrouterConfigured ? 'healthy' as const : 'warning' as const, configured: openrouterConfigured };
  const modules: SupervisorReport['modules'] = {
    ...audit.modules,
    payments: { ...audit.modules.payments, live: payments.live },
    sympy,
    openrouter,
  };
  const allHealthy = Object.values(modules).every(module => module.status === 'healthy');
  return { ...audit, healthy: audit.healthy && allHealthy, modules,
    environment: { openrouterConfigured, resendConfigured, paymentsLive: payments.live } };
}
