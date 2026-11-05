import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "var(--canvas)",
        bg: "var(--bg)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        ink: "var(--text)",
        muted: "var(--muted)",
        line: "var(--border)",
        ok: "var(--ok)",
        "ok-bg": "var(--ok-bg)",
        warn: "var(--warn)",
        "warn-bg": "var(--warn-bg)",
        bad: "var(--bad)",
        "bad-bg": "var(--bad-bg)",
        info: "var(--info)",
        "info-bg": "var(--info-bg)",
        chrome: "var(--chrome)",
        "chrome-2": "var(--chrome-2)",
        blue: "#1769FF",
        cyan: "#39C7F4",
        success: "#16A879",
        warning: "#F2A33A",
        danger: "#E85A67",
        graphite: "#111B2C",
        deep: "#14243A",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "Segoe UI", "sans-serif"],
        display: ["var(--font-grotesk)", "var(--font-inter)", "Segoe UI", "sans-serif"],
        mono: ["var(--font-mono)", "Consolas", "monospace"],
      },
      boxShadow: {
        console: "0 24px 60px rgba(17, 27, 44, 0.16)",
      },
    },
  },
  plugins: [],
};

export default config;
