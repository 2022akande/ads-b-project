import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        radar: {
          bg: "#0a0f14",
          panel: "#0f1822",
          grid: "#1b2a36",
          legit: "#39d98a",
          alert: "#ff4d4f",
          warn: "#ffb020",
        },
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
