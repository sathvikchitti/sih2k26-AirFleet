/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ops: {
          bg: '#0b0c0d',
          panel: '#121416',
          panel2: '#181b1e',
          border: '#25292e',
          muted: '#878e95',
          accent: '#8fe388',
          accent2: '#7aa6c8',
          ok: '#8fe388',
          warn: '#f2a33a',
          crit: '#f0524a'
        }
      },
      fontFamily: {
        display: ['Big Shoulders', 'Barlow Condensed', 'Arial Narrow', 'sans-serif'],
        sans: ['Instrument Sans', 'Inter', 'system-ui', 'Segoe UI', 'sans-serif'],
        mono: ['Geist Mono', 'JetBrains Mono', 'Consolas', 'monospace']
      }
    }
  },
  plugins: []
}
