/** @type {import('tailwindcss').Config} */
export default {
  content: ["./src/renderer/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Henosync design system
        base: "#0D0F12",
        surface1: "#141619",
        surface2: "#1C1F24",
        surface3: "#252A31",
        border: "#2A2F38",
        accent: "#4A9EFF",
        success: "#3DD68C",
        warning: "#F5A623",
        danger: "#F05252",
        muted: "#8B95A3",
      },
      fontFamily: {
        sans: ["Inter", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
};
