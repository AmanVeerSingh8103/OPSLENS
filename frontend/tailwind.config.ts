import type { Config } from "tailwindcss";
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 950: "#07070b", 900: "#0b0b11", 850: "#0f0f17", 800: "#14141e", 700: "#1c1c29", 600: "#2a2a3b" },
        accent: { DEFAULT: "#7c6cf6", soft: "#a79bff", blue: "#4f8cff" },
        ok: "#34d399", bad: "#f87171", warn: "#fbbf24",
      },
      fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"], mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"] },
      boxShadow: { panel: "0 1px 0 0 rgba(255,255,255,0.03) inset, 0 8px 24px -12px rgba(0,0,0,0.6)" },
    },
  },
  plugins: [],
};
export default config;
