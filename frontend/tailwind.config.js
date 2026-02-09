/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'claude': {
          50: '#fef7f0',
          100: '#feeee0',
          200: '#fcd9b8',
          300: '#f9be85',
          400: '#f59950',
          500: '#f27d2d',
          600: '#e36320',
          700: '#bc4c1c',
          800: '#963e1e',
          900: '#79351c',
          950: '#41190c',
        },
      },
      fontFamily: {
        'mono': ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
}
