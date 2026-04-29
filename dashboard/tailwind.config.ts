import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1f1c19",
        paper: "#f6f0e8",
        sand: "#ece2d6",
        mist: "#fffaf3",
        accent: "#c7683f",
        accentSoft: "#ead0c2",
        olive: "#50624d",
        border: "#d4c8bb",
        success: "#3f7a53",
        warning: "#b98339",
        danger: "#aa4a42",
      },
      boxShadow: {
        card: "0 24px 60px rgba(69, 51, 34, 0.08)",
      },
      fontFamily: {
        sans: ["Manrope", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
      backgroundImage: {
        grid: "radial-gradient(circle at 1px 1px, rgba(72, 57, 43, 0.08) 1px, transparent 0)",
      },
    },
  },
  plugins: [],
} satisfies Config;
