'use client';

import { FormEvent, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, ArrowRight, Eye, EyeOff, LockKeyhole, Mail, UserRound } from 'lucide-react';

type Mode = 'login' | 'register' | 'forgot' | 'reset';
export default function AuthForm({ mode, resetToken = '' }: { mode: Mode; resetToken?: string }) {
  const [name, setName] = useState(''); const [email, setEmail] = useState(''); const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false); const [notice, setNotice] = useState(''); const [error, setError] = useState(''); const [showPassword, setShowPassword] = useState(false);
  const title = { login: 'Xush kelibsiz', register: 'Hisob yarating', forgot: 'Parolni tiklash', reset: 'Yangi parol o‘rnating' }[mode];
  const subtitle = { login: 'Masalalarni yechishda davom eting.', register: 'Matematika o‘rganish yo‘lingizni boshlang.', forgot: 'Emailingizga xavfsiz tiklash havolasini yuboramiz.', reset: 'Yangi parolingizni kamida 10 belgidan tanlang.' }[mode];
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('');
    const endpoint = { login: '/api/auth/login', register: '/api/auth/register', forgot: '/api/auth/password/forgot', reset: '/api/auth/password/reset' }[mode];
    const payload = mode === 'login' ? { email, password } : mode === 'register' ? { name, email, password } : mode === 'forgot' ? { email } : { token: resetToken, password };
    try {
      const response = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const result = await response.json(); if (!response.ok) throw new Error(result.error || 'So‘rov bajarilmadi.');
      if (mode === 'login' || mode === 'register') {
        const next = new URLSearchParams(window.location.search).get('next');
        const safeNext = next && next.startsWith('/') && !next.startsWith('//') && !next.startsWith('/\\') ? next : '/dashboard';
        window.location.assign(safeNext); return;
      }
      if (mode === 'forgot') setNotice(result.message);
      if (mode === 'reset') { setNotice('Parol yangilandi. Endi yangi parol bilan tizimga kiring.'); window.setTimeout(() => window.location.assign('/login'), 900); }
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Tarmoq xatosi. Qayta urinib ko‘ring.'); }
    finally { setBusy(false); }
  }
  return <main className="account-page"><div className="account-glow"/><div className="auth-shell"><Link href="/" className="brand auth-brand"><span className="brand-mark"><span>∑</span><i /></span><span>Math<span className="brand-ai">AI</span></span></Link><section className="auth-card"><Link href="/" className="back-link"><ArrowLeft size={15}/> Bosh sahifa</Link><div className="account-kicker">MATHAI HISOBI</div><h1>{title}</h1><p className="account-subtitle">{subtitle}</p>
  <form className="auth-form" onSubmit={submit}>
    {mode === 'register' && <label>Ism va familiya<span className="auth-input"><UserRound size={16}/><input required minLength={2} maxLength={80} autoComplete="name" value={name} onChange={e=>setName(e.target.value)} placeholder="Ismingiz"/></span></label>}
    {mode !== 'reset' && <label>Email manzili<span className="auth-input"><Mail size={16}/><input type="email" required maxLength={254} autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="siz@example.com"/></span></label>}
    {(mode === 'login' || mode === 'register' || mode === 'reset') && <label>{mode === 'reset' ? 'Yangi parol' : 'Parol'}<span className="auth-input"><LockKeyhole size={16}/><input type={showPassword?'text':'password'} required minLength={mode==='login'?1:10} maxLength={256} autoComplete={mode==='login'?'current-password':'new-password'} value={password} onChange={e=>setPassword(e.target.value)} placeholder={mode==='login'?'Parolingiz':'Kamida 10 belgi'}/><button type="button" className="show-password" onClick={()=>setShowPassword(!showPassword)} aria-label="Parolni ko‘rsatish">{showPassword?<EyeOff size={15}/>:<Eye size={15}/>}</button></span></label>}
    {error && <div className="account-error" role="alert">{error}</div>}{notice && <div className="account-notice" role="status">{notice}</div>}
    <button className="account-submit" disabled={busy}>{busy?'Kuting...': mode==='login'?'Tizimga kirish': mode==='register'?'Hisob yaratish':mode==='forgot'?'Tiklash havolasini yuborish':'Parolni yangilash'}<ArrowRight size={16}/></button>
  </form>
  {mode==='login' && <div className="auth-links"><Link href="/forgot-password">Parolni unutdingizmi?</Link><span>Hisob yo‘qmi? <Link href="/register">Ro‘yxatdan o‘ting</Link></span></div>}
  {mode==='register' && <p className="auth-legal">Hisob yaratib, MathAI’dan foydalanish shartlariga rozilik bildirasiz.</p>}
  {(mode==='forgot'||mode==='reset') && <div className="auth-links"><Link href="/login">Tizimga kirishga qaytish</Link></div>}
  </section><p className="auth-foot">© {new Date().getFullYear()} MathAI · Matematikani tushunib yeching · <strong className="creator-brand">toshniyozov.dev</strong></p></div></main>;
}
