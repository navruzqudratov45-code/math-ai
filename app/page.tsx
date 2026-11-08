'use client';

import { type ReactNode, useRef, useState } from 'react';
import { ArrowDown, ArrowRight, ArrowUpRight, Check, CircleHelp, ImagePlus, Lightbulb, Menu, Search, Shapes, Sparkles, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import FormulaLibrary from './formula-library';

type Category = 'Matematika' | 'Geometriya';
type DiagramData = { kind: string; labels?: Record<string, string>; points?: [number, number][] };
type Computation = { supported?: boolean; operation?: string; domain?: string; input?: string; result?: string; latex?: string; formula?: string; theory?: string; steps?: string[]; verification?: string; aiVerified?: boolean; diagram?: DiagramData };
const examples = [
  { category: 'Matematika' as Category, label: 'Algebra', text: '2x² − 5x − 3 = 0 tenglamani yeching', symbol: 'x²', tone: 'purple' },
  { category: 'Matematika' as Category, label: 'Funksiyalar', text: 'f(x) = 3x + 2 funksiyaning x = 4 dagi qiymatini toping', symbol: 'ƒ', tone: 'blue' },
  { category: 'Geometriya' as Category, label: 'Uchburchaklar', text: 'Tomonlari 5, 12 va 13 bo‘lgan uchburchak yuzini toping', symbol: '△', tone: 'pink' },
  { category: 'Geometriya' as Category, label: 'Aylana', text: 'Radiusi 7 cm bo‘lgan aylananing yuzini hisoblang', symbol: '◯', tone: 'cyan' },
  { category: 'Matematika' as Category, label: 'Boolean funksiyalar', text: 'f(x) = (10101010) funksiyasining muhim va soxta argumentlarini toping', symbol: '01', tone: 'cyan' },
];

function Logo() { return <a href="#top" className="brand" aria-label="MathAI bosh sahifa"><span className="brand-mark"><span>∑</span><i /></span><span>Math<span className="brand-ai">AI</span></span></a>; }

function Header() {
  const [open, setOpen] = useState(false);
  return <header className="site-header"><div className="nav-wrap"><Logo /><button className="mobile-menu" onClick={() => setOpen(!open)} aria-label="Menyuni ochish">{open ? <X size={20} /> : <Menu size={20} />}</button><nav className={open ? 'nav-links open' : 'nav-links'}><a href="#solver" onClick={() => setOpen(false)}>Yechim topish</a><a href="#formulas" onClick={() => setOpen(false)}>Formulalar</a><a href="#features" onClick={() => setOpen(false)}>Imkoniyatlar</a><a href="#free" onClick={() => setOpen(false)}>100% bepul</a></nav><a className="nav-cta" href="/login">Hisobga kirish <ArrowUpRight size={15} /></a></div></header>;
}

function GeometryDiagram({ diagram }: { diagram: DiagramData }) {
  const labels = diagram.labels ?? {};
  const ink = '#b7a4ff';
  let figure: ReactNode;
  if (diagram.kind === 'coordinates' && diagram.points?.length) {
    const xs = diagram.points.map(point => point[0]), ys = diagram.points.map(point => point[1]);
    const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
    const toPoint = ([x, y]: [number, number]) => `${45 + (x - minX) / (maxX - minX || 1) * 230},${165 - (y - minY) / (maxY - minY || 1) * 125}`;
    const coords = diagram.points.map(toPoint);
    figure = <><path d="M22 165H296M45 185V18" className="diagram-axis" /><polyline points={coords.join(' ')} className="diagram-line" fill={diagram.points.length >= 3 ? 'rgba(139,112,222,.12)' : 'none'} />{diagram.points.map((point, i) => { const [x, y] = toPoint(point).split(',').map(Number); return <g key={i}><circle cx={x} cy={y} r="4" className="diagram-dot" /><text x={x + 7} y={y - 8} className="diagram-label">{labels[String.fromCharCode(65 + i)] ?? `(${point[0]}, ${point[1]})`}</text></g>; })}</>;
  } else if (diagram.kind === 'circle') {
    figure = <><circle cx="160" cy="102" r="65" className="diagram-fill" /><line x1="160" y1="102" x2="225" y2="102" className="diagram-stroke" /><circle cx="160" cy="102" r="3" fill={ink} /><text x="188" y="94" className="diagram-label">r = {labels.r}</text><text x="120" y="190" className="diagram-label">d = {labels.d}</text></>;
  } else if (diagram.kind === 'triangle' || diagram.kind === 'rightTriangle') {
    const right = diagram.kind === 'rightTriangle';
    figure = <><path d={right ? 'M58 170 L58 42 L270 170 Z' : 'M45 170 L152 32 L275 170 Z'} className="diagram-fill" />{right && <path d="M58 151 H77 V170" className="diagram-stroke" />}<text x="150" y="191" className="diagram-label">{labels.a ?? labels.b ?? ''}</text><text x="62" y="102" className="diagram-label">{labels.b ?? labels.h ?? ''}</text><text x="218" y="105" className="diagram-label">{labels.c ?? ''}</text><text x="36" y="32" className="diagram-label">{labels.A ?? ''}°</text><text x="263" y="32" className="diagram-label">{labels.B ?? ''}°</text><text x="146" y="25" className="diagram-label">{labels.C ? `${labels.C}°` : ''}</text></>;
  } else if (diagram.kind === 'cube' || diagram.kind === 'cuboid') {
    figure = <><path d="M72 74 L170 74 L170 170 L72 170 Z M72 74 L120 35 L218 35 L170 74 M170 74 L218 35 L218 132 L170 170 M72 170 L120 132 L218 132" className="diagram-fill diagram-wire" /><text x="105" y="190" className="diagram-label">{labels.l ?? labels.a ?? ''}</text><text x="224" y="88" className="diagram-label">{labels.h ?? ''}</text><text x="174" y="29" className="diagram-label">{labels.w ?? ''}</text></>;
  } else if (diagram.kind === 'cylinder') {
    figure = <><ellipse cx="160" cy="48" rx="72" ry="22" className="diagram-fill" /><path d="M88 48 V150 M232 48 V150" className="diagram-stroke" /><path d="M88 150 C88 178 232 178 232 150" className="diagram-stroke" /><path d="M88 150 C88 122 232 122 232 150" className="diagram-stroke diagram-hidden" /><line x1="160" y1="48" x2="217" y2="48" className="diagram-stroke" /><text x="184" y="42" className="diagram-label">r={labels.r}</text><text x="240" y="106" className="diagram-label">h={labels.h}</text></>;
  } else if (diagram.kind === 'cone') {
    figure = <><path d="M160 30 L88 151 M160 30 L232 151 M88 151 C88 123 232 123 232 151" className="diagram-stroke" /><path d="M88 151 C88 178 232 178 232 151" className="diagram-stroke" /><line x1="160" y1="30" x2="160" y2="151" className="diagram-dash" /><text x="166" y="102" className="diagram-label">h={labels.h}</text><text x="184" y="158" className="diagram-label">r={labels.r}</text></>;
  } else if (diagram.kind === 'sphere') {
    figure = <><circle cx="160" cy="102" r="70" className="diagram-fill" /><ellipse cx="160" cy="102" rx="70" ry="25" className="diagram-stroke" /><path d="M160 32 C120 50 120 154 160 172 M160 32 C200 50 200 154 160 172" className="diagram-stroke diagram-hidden" /><line x1="160" y1="102" x2="220" y2="67" className="diagram-stroke" /><text x="193" y="65" className="diagram-label">r={labels.r}</text></>;
  } else if (diagram.kind === 'prism') {
    figure = <><path d="M60 148 L110 58 L160 148 Z M115 170 L165 80 L215 170 Z M60 148 L115 170 M110 58 L165 80 M160 148 L215 170" className="diagram-fill diagram-wire" /><text x="223" y="123" className="diagram-label">h={labels.h}</text><text x="102" y="49" className="diagram-label">B={labels.B}</text></>;
  } else if (diagram.kind === 'pyramid') {
    figure = <><path d="M72 145 L160 168 L248 145 L160 125 Z M160 35 L72 145 M160 35 L160 168 M160 35 L248 145" className="diagram-fill diagram-wire" /><path d="M160 35 L160 145" className="diagram-dash" /><text x="166" y="97" className="diagram-label">h={labels.h}</text><text x="116" y="187" className="diagram-label">B={labels.B}</text></>;
  } else if (diagram.kind === 'polygon') {
    const n = Math.min(12, Math.max(3, Number(labels.n) || 6));
    const pts = Array.from({ length: n }, (_, i) => { const a = -Math.PI / 2 + i * 2 * Math.PI / n; return `${160 + 72 * Math.cos(a)},${102 + 72 * Math.sin(a)}`; }).join(' ');
    figure = <><polygon points={pts} className="diagram-fill" /><text x="135" y="190" className="diagram-label">n={labels.n}, a={labels.a}</text></>;
  } else if (diagram.kind === 'trapezoid') {
    figure = <><path d="M72 168 L108 48 L211 48 L248 168 Z" className="diagram-fill" /><text x="139" y="39" className="diagram-label">b={labels.b}</text><text x="144" y="190" className="diagram-label">a={labels.a}</text><text x="54" y="105" className="diagram-label">h={labels.h}</text></>;
  } else if (diagram.kind === 'parallelogram') {
    figure = <><path d="M95 160 L135 50 L265 50 L225 160 Z" className="diagram-fill" /><text x="154" y="182" className="diagram-label">a={labels.a}</text><text x="190" y="43" className="diagram-label">b={labels.b}</text><text x="115" y="101" className="diagram-label">h={labels.h}</text></>;
  } else if (diagram.kind === 'rhombus') {
    figure = <><path d="M160 32 L255 102 L160 172 L65 102 Z" className="diagram-fill" /><line x1="65" y1="102" x2="255" y2="102" className="diagram-dash" /><line x1="160" y1="32" x2="160" y2="172" className="diagram-dash" /><text x="167" y="98" className="diagram-label">a={labels.a}</text></>;
  } else {
    figure = <><rect x="76" y="47" width="168" height="112" rx="3" className="diagram-fill" /><text x="144" y="182" className="diagram-label">a={labels.a}</text><text x="249" y="105" className="diagram-label">b={labels.b}</text></>;
  }
  return <div className="geometry-diagram"><svg viewBox="0 0 320 210" role="img" aria-label="Masala shaklining chizmasi"><defs><linearGradient id="diagramGlow" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stopColor="#9173ed" stopOpacity=".2" /><stop offset="1" stopColor="#5485dd" stopOpacity=".06" /></linearGradient></defs>{figure}</svg><span>Chizma — o‘lchamlar masshtabda bo‘lmasligi mumkin</span></div>;
}

function Solver({ category, setCategory, text, setText }: { category: Category; setCategory: (c: Category) => void; text: string; setText: (s: string) => void }) {
  const [preview, setPreview] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState('');
  const [answer, setAnswer] = useState('');
  const [computation, setComputation] = useState<Computation | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  function selectFile(file?: File) {
    if (!file) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) { setNotice('Faqat JPG, PNG yoki WEBP rasmlar qabul qilinadi.'); return; }
    if (file.size > 6 * 1024 * 1024) { setNotice('Rasm hajmi 6 MB dan oshmasligi kerak.'); return; }
    if (preview) URL.revokeObjectURL(preview);
    setPreview(URL.createObjectURL(file)); setNotice(''); setAnswer(''); setComputation(null);
  }
  async function compressImageIfNeeded(file: File): Promise<File> {
    if (file.size <= 450 * 1024) return file;
    return new Promise(resolve => {
      const img = new Image();
      const url = URL.createObjectURL(file);
      img.onload = () => {
        URL.revokeObjectURL(url);
        const maxSide = 1600;
        let { width, height } = img;
        if (width > maxSide || height > maxSide) {
          if (width >= height) { height = Math.round((height * maxSide) / width); width = maxSide; }
          else { width = Math.round((width * maxSide) / height); height = maxSide; }
        }
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        if (!ctx) return resolve(file);
        ctx.drawImage(img, 0, 0, width, height);
        canvas.toBlob(blob => {
          if (!blob || blob.size >= file.size) return resolve(file);
          resolve(new File([blob], file.name.replace(/\.[^.]+$/, '') + '.jpg', { type: 'image/jpeg' }));
        }, 'image/jpeg', 0.86);
      };
      img.onerror = () => { URL.revokeObjectURL(url); resolve(file); };
      img.src = url;
    });
  }
  async function solve() {
    if (!text.trim() && !preview) { setNotice('Masala matnini kiriting yoki rasm yuklang.'); return; }
    setLoading(true); setNotice(''); setAnswer(''); setComputation(null);
    try {
      const body = new FormData();
      body.append('category', category);
      if (text.trim()) body.append('problem', text.trim());
      if (preview && inputRef.current?.files?.[0]) {
        const readyFile = await compressImageIfNeeded(inputRef.current.files[0]);
        body.append('image', readyFile);
      }
      const response = await fetch('/api/solve', { method: 'POST', headers: preview ? undefined : { 'Content-Type': 'application/json' }, body: preview ? body : JSON.stringify({ problem: text.trim(), category }) });
      const rawText = await response.text();
      let result: { answer?: string; error?: string; computation?: Computation } | null = null;
      try {
        result = JSON.parse(rawText);
      } catch {
        if (response.status === 502 || response.status === 503 || response.status === 504) {
          throw new Error(`Server hozir uyg‘onmoqda yoki javob kutish vaqti tugadi (HTTP ${response.status}). Iltimos, 10 soniya kutib qayta "Masalani yechish" tugmasini bosing.`);
        }
        throw new Error(`Serverdan kutilmagan javob keldi (HTTP ${response.status}). Sahifani yangilab qayta urinib ko‘ring.`);
      }
      if (!response.ok) throw new Error(result?.error || 'Masalani yechishda xatolik yuz berdi.');
      if (typeof result?.answer !== 'string' || !result.answer.trim()) throw new Error('AI xizmatidan yaroqli javob kelmadi.');
      setAnswer(result.answer);
      setComputation(result.computation?.supported ? result.computation : null);
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : 'So‘rov bajarilmadi. Qayta urinib ko‘ring.');
    } finally { setLoading(false); }
  }
  return <>
  <div className="solver-card">
    <div className="solver-head"><div><div className="eyebrow"><span className="live-dot" /> ISHLASHNI BOSHLANG</div><h2>Masalangizni kiriting</h2><p>Matn yozing yoki masala rasmini yuklang</p></div><div className="solver-spark"><Sparkles size={19} /></div></div>
    <div className="category-switch" role="tablist" aria-label="Masala turi">
      {(['Matematika', 'Geometriya'] as Category[]).map((item, i) => <button key={item} className={category === item ? 'category active' : 'category'} onClick={() => { setCategory(item); setAnswer(''); setComputation(null); }} role="tab" aria-selected={category === item}>{i === 0 ? <span className="math-icon">∑</span> : <Shapes size={17} />}{item}</button>)}
    </div>
    <div className="input-label-row"><label htmlFor="problem">Masala sharti</label><span>Ctrl + Enter ↵</span></div>
    <div className="problem-input-wrap"><textarea id="problem" value={text} onChange={e => { setText(e.target.value); setNotice(''); setAnswer(''); setComputation(null); }} placeholder={category === 'Matematika' ? 'Masalan: 2x + 5 = 17 tenglamani bosqichma-bosqich yeching…' : 'Masalan: Uchburchakning ikki tomoni 5 cm va 7 cm, ular orasidagi burchak 60°. Yuzini toping…'} rows={4} onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) solve(); }} />
      {preview && <div className="image-preview"><img src={preview} alt="Yuklangan masala rasmi" /><span>Masala rasmi yuklandi</span><button onClick={() => { URL.revokeObjectURL(preview); setPreview(null); if (inputRef.current) inputRef.current.value = ''; }} aria-label="Rasmni olib tashlash"><X size={15} /></button></div>}
      <div className="input-bottom"><span className="input-hint"><Lightbulb size={14} /> Har bir qadamni tushuntirib beramiz</span><button className="upload-button" type="button" onClick={() => inputRef.current?.click()}><ImagePlus size={16} /> Rasm yuklash</button><input ref={inputRef} type="file" accept="image/*" hidden onChange={e => selectFile(e.target.files?.[0])} /></div>
    </div>
    {notice && <div className="notice" role="status"><CircleHelp size={15} />{notice}</div>}
    <button className={loading ? 'solve-button loading' : 'solve-button'} onClick={solve} disabled={loading}>{loading ? <><span className="spinner" /> Yechim tayyorlanmoqda...</> : <>Masalani yechish <ArrowRight size={17} /></>}</button>
    <div className="trust-row"><span><Check size={13} /> Qadam-baqadam tushuntirish</span><span><Check size={13} /> O‘zbek tilida</span></div>
  </div>
  {computation && <section className="computation-card" aria-live="polite"><div className="answer-heading"><div><div className="eyebrow">SYMPY HISOB-KITOBI</div><h3>{computation.aiVerified ? 'AI javobi tekshirildi' : 'Mustaqil hisob natijasi'}</h3></div><span className={computation.aiVerified ? 'verification-mark verified' : 'verification-mark'}>{computation.aiVerified ? '✓ Mos' : '∑ Aniq'}</span></div>{computation.theory && <div className="computation-theory"><strong>Nazariya</strong><p>{computation.theory}</p></div>}{computation.formula && <div className="computation-formula"><strong>Formula</strong><ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>{`$$${computation.formula}$$`}</ReactMarkdown></div>}{computation.diagram && <GeometryDiagram diagram={computation.diagram} />}<div className="computation-result"><ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>{`**${computation.result ?? ''}**\n\n$$${computation.latex ?? ''}$$`}</ReactMarkdown></div>{computation.steps?.length ? <ol className="computation-steps">{computation.steps.map((step, index) => <li key={index}><ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>{step}</ReactMarkdown></li>)}</ol> : null}<p className="computation-note">{computation.aiVerified ? 'AI yechimining yakuniy natijasi SymPy natijasi bilan mos keldi.' : 'SymPy natijasi aniq hisoblandi; AI matnidagi javob formatini avtomatik moslashtirib bo‘lmadi.'}</p></section>}
  {answer && <section className="answer-card" aria-live="polite"><div className="answer-heading"><div><div className="eyebrow">MATHAI YECHIMI</div><h3>Masala yechimi</h3></div><Sparkles size={18} /></div><article className="markdown-answer"><ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>{answer}</ReactMarkdown></article></section>}
  </>;
}

function Examples({ onSelect }: { onSelect: (category: Category, text: string) => void }) { const [filter, setFilter] = useState<'Barchasi' | Category>('Barchasi'); const shown = examples.filter(e => filter === 'Barchasi' || e.category === filter); return <section className="section examples-section" id="examples"><div className="section-heading"><div><div className="eyebrow">SINAB KO‘RING</div><h2>Birinchi masalangizga<br /><span>g‘oya kerakmi?</span></h2></div><p>Misollardan birini tanlang — u masala maydoniga qo‘shiladi.</p></div><div className="filter-row">{(['Barchasi', 'Matematika', 'Geometriya'] as const).map(f => <button key={f} className={filter === f ? 'filter active' : 'filter'} onClick={() => setFilter(f)}>{f}</button>)}</div><div className="example-grid">{shown.map((e, i) => <button key={e.text} className="example-card" onClick={() => { onSelect(e.category, e.text); document.getElementById('solver')?.scrollIntoView({ behavior: 'smooth' }); }}><div className={'example-symbol ' + e.tone}>{e.symbol}</div><div className="example-meta"><span>{e.category}</span><span>0{i + 1}</span></div><div className="example-title">{e.label}</div><p>{e.text}</p><span className="example-action">Misolni sinash <ArrowUpRight size={15} /></span></button>)}</div></section>; }

const features = [
  { n: '01', icon: '∴', title: 'Faqat javob emas', text: 'Har bir yechim nima uchun shunday ekanini sodda izohlar bilan ochib beradi.' },
  { n: '02', icon: '▱', title: 'Geometriya ko‘rgazmali', text: 'Shakllar, teoremalar va chizmalar orqali fazoviy fikrlashni rivojlantiring.' },
  { n: '03', icon: '↗', title: 'O‘z sur’atingizda', text: 'Maktabdan universitetgacha — bilim darajangizga mos tushuntirishlar.' },
];
function Features() { return <section className="section features-section" id="features"><div className="section-heading"><div><div className="eyebrow">O‘RGANISHNING YANGI USULI</div><h2>Har bir qadamda<br /><span>yoningizdamiz.</span></h2></div><p>MathAI — masalani yechishdan ko‘ra ko‘proq. Bu matematikani chuqurroq tushunish yo‘li.</p></div><div className="features-grid">{features.map(f => <article className="feature-card" key={f.n}><div className="feature-top"><span className="feature-icon">{f.icon}</span><span>{f.n} / 03</span></div><h3>{f.title}</h3><p>{f.text}</p><div className="feature-line" /></article>)}</div><div className="learning-strip"><div className="learning-icon"><Lightbulb size={20} /></div><div><strong>Tushunish — haqiqiy natija.</strong><p>Ta’rif, formula, yechim, tekshiruv va eslab qolish uchun xulosa.</p></div><span className="strip-arrow"><ArrowRight size={17} /></span></div></section>; }

function FreePlatform() { return <section className="pricing-section" id="free"><div className="section pricing-inner"><div className="pricing-heading"><div className="eyebrow">HAMMA UCHUN OCHIQ</div><h2><span>100% Bepul</span><br/>Platforma.</h2><p>MathAI’ning barcha imkoniyatlaridan to‘lovsiz foydalaning.</p><a className="plan-link" href="#solver">Hozir masala yechish <ArrowRight size={14}/></a></div><article className="free-platform-card"><div className="plan-name"><Sparkles size={15}/> TO‘LIQ FOYDALANISH</div><p className="free-platform-lead">O‘rganish uchun kerak bo‘lgan barcha vositalar bir joyda.</p><ul><li><Check size={15}/> Bosqichma-bosqich AI yechimlari va chuqur izohlar</li><li><Check size={15}/> SymPy orqali mustaqil matematik tekshiruv</li><li><Check size={15}/> Geometriya chizmalari va hisob-kitoblar</li><li><Check size={15}/> Rasm yuklab masala yechish</li><li><Check size={15}/> Hisob ochganda yechimlar tarixi va saqlash</li><li><Check size={15}/> Kuniga 100 ta hisoblangan AI so‘rovi</li></ul><a className="plan-button premium-button" href="#solver">Bepul boshlash <ArrowRight size={15}/></a></article></div></section>; }

function Footer() { return <footer className="footer"><div className="footer-main"><Logo /><p>Matematikani tushunish uchun<br />yaratilgan aqlli yordamchi.</p><a className="back-top" href="#top">Yuqoriga <ArrowUpRight size={14} /></a></div><div className="footer-bottom"><span>© {new Date().getFullYear()} MathAI. Barcha huquqlar himoyalangan.</span><span>O‘rganing. Tushuning. O‘sing.</span><span>Created by <strong className="creator-brand">toshniyozov.dev</strong></span></div></footer>; }

function Hero({ category, setCategory, text, setText }: { category: Category; setCategory: (c: Category) => void; text: string; setText: (s: string) => void }) { return <section className="hero" id="top"><div className="hero-glow glow-one" /><div className="hero-glow glow-two" /><div className="hero-content"><div className="hero-badge"><Sparkles size={13} /> MATEMATIKANI TUSHUNIB O‘RGANING</div><h1>Javobni toping.<br /><span>Yechimni tushuning.</span></h1><p className="hero-copy">Matematika va geometriya masalalarini aniq, bosqichma-bosqich tushuntirishlar bilan yeching. Har bir formulada — yangi bilim.</p><div className="hero-points"><span><i>✦</i> Batafsil izohlar</span><span><i>✦</i> Shaxsiy repetitor</span><span><i>✦</i> O‘zbek tilida</span></div><a className="hero-link" href="#solver">Bepul sinab ko‘ring <ArrowDown size={15} /></a></div><div className="solver-wrap" id="solver"><div className="orbit orbit-a" /><div className="orbit orbit-b" /><Solver category={category} setCategory={setCategory} text={text} setText={setText} /></div><div className="hero-foot"><span>Har bir qadam — tushunishga bir qadam yaqin.</span><span className="foot-stars">✳ &nbsp; 01 / 03</span></div></section>; }

export default function Home() { const [category, setCategory] = useState<Category>('Matematika'); const [text, setText] = useState(''); const tryProblem = (c: Category, t: string) => { setCategory(c); setText(t); }; return <main><Header /><Hero category={category} setCategory={setCategory} text={text} setText={setText} /><Examples onSelect={tryProblem} /><FormulaLibrary onTryProblem={tryProblem} /><Features /><FreePlatform /><Footer /></main>; }

