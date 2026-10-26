/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#090d16",
        surface: "#111827",
        surfaceBorder: "#1f2937",
        selfUser: "#38bdf8",
        tier1: "#10b981",
        tier2: "#f59e0b",
        tier3: "#f43f5e",
        organization: "#64748b",
        pathHighlight: "#06b6d4",
      },
    },
  },
  plugins: [],
};
