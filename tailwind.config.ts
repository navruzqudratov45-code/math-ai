import type { Config } from 'tailwindcss';
const config: Config = { content: ['./app/**/*.{js,ts,jsx,tsx,mdx}', './components/**/*.{js,ts,jsx,tsx,mdx}'], theme: { extend: { colors: { ink: '#070812', panel: '#0D0F1C', violet: '#8B5CF6' }, fontFamily: { sans: ['var(--font-inter)', 'sans-serif'] } } }, plugins: [] };
export default config;
