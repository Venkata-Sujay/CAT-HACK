/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Industrial control-tower palette. Deliberately desaturated so the
        // status colours below are the only saturated things on screen -- an
        // operator's eye should go straight to what is wrong.
        base: "#0B0E13",
        surface: "#12161D",
        elevated: "#1A1F28",
        hover: "#212734",
        border: "#242B38",
        borderlight: "#2E3644",

        ink: "#E8ECF3",
        muted: "#8D97AA",
        faint: "#5C6678",

        // Industrial amber. Reserved for the brand and primary actions.
        accent: "#FFB020",
        accentdim: "#B87C13",

        ok: "#22C55E",
        okdim: "#166534",
        info: "#3B82F6",
        warn: "#F59E0B",
        warndim: "#78350F",
        danger: "#EF4444",
        dangerdim: "#7F1D1D",
        neutral: "#64748B",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        // Asset codes are machine identifiers and read better monospaced.
        mono: ["JetBrains Mono", "SFMono-Regular", "Consolas", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      boxShadow: {
        card: "0 1px 2px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.02)",
        raised: "0 8px 24px -6px rgba(0,0,0,0.6)",
      },
      animation: {
        "pulse-dot": "pulse-dot 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fade-in 0.2s ease-out",
        "slide-in": "slide-in 0.22s cubic-bezier(0.16, 1, 0.3, 1)",
      },
      keyframes: {
        "pulse-dot": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.35" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "slide-in": {
          from: { transform: "translateX(100%)" },
          to: { transform: "translateX(0)" },
        },
      },
    },
  },
  plugins: [],
};
