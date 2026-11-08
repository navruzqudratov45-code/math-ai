import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';

export type SympyResult = {
  supported: boolean;
  domain?: string;
  reason?: string;
  operation?: string;
  input?: string;
  result?: string;
  latex?: string;
  steps?: string[];
  verification?: string;
  canonical?: string[][];
  aiVerified?: boolean;
  theory?: string;
  formula?: string;
  diagram?: { kind: string; labels?: Record<string, string>; points?: [number, number][] };
};

type PythonEnvelope = { ok: true; data: SympyResult } | { ok: false; error: string };

export async function computeWithSympy(problem: string): Promise<SympyResult> {
  if (problem.length > 1000) return { supported: false, reason: 'Ifoda SymPy uchun 1000 belgidan uzun.' };
  const projectPython = process.platform === 'win32'
    ? path.join(process.cwd(), '.venv', 'Scripts', 'python.exe')
    : path.join(process.cwd(), '.venv', 'bin', 'python');
  const configuredPython = process.env.SYMPY_PYTHON;
  const interpreter = configuredPython || (existsSync(projectPython) ? projectPython : process.platform === 'win32' ? 'py' : 'python3');
  const args = [path.join(process.cwd(), 'solver', 'math_engine.py')];
  if (!configuredPython && interpreter === 'py') args.unshift('-3');

  return new Promise((resolve, reject) => {
    const child = spawn(/*turbopackIgnore: true*/ interpreter, args, { cwd: process.cwd(), windowsHide: true, shell: false, stdio: ['pipe', 'pipe', 'pipe'] });
    let stdout = '';
    let stderr = '';
    let timedOut = false;
    const timeout = setTimeout(() => { timedOut = true; child.kill(); }, 25_000);
    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');
    child.stdout.on('data', chunk => { stdout += chunk; if (stdout.length > 256_000) child.kill(); });
    child.stderr.on('data', chunk => { stderr += chunk; });
    child.on('error', reject);
    child.on('close', code => {
      clearTimeout(timeout);
      if (timedOut) return reject(new Error('SymPy hisoblash muddati tugadi.'));
      if (code !== 0) return reject(new Error(stderr.slice(0, 300) || `SymPy jarayoni ${code} kodi bilan tugadi.`));
      try {
        const envelope = JSON.parse(stdout.trim()) as PythonEnvelope;
        if (!envelope.ok) return resolve({ supported: false, reason: envelope.error });
        resolve(envelope.data);
      } catch {
        reject(new Error('SymPy javobini o‘qib bo‘lmadi.'));
      }
    });
    child.stdin.end(JSON.stringify({ problem }));
  });
}

export function aiResultMatchesSympy(answer: string, computation: SympyResult): boolean {
  if (!computation.supported || !computation.canonical?.length) return false;
  const normalized = (value: string) => value.toLowerCase()
    .replace(/\\frac\{(-?\d+)\}\{(\d+)\}/g, '$1/$2')
    .replace(/\\left|\\right/g, '')
    .replace(/\\cdot|\\times/g, '')
    .replace(/\*\*/g, '^')
    .replace(/[\s$\\{}()[\]_]/g, '')
    .replace(/([xyzabctuvwn])\d+=/g, '$1=')
    .replace(/\*/g, '');
  const finalMarker = /(?:final answer|yakuniy javob|yakuniy natija|the solution is|javob\s*:|natija\s*:)/gi;
  let match: RegExpExecArray | null;
  let finalStart = -1;
  while ((match = finalMarker.exec(answer)) !== null) finalStart = match.index + match[0].length;
  if (finalStart < 0) return false;
  const answerText = normalized(answer.slice(finalStart));
  return computation.canonical.every(variants => variants.some(value => {
    const candidate = normalized(value);
    return candidate.length > 0 && answerText.includes(candidate);
  }));
}
