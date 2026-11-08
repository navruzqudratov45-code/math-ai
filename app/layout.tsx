import type { Metadata } from 'next';
import './globals.css';
import 'katex/dist/katex.min.css';

export const metadata: Metadata = { title: 'MathAI — Matematikani tushunib yeching', description: 'Matematika va geometriyani bosqichma-bosqich o‘rganing.' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="uz"><body>{children}</body></html>;
}
