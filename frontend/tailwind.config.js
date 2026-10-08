/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'Segoe UI', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'Consolas', 'monospace'],
      },
      colors: {
        brand: { 50: '#eef4ff', 100: '#dbe6fe', 400: '#6690f8', 500: '#3b6ef5', 600: '#2a56db', 700: '#2243b0', 900: '#14234f' },
      },
    },
  },
  plugins: [],
}
