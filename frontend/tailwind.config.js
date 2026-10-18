/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ops: {
          bg: '#0d1117',
          panel: '#151b24',
          panel2: '#1c2431',
          border: '#2a3444',
          muted: '#8b94a3',
          accent: '#d8a93d',
          accent2: '#4f9cf0',
          ok: '#3fb97f',
          warn: '#d8a93d',
          crit: '#e05c5c'
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'Consolas', 'monospace']
      }
    }
  },
  plugins: []
}
