/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["Space Grotesk", "Inter", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      colors: {
        bg: {
          DEFAULT: "#070b14",
          panel: "#0d1424",
          panel2: "#111a2e",
          line: "#1a2540",
        },
        accent: {
          DEFAULT: "#ff6b35",
          glow: "#ff8c61",
          ember: "#ffa66b",
        },
        court: {
          DEFAULT: "#2563eb",
          deep: "#1d4ed8",
          glow: "#60a5fa",
        },
        win: "#00d4a4",
        loss: "#ff5470",
        warn: "#fbbf24",
      },
      backgroundImage: {
        "court-grid":
          "radial-gradient(circle at 50% 0%, rgba(37, 99, 235, 0.18), transparent 55%), radial-gradient(circle at 100% 100%, rgba(255, 107, 53, 0.12), transparent 50%)",
        "panel-glow":
          "linear-gradient(135deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.02) 50%, rgba(255,255,255,0.0) 100%)",
      },
      boxShadow: {
        glow: "0 0 30px rgba(37, 99, 235, 0.18)",
        ember: "0 0 22px rgba(255, 107, 53, 0.32)",
        card: "0 24px 60px -25px rgba(8, 13, 27, 0.85)",
      },
      keyframes: {
        "fade-in-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        pulse_dot: {
          "0%, 100%": { opacity: "0.6", transform: "scale(0.95)" },
          "50%": { opacity: "1", transform: "scale(1.1)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-700px 0" },
          "100%": { backgroundPosition: "700px 0" },
        },
      },
      animation: {
        "fade-in-up": "fade-in-up 0.45s ease-out both",
        "pulse-dot": "pulse_dot 1.6s ease-in-out infinite",
        shimmer: "shimmer 2.6s linear infinite",
      },
    },
  },
  plugins: [],
};
