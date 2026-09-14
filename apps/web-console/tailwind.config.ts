import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './features/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#10221e',
        forest: '#17463d',
        lime: '#d8f36a',
        mist: '#f4f6f1',
      },
      boxShadow: { panel: '0 12px 40px rgba(16, 34, 30, 0.08)' },
    },
  },
  plugins: [],
}

export default config
