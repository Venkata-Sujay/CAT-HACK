/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // ---------------------------------------------------------------
        // Caterpillar industrial palette.
        //
        // Two rules hold the whole system together:
        //   1. The greys are warm-neutral, not blue. Blue-grey plus yellow
        //      reads as "generic dark dashboard"; a warm charcoal reads like
        //      painted steel, which is what this product actually lives on.
        //   2. Yellow is BRAND and PRIMARY ACTION only. It is never a status.
        //      Status is green / amber / red, so a yellow thing on screen is
        //      always something you can click, never something that is wrong.
        // ---------------------------------------------------------------
        base: "#0A0B0D",       // page
        surface: "#141619",    // cards
        elevated: "#1C1F24",   // raised panels, table hover
        hover: "#252930",
        border: "#282C33",
        borderlight: "#363B44",

        ink: "#F2F4F7",
        muted: "#98A0AD",
        faint: "#697384",

        // Caterpillar yellow (Pantone 109 equivalent).
        accent: "#FFCD11",
        accentdim: "#C79B00",
        accentwash: "#3A2F00",

        ok: "#3DD68C",
        okdim: "#12432B",
        info: "#5B9DFF",
        warn: "#F5A524",
        warndim: "#5C3A00",
        danger: "#F0555A",
        dangerdim: "#5C1A1D",
        neutral: "#6B7688",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        // Machine identifiers and live numbers. Monospace stops asset codes
        // from looking like prose and stops digits jittering on every poll.
        mono: ["JetBrains Mono", "SFMono-Regular", "Consolas", "monospace"],
        // Condensed uppercase for panel labels -- the signage voice used on
        // real plant equipment.
        display: ["Barlow Condensed", "Inter", "system-ui", "sans-serif"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      boxShadow: {
        card: "0 1px 2px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.03)",
        raised: "0 12px 32px -8px rgba(0,0,0,0.7)",
        glow: "0 0 0 1px rgba(255,205,17,0.35), 0 6px 20px -6px rgba(255,205,17,0.25)",
      },
      backgroundImage: {
        // Hazard stripe. Used as a 4px accent rail on the primary panel and
        // on critical alerts -- the one piece of visual language that comes
        // straight off real plant equipment.
        hazard:
          "repeating-linear-gradient(135deg, #FFCD11 0 8px, #0A0B0D 8px 16px)",
        "hazard-danger":
          "repeating-linear-gradient(135deg, #F0555A 0 8px, #0A0B0D 8px 16px)",
      },
      animation: {
        "pulse-dot": "pulse-dot 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fade-in 0.2s ease-out",
        "slide-in": "slide-in 0.22s cubic-bezier(0.16, 1, 0.3, 1)",
        "rise": "rise 0.35s cubic-bezier(0.16, 1, 0.3, 1) both",
        "sweep": "sweep 2.4s linear infinite",
      },
      keyframes: {
        "pulse-dot": {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.3", transform: "scale(0.82)" },
        },
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "slide-in": {
          from: { transform: "translateX(100%)" },
          to: { transform: "translateX(0)" },
        },
        rise: {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        sweep: {
          from: { backgroundPosition: "0 0" },
          to: { backgroundPosition: "32px 0" },
        },
      },
    },
  },
  plugins: [],
};
