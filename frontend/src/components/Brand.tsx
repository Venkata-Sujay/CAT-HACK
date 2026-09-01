/**
 * Caterpillar branding.
 *
 * The official logo is NOT committed to this repo. `CatBadge` probes for
 * `/brand/cat-logo.svg`, then `/brand/cat-logo.png`, and falls back to a built
 * wordmark when neither is present -- so the layout is identical either way and
 * dropping the official asset in is a zero-code change. See
 * `frontend/public/brand/README.md`.
 */

import { useEffect, useState } from "react";

type Probe = "loading" | "svg" | "png" | "none";

const CANDIDATES: { key: Exclude<Probe, "loading" | "none">; src: string }[] = [
  { key: "svg", src: "/brand/cat-logo.svg" },
  { key: "png", src: "/brand/cat-logo.png" },
];

// Module-level cache: the probe runs once per page load, not once per mount.
// Six <CatBadge>s on a screen must not fire six HEAD requests each render.
let cached: Probe | null = null;
const waiters: ((p: Probe) => void)[] = [];

function probeLogo(): Promise<Probe> {
  if (cached) return Promise.resolve(cached);
  return new Promise((resolve) => {
    waiters.push(resolve);
    if (waiters.length > 1) return; // a probe is already in flight

    const settle = (result: Probe) => {
      cached = result;
      waiters.splice(0).forEach((fn) => fn(result));
    };

    let index = 0;
    const tryNext = () => {
      if (index >= CANDIDATES.length) return settle("none");
      const candidate = CANDIDATES[index++];
      const img = new Image();
      img.onload = () => settle(candidate.key);
      img.onerror = tryNext;
      img.src = candidate.src;
    };
    tryNext();
  });
}

export function useCatLogo(): string | null {
  const [state, setState] = useState<Probe>(cached ?? "loading");
  useEffect(() => {
    let alive = true;
    probeLogo().then((result) => alive && setState(result));
    return () => {
      alive = false;
    };
  }, []);
  if (state === "svg") return "/brand/cat-logo.svg";
  if (state === "png") return "/brand/cat-logo.png";
  return null;
}

/**
 * The CAT mark. `height` is in px; width flexes.
 * `tone="light"` for dark backgrounds (default), `"dark"` on yellow.
 */
export function CatBadge({
  height = 22,
  tone = "light",
  className = "",
}: {
  height?: number;
  tone?: "light" | "dark";
  className?: string;
}) {
  const logo = useCatLogo();

  if (logo) {
    return (
      <img
        src={logo}
        alt="Caterpillar"
        style={{ height }}
        className={`w-auto object-contain ${className}`}
      />
    );
  }

  // Fallback wordmark: the CAT typographic lockup -- heavy condensed letters on
  // yellow with the triangular accent under the A. Recognisably in the family
  // without reproducing the trademarked mark itself.
  const fg = tone === "dark" ? "#0A0B0D" : "#0A0B0D";
  return (
    <span
      className={`inline-flex items-center ${className}`}
      style={{ height }}
      aria-label="Caterpillar"
    >
      <svg viewBox="0 0 96 34" style={{ height }} className="w-auto">
        <rect width="96" height="34" rx="3" fill="#FFCD11" />
        <text
          x="8"
          y="26"
          fontFamily="Barlow Condensed, Inter, sans-serif"
          fontSize="26"
          fontWeight="700"
          letterSpacing="1.5"
          fill={fg}
        >
          CAT
        </text>
        <path d="M60 26 L70 26 L65 15 Z" fill={fg} />
        <rect x="74" y="23" width="16" height="3" fill={fg} />
      </svg>
    </span>
  );
}

/**
 * Corner attribution strip.
 *
 * Lives in the sidebar footer rather than floating over the viewport. A fixed
 * bottom-right ribbon sat on top of whatever the page had in its own bottom
 * right corner -- the last row of the clients table, the last card in the
 * action queue -- and no amount of pointer-events tuning fixes text covering
 * text. The sidebar foot is still the edge of the page and collides with
 * nothing.
 */
export function CatCorner() {
  return (
    <div className="flex items-center gap-2 px-2.5 py-2 rounded-lg border border-border/70 bg-base/60">
      <CatBadge height={14} />
      <span className="label text-[8px] leading-none">Hackathon Build</span>
    </div>
  );
}
