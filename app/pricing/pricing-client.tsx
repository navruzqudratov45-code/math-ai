'use client';

import Link from 'next/link';
import { ArrowLeft, ArrowRight, BookOpenCheck, Check } from 'lucide-react';

const included = [
  'Kuniga 100 ta AI yechimi',
  'Batafsil nazariya va qadam-baqadam tushuntirish',
  'SymPy hisob-kitobi va tekshiruvi',
  'Matematika, geometriya va diskret matematika',
  'Rasm orqali masala yuborish',
  'Hisobda yechimlar tarixi va 1 000 tagacha saqlangan masala',
];

export default function PricingClient() {
  return <main className="workspace-page pricing-page"><header className="workspace-header"><Link className="brand" href="/"><span className="brand-mark"><span>∑</span><i/></span><span>Math<span className="brand-ai">AI</span></span></Link><div className="workspace-actions"><Link href="/" className="workspace-link"><ArrowLeft size={15}/> Bosh sahifa</Link></div></header><section className="pricing-main"><div className="account-kicker">MATHAI · 100% BEPUL</div><h1>Barcha imkoniyatlar hamma uchun.</h1><p className="pricing-lead">Hech qanday to‘lov yoki obuna talab qilinmaydi. Bepul hisob bilan yechimlarni saqlang va tarixga istalgan vaqtda qayting.</p><article className="subscription-card free-access-card"><div className="subscription-name"><BookOpenCheck size={15}/> TO‘LIQ BEPUL KIRISH</div><div className="subscription-price">0 so‘m<small>· barcha imkoniyatlar ochiq</small></div><ul>{included.map((feature,index)=><li key={index}><Check size={14}/>{feature}</li>)}</ul><Link className="account-submit" href="/#solver">Masala yechishni boshlash<ArrowRight size={15}/></Link></article></section><footer className="app-signature">MathAI · <strong className="creator-brand">toshniyozov.dev</strong></footer></main>;
}
