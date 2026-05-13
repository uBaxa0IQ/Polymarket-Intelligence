import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        base:   '#0a0a0f',
        panel:  '#111118',
        card:   '#1a1a24',
        border: '#2a2a3a',
        accent: '#6366f1',
        text:   '#e2e8f0',
        muted:  '#64748b',
        green:  '#22c55e',
        red:    '#ef4444',
        yellow: '#f59e0b',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
} satisfies Config
