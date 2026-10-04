/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: 'var(--canvas)', ink: 'var(--ink)', inksoft: 'var(--ink-soft)',
        card: 'var(--card)', line: 'var(--line)', tint: 'var(--tint)',
        brand: 'var(--green)', coral: 'var(--coral)', blue: 'var(--blue)', plum: 'var(--plum)'
      },
      fontFamily: {
        disp: ['"Bricolage Grotesque"', 'sans-serif'],
        body: ['Inter', '"Plus Jakarta Sans"', 'sans-serif'],
        num: ['"Space Grotesk"', 'monospace']
      },
      borderRadius: { xl2: '20px' }
    }
  },
  plugins: []
}
