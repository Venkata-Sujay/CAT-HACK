/**
 * Equipment photography.
 *
 * Real machine photos, downloaded into `public/equipment/` rather than
 * hotlinked -- a demo that loses its images because the venue WiFi dropped is
 * worse than one that never had them. Licences and sources are in
 * `public/equipment/CREDITS.md`.
 *
 * Two sizes per type: `card` (800x500) for panels and detail headers, `thumb`
 * (240x150) for table rows and list items. Serving the 800px file into a 40px
 * table cell 50 times is the difference between a snappy fleet table and a
 * 7 MB screen.
 */

import type { ProductType } from "./types";

const SLUG: Record<string, string> = {
  EXCAVATOR: "excavator",
  BULLDOZER: "bulldozer",
  CRANE: "crane",
  GRADER: "grader",
  WHEEL_LOADER: "wheel_loader",
};

export function equipmentImage(
  type: ProductType | string | null | undefined,
  size: "card" | "thumb" = "card",
): string {
  const slug = SLUG[String(type ?? "").toUpperCase()] ?? "excavator";
  return size === "thumb" ? `/equipment/${slug}-thumb.jpg` : `/equipment/${slug}.jpg`;
}

export const HERO_IMAGE = "/equipment/hero.jpg";

/** Short spec line shown under an equipment photo. Purely descriptive copy. */
export const TYPE_BLURB: Record<string, string> = {
  EXCAVATOR: "Tracked · bucket · trenching and bulk earthmoving",
  BULLDOZER: "Tracked · blade · site clearing and grading",
  CRANE: "Lattice boom · lifting and placement",
  GRADER: "Six-wheel · moldboard · road profiling and finishing",
  WHEEL_LOADER: "Articulated · bucket · stockpile and load-out",
};

export const ALL_PRODUCT_TYPES: ProductType[] = [
  "EXCAVATOR",
  "BULLDOZER",
  "CRANE",
  "GRADER",
  "WHEEL_LOADER",
];
