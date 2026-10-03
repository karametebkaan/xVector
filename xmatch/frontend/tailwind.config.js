/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        dark: {
          950: '#070a0f',
          900: '#0d1117',
          850: '#161b22',
          800: '#21262d',
          700: '#30363d',
          600: '#484f58',
        },
        brand: {
          blue: '#58a6ff',
          green: '#3fb950',
          yellow: '#d29922',
          purple: '#bc8cff',
          red: '#f85149',
        }
      }
    },
  },
  plugins: [],
}
