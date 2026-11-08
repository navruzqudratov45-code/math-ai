import { NextRequest, NextResponse } from 'next/server';
import { aiResultMatchesSympy, computeWithSympy, type SympyResult } from '../../../lib/math-engine';
import { dbCall, requireRequestUser } from '../../../lib/auth';

export const runtime = 'nodejs';
export const maxDuration = 60;

const MAX_TEXT_LENGTH = 12_000;
const MAX_IMAGE_BYTES = 6 * 1024 * 1024;
const MAX_BODY_BYTES = 7 * 1024 * 1024;
const RATE_WINDOW_MS = 60_000;
const RATE_LIMIT = 8;
const requestsByIp = new Map<string, { count: number; resetAt: number }>();
const allowedTypes = new Set(['image/jpeg', 'image/png', 'image/webp']);

function error(message: string, status: number) {
  return NextResponse.json({ error: message }, { status });
}

function logSupervisorEvent(event: { module: 'sympy' | 'openrouter'; severity: 'warning' | 'critical'; code: string; message: string }) {
  void dbCall({ op: 'supervisor_log', ...event }).catch(() => {});
}

function getNetworkFailure(cause: unknown) {
  const root = cause && typeof cause === 'object' ? cause as Record<string, unknown> : {};
  const nested = root.cause && typeof root.cause === 'object' ? root.cause as Record<string, unknown> : {};
  const children = Array.isArray(nested.errors) ? nested.errors : [];
  const child = children.find(item => item && typeof item === 'object' && typeof (item as Record<string, unknown>).code === 'string') as Record<string, unknown> | undefined;
  const code = [nested.code, child?.code, root.code].find(value => typeof value === 'string') as string | undefined;
  const name = typeof root.name === 'string' ? root.name : 'Error';

  if (code === 'EACCES' || code === 'EPERM') {
    return { code, logReason: 'outbound connection denied', userMessage: 'Server OpenRouter tarmog‘iga chiqolmadi (EACCES). Server jarayoni uchun tashqi HTTPS ulanishiga ruxsat bering.' };
  }
  if (name === 'TimeoutError' || code === 'ETIMEDOUT' || code === 'ESOCKETTIMEDOUT') {
    return { code: code ?? 'TIMEOUT', logReason: 'request timed out', userMessage: 'OpenRouter javobi belgilangan vaqtda kelmadi. Birozdan keyin qayta urinib ko‘ring.' };
  }
  if (code === 'ENOTFOUND' || code === 'EAI_AGAIN') {
    return { code, logReason: 'DNS resolution failed', userMessage: 'OpenRouter manzili topilmadi (DNS). Serverning DNS yoki tarmoq sozlamasini tekshiring.' };
  }
  if (code === 'ECONNREFUSED' || code === 'ECONNRESET' || code === 'ENETUNREACH') {
    return { code, logReason: 'connection unavailable', userMessage: `OpenRouter bilan aloqa uzildi (${code}). Server tarmog‘ini tekshirib, qayta urinib ko‘ring.` };
  }
  return { code: code ?? name, logReason: 'unclassified connection failure', userMessage: 'OpenRouter bilan aloqa o‘rnatilmadi. Server jurnallarida xavfsiz diagnostika kodi qayd etildi.' };
}

function checkRateLimit(ip: string) {
  const now = Date.now();
  if (requestsByIp.size > 10_000) {
    requestsByIp.forEach((entry, address) => { if (entry.resetAt <= now) requestsByIp.delete(address); });
  }
  const current = requestsByIp.get(ip);
  if (!current || current.resetAt <= now) {
    requestsByIp.set(ip, { count: 1, resetAt: now + RATE_WINDOW_MS });
    return true;
  }
  current.count += 1;
  return current.count <= RATE_LIMIT;
}

function isAllowedImage(file: File) {
  const extension = file.name.split('.').pop()?.toLowerCase();
  const matchingExtension = (file.type === 'image/jpeg' && ['jpg', 'jpeg'].includes(extension ?? ''))
    || (file.type === 'image/png' && extension === 'png')
    || (file.type === 'image/webp' && extension === 'webp');
  return allowedTypes.has(file.type) && matchingExtension;
}

const solutionInstructions = `You are MathAI, a careful mathematics tutor. Solve the user's actual problem; never invent missing conditions or claim certainty when the input is ambiguous. For geometry problems, explain in simple Uzbek regardless of the language of the input; for other subjects, use the language used by the user (if mixed or unclear, use simple Uzbek). For image input, transcribe the mathematical notation first and explicitly ask a concise clarification question instead of solving if any essential part is unreadable. For a well-posed problem, use these headings and include all of them: Problem identification; Given information; Relevant theory (definitions and applicable theorems); Formulas (define variables); Step-by-step solution (show calculations and explain why each operation/formula is used); Final answer; Verification (substitute/check or explain if verification is not possible); Learning summary. Use correct LaTeX enclosed in $...$ or $$...$$. Cover geometry proofs and calculations when requested. If data is insufficient, say exactly what is missing. Do not make up a practice problem unless the user asks for one. Solve every numbered or lettered sub-problem through its final item; do not stop after the first. Keep each item's steps concise and clearly label all items. For Boolean truth-table vectors, interpret f(x̃ⁿ)=(α₀…α₂ⁿ⁻¹) in lexicographic order from (0,…,0) to (1,…,1); vector length is 2ⁿ (length 8 means x₁,x₂,x₃). For xᵢ, compare the first and second halves of each block of size 2ⁿ⁻ⁱ⁺¹ (x₁ compares 4-bit halves, x₂ 2-bit halves within each 4-bit block, x₃ adjacent bits for n=3). Equal halves throughout means the argument is soxta/fiktiv; any unequal pair means it is muhim/essential. Report a simplified Boolean expression and analyze every supplied vector.`;

const operationNames: Record<string, string> = {
  simplify: 'Algebraik soddalashtirish', expand: 'Qavslarni ochish', factor: 'Ko‘paytuvchilarga ajratish',
  solve: 'Tenglamani yechish', derivative: 'Hosila', integral: 'Integral', limit: 'Limit',
  determinant: 'Determinant', matrix: 'Matritsa amali', boolean_vector: 'Boolean funksiya vektori',
};

export async function POST(request: NextRequest) {
  const contentLength = Number(request.headers.get('content-length') ?? 0);
  if (!contentLength) return error('So‘rov hajmini aniqlab bo‘lmadi. Qayta urinib ko‘ring.', 411);
  if (contentLength > MAX_BODY_BYTES) return error('So‘rov hajmi 7 MB dan oshmasligi kerak.', 413);

  const forwardedFor = request.headers.get('x-forwarded-for');
  const ip = forwardedFor?.split(',')[0]?.trim() || request.headers.get('x-real-ip') || 'unknown';
  if (!checkRateLimit(ip)) return error('So‘rovlar limiti tugadi. Bir daqiqadan so‘ng qayta urinib ko‘ring.', 429);

  let problem = '';
  let selectedCategory: 'Matematika' | 'Geometriya' | null = null;
  let imagePart: { type: 'image_url'; image_url: { url: string } } | undefined;
  try {
    const contentType = request.headers.get('content-type') ?? '';
    if (contentType.includes('multipart/form-data')) {
      const form = await request.formData();
      const text = form.get('problem');
      if (typeof text === 'string') problem = text.trim();
      const category = form.get('category');
      if (category === 'Matematika' || category === 'Geometriya') selectedCategory = category;
      const image = form.get('image');
      if (image instanceof File && image.size > 0) {
        if (!isAllowedImage(image)) return error('Faqat JPG, PNG yoki WEBP rasmlar qabul qilinadi.', 415);
        if (image.size > MAX_IMAGE_BYTES) return error('Rasm hajmi 6 MB dan oshmasligi kerak.', 413);
        const bytes = Buffer.from(await image.arrayBuffer());
        const isJpeg = image.type === 'image/jpeg' && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff;
        const isPng = image.type === 'image/png' && bytes.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]));
        const isWebp = image.type === 'image/webp' && bytes.toString('ascii', 0, 4) === 'RIFF' && bytes.toString('ascii', 8, 12) === 'WEBP';
        if (!isJpeg && !isPng && !isWebp) return error('Rasm faylining mazmuni tanlangan formatga mos kelmadi.', 415);
        const base64 = bytes.toString('base64');
        imagePart = { type: 'image_url', image_url: { url: `data:${image.type};base64,${base64}` } };
      }
    } else if (contentType.includes('application/json')) {
      const body = await request.json();
      if (typeof body.problem === 'string') problem = body.problem.trim();
      if (body.category === 'Matematika' || body.category === 'Geometriya') selectedCategory = body.category;
    } else {
      return error('So‘rov JSON yoki rasmli multipart/form-data bo‘lishi kerak.', 415);
    }
  } catch {
    return error('So‘rovni o‘qib bo‘lmadi. Matn yoki rasmni qayta tekshiring.', 400);
  }

  if (problem.length > MAX_TEXT_LENGTH) return error('Masala matni 12 000 belgidan oshmasligi kerak.', 413);
  if (!problem && !imagePart) return error('Masala matnini kiriting yoki rasm yuklang.', 400);

  const signedInUser = await requireRequestUser(request);
  const key = process.env.OPENROUTER_API_KEY;
  const model = process.env.OPENROUTER_MODEL;
  const startedAt = Date.now();
  let requestDomain = selectedCategory === 'Geometriya' || /geometry|geometri|uchburchak|aylana|radius|kub|silindr|konus|shar|piramida/i.test(problem) ? 'geometry' : 'math';
  const inputType = imagePart ? (problem ? 'mixed' : 'image') : 'text';
  const logAiRequest = async (status: number, errorCode?: string) => {
    try { await dbCall({ op: 'log_request', userId: signedInUser?.id ?? null, model, domain: requestDomain, status, latencyMs: Date.now() - startedAt, errorCode, inputType }); }
    catch (cause) { console.error('AI usage log unavailable:', cause instanceof Error ? cause.message.slice(0, 140) : 'unknown error'); }
  };
  if (!key || !model) {
    await logAiRequest(503, 'solver_not_configured');
    return error('AI solver sozlanmagan. Server muhitida OPENROUTER_API_KEY va OPENROUTER_MODEL qiymatlarini kiriting.', 503);
  }
  let quota: {
    allowed: boolean;
    reason?: string;
    used: number;
    limit: number;
    remaining: number;
    plan: string;
    usageDate: string;
    resetsAt: number;
    premiumExtendedExplanations: boolean;
    premiumPriorityRouting: boolean;
  } = { allowed: true, used: 0, limit: 100, remaining: 100, plan: 'free', usageDate: '', resetsAt: 0,
    premiumExtendedExplanations: true, premiumPriorityRouting: true };
  if (signedInUser) {
    try { quota = await dbCall({ op: 'reserve_usage', userId: signedInUser.id, hasText: Boolean(problem), hasImage: Boolean(imagePart) }); }
    catch (cause) {
      console.error('Daily quota reservation failed:', cause instanceof Error ? cause.message.slice(0, 140) : 'unknown error');
      return error('Kunlik foydalanish limitini tekshirib bo‘lmadi. Birozdan keyin qayta urinib ko‘ring.', 503);
    }
    if (!quota.allowed) {
      await logAiRequest(429, quota.reason === 'global_limit' ? 'global_daily_limit' : 'daily_limit');
      const message = quota.reason === 'global_limit'
        ? 'Platformaning bugungi umumiy bepul AI limiti tugadi. Yangi limit yarim tunda UTC bo‘yicha tiklanadi.'
        : `Bugungi bepul limit (${quota.limit} ta so‘rov) tugadi. Yangi limit yarim tunda UTC bo‘yicha tiklanadi.`;
      return NextResponse.json({ error: message, usage: quota }, { status: 429 });
    }
  } else {
    try {
      const globalCheck = await dbCall<{ allowed: boolean; used: number; limit: number; resetsAt: number }>({ op: 'check_global_limit' });
      if (!globalCheck.allowed) {
        await logAiRequest(429, 'global_daily_limit');
        return NextResponse.json({ error: 'Platformaning bugungi umumiy bepul AI limiti tugadi. Yangi limit yarim tunda UTC bo‘yicha tiklanadi.' }, { status: 429 });
      }
    } catch (cause) {
      console.error('Global limit check failed:', cause instanceof Error ? cause.message.slice(0, 140) : 'unknown error');
    }
  }
  const content: Array<{ type: 'text'; text: string } | { type: 'image_url'; image_url: { url: string } }> = [];
  if (problem) content.push({ type: 'text', text: `User's problem:\n${problem}` });
  if (imagePart) content.push(imagePart);
  if (!problem && imagePart) content.unshift({ type: 'text', text: 'Read and solve the problem in the attached image. Transcribe notation faithfully; ask for clarification if unclear.' });
  if (selectedCategory) content.unshift({ type: 'text', text: `The user selected the ${selectedCategory === 'Geometriya' ? 'geometry' : 'mathematics'} category. ${selectedCategory === 'Geometriya' ? 'Treat this as a geometry request, including when the problem is provided only as an image. Apply relevant geometric theory and explain in simple Uzbek.' : 'Treat this as a mathematics request.'}` });

  let computation: SympyResult | null = null;
  if (problem) {
    try {
      const result = await computeWithSympy(problem);
      if (result.supported) computation = result;
    } catch (cause) {
      console.error('SymPy engine unavailable:', cause instanceof Error ? cause.message.slice(0, 180) : 'unknown error');
      logSupervisorEvent({ module: 'sympy', severity: 'warning', code: 'sympy_problem_verification_failed', message: 'Masala uchun SymPy tekshiruvi bajarilmadi.' });
    }
  }
  const computationContext = computation
    ? `\n\nTRUSTED SYMPY COMPUTATION (independently computed; treat this as authoritative):\nDomain: ${computation.domain ?? 'algebra'}\nOperation: ${operationNames[computation.operation ?? ''] ?? computation.operation}\nExpression: ${computation.input}\n${computation.theory ? `Theory: ${computation.theory}\n` : ''}${computation.formula ? `Formula: ${computation.formula}\n` : ''}Exact result: ${computation.result}\nLaTeX result: $${computation.latex}$\nCalculation outline:\n${computation.steps?.map((step, index) => `${index + 1}. ${step}`).join('\n')}\nUse the exact result above in your final answer, show the supplied calculation outline, and do not contradict the SymPy result. Explain in simple language.\n`
    : '';
  if (computation?.domain === 'geometry') requestDomain = 'geometry';

  try {
    const systemPrompt = solutionInstructions + '\n\nTeaching quality: provide intuition, derive key formulas briefly, verify the result when possible, mention relevant edge cases, and do not skip important transformations.' + computationContext;
    let messages: Array<{ role: string; content: unknown }> = [{ role: 'system', content: systemPrompt }, { role: 'user', content }];
    let answer = '';
    let payload: any = null;
    let upstream: Response | null = null;
    let finishReason: string | null = null;
    const completionDeadline = Date.now() + 55_000;
    for (let attempt = 0; attempt < 5; attempt += 1) {
      const remainingMs = completionDeadline - Date.now();
      if (remainingMs < 1500) break;
      upstream = await fetch('https://openrouter.ai/api/v1/chat/completions', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${key}`,
          'Content-Type': 'application/json',
          'HTTP-Referer': process.env.OPENROUTER_SITE_URL || 'http://localhost:3000',
          'X-Title': 'MathAI',
        },
        body: JSON.stringify({ model, temperature: 0.2, max_tokens: 8192, provider: { sort: 'throughput' }, messages }),
        signal: AbortSignal.timeout(Math.min(40_000, remainingMs)),
      });
      payload = await upstream.json().catch(() => null);
      if (!upstream.ok) break;
      const choice = payload?.choices?.[0];
      const segment = choice?.message?.content;
      if (typeof segment !== 'string' || !segment.trim()) { await logAiRequest(502, 'empty_answer'); return error('AI xizmatidan yaroqli javob kelmadi. Qayta urinib ko‘ring.', 502); }
      answer += (answer ? '\n' : '') + segment.trim();
      finishReason = typeof choice.finish_reason === 'string' ? choice.finish_reason : null;
      if (finishReason !== 'length') break;
      messages = [
        { role: 'system', content: systemPrompt },
        { role: 'user', content },
        { role: 'assistant', content: answer },
        { role: 'user', content: 'Continue exactly from where your previous response stopped. Complete every remaining numbered or lettered sub-problem, including its final answer and verification. Do not repeat already completed sections.' },
      ];
    }
    if (!upstream) { await logAiRequest(502, 'completion_deadline'); return error('Yechimni to‘liq tayyorlash uchun vaqt yetmadi. Masalani kichikroq qismlarga bo‘lib qayta yuboring.', 502); }
    if (!upstream.ok) {
      let providerReason = '';
      const rawProviderError = payload?.error?.metadata?.raw;
      if (typeof rawProviderError === 'string') {
        try {
          const details = JSON.parse(rawProviderError);
          const message = details?.error?.message;
          if (typeof message === 'string') providerReason = message.slice(0, 240).replaceAll(key, '[redacted]');
        } catch { /* Provider errors are not always JSON. */ }
      }
      console.error('OpenRouter request failed:', upstream.status, payload?.error?.code ?? 'no-code', payload?.error?.message ?? 'unknown error', payload?.error?.metadata?.provider_name ?? 'provider unavailable', providerReason);
      if (upstream.status >= 500) logSupervisorEvent({ module: 'openrouter', severity: 'critical', code: 'openrouter_upstream_5xx', message: `OpenRouter upstream ${upstream.status} holatini qaytardi.` });
      await logAiRequest(upstream.status, String(payload?.error?.code ?? 'upstream_error').slice(0, 80));
      if (upstream.status === 401 || upstream.status === 403) return error('AI xizmati kalitni qabul qilmadi. OPENROUTER_API_KEY sozlamasini tekshiring.', 502);
      if (upstream.status === 429) return error('AI xizmati vaqtincha band. Birozdan keyin urinib ko‘ring.', 503);
      return error('AI solver hozir javob bera olmadi. Keyinroq qayta urinib ko‘ring.', 502);
    }
    if (finishReason === 'length') { await logAiRequest(502, 'completion_truncated'); return error('Masala yechimi javob hajmi chegarasiga yetdi. Barcha bandlarni yechish uchun masalani kichikroq qismlarga bo‘lib qayta yuboring.', 502); }
    if (!computation && imagePart) {
      const transcription = answer.match(/(?:equation|tenglama)[^$\n]{0,80}\$([^$]*=[^$]*)\$/i)?.[1];
      if (transcription) {
        try {
          const result = await computeWithSympy(transcription);
          if (result.supported) computation = result;
        } catch (cause) {
          console.error('SymPy image verification unavailable:', cause instanceof Error ? cause.message.slice(0, 180) : 'unknown error');
          logSupervisorEvent({ module: 'sympy', severity: 'warning', code: 'sympy_image_verification_failed', message: 'Rasmdan o‘qilgan ifoda uchun SymPy tekshiruvi bajarilmadi.' });
        }
      }
    }
    if (computation) {
      if (computation.canonical?.length) computation.aiVerified = aiResultMatchesSympy(answer, computation);
      if (computation.supported && computation.aiVerified === false) logSupervisorEvent({ module: 'sympy', severity: 'warning', code: 'ai_sympy_result_mismatch', message: 'AI javobining yakuniy natijasi SymPy natijasi bilan mos kelmadi.' });
    }
    await logAiRequest(200);
    if (signedInUser) {
      try { await dbCall({ op: 'save_problem', userId: signedInUser.id, prompt: problem || '[Yuklangan rasm orqali masala]', answer: answer.trim(), domain: computation?.domain === 'geometry' ? 'geometry' : requestDomain }); }
      catch (cause) { console.error('Problem history save unavailable:', cause instanceof Error ? cause.message.slice(0, 140) : 'unknown error'); }
    }
    return NextResponse.json({ answer: answer.trim(), model, computation });
  } catch (cause) {
    const failure = getNetworkFailure(cause);
    console.error('OpenRouter connection failed:', JSON.stringify({ code: failure.code, reason: failure.logReason }));
    await logAiRequest(502, String(failure.code).slice(0, 80));
    return error(failure.userMessage, 502);
  }
}
