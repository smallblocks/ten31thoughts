/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: '#1a1a2e', light: '#16213e', accent: '#e94560' },
        surface: '#16161a',
        border: '#2a2a30',
        'text-primary': '#e8e8ea',
        'text-secondary': '#888892',
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'monospace'],
        serif: ['"IBM Plex Serif"', 'serif'],
      },
    },
  },
  plugins: [],
}
