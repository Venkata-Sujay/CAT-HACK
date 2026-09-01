/**
 * Equipment type strip -- five photo cards, one per machine class.
 *
 * This exists because a fleet dashboard made only of numbers gives a viewer
 * nothing to anchor on. "12 EXCAVATOR" is a row in a table; a photograph of an
 * excavator with 12 on it is a fleet. It is also the fastest route from the
 * dashboard into a filtered fleet view, which is the click people actually
 * want to make from here.
 *
 * The bar under each photo is deployed / available / maintenance in one line,
 * so utilisation of that class is legible without reading any digits.
 */

import { useNavigate } from "react-router-dom";
import { productTypeLabel } from "../lib/format";
import { TYPE_BLURB, equipmentImage } from "../lib/equipment";
import type { ProductTypeStat } from "../lib/types";

export function FleetStrip({
  stats,
  basePath = "/company/fleet",
}: {
  stats: ProductTypeStat[];
  basePath?: string;
}) {
  const navigate = useNavigate();

  // A class the viewer holds none of is not information. On the company side
  // every class has stock so nothing is dropped; on a client's dashboard it
  // removes the "Crane 0" card for equipment they never rented.
  const visible = stats.filter((stat) => stat.total > 0);
  if (visible.length === 0) return null;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
      {visible.map((stat) => {
        const total = Math.max(1, stat.total);
        const pct = (n: number) => `${(n / total) * 100}%`;
        return (
          <button
            key={stat.product_type}
            onClick={() => navigate(`${basePath}?type=${stat.product_type}`)}
            className="card overflow-hidden text-left group hover:border-accent/50 transition-colors"
            title={`${stat.total} ${productTypeLabel(stat.product_type)}s — click to filter the fleet`}
          >
            <div className="relative h-[86px] overflow-hidden bg-base">
              <img
                src={equipmentImage(stat.product_type, "card")}
                alt={productTypeLabel(stat.product_type)}
                loading="lazy"
                className="w-full h-full object-cover opacity-80 group-hover:opacity-100
                           group-hover:scale-[1.04] transition-all duration-300"
              />
              {/* Gradient so the count stays readable over any photo. */}
              <div className="absolute inset-0 bg-gradient-to-t from-surface via-surface/45 to-transparent" />
              <div className="absolute bottom-1.5 left-2.5 right-2.5 flex items-end justify-between gap-2">
                <span className="text-[11px] font-semibold text-ink leading-tight drop-shadow">
                  {productTypeLabel(stat.product_type)}
                </span>
                <span className="text-xl font-semibold text-ink tnum leading-none drop-shadow">
                  {stat.total}
                </span>
              </div>
            </div>

            <div className="px-2.5 py-2">
              <div className="flex h-1.5 rounded-full overflow-hidden bg-base border border-border/50">
                <div className="bg-accent" style={{ width: pct(stat.deployed) }} />
                <div className="bg-neutral/60" style={{ width: pct(stat.warehouse) }} />
                <div className="bg-warn" style={{ width: pct(stat.maintenance) }} />
              </div>
              {/* Depot and workshop counts are dropped when zero: a client has
                  no depot, and "0 depot" on every card is pure noise. */}
              <div className="flex items-center justify-between mt-1.5 text-2xs text-faint">
                <span className="tnum">
                  <span className="text-accent font-semibold">{stat.deployed}</span> out
                </span>
                {stat.warehouse > 0 && (
                  <span className="tnum">
                    <span className="text-muted font-semibold">{stat.warehouse}</span> depot
                  </span>
                )}
                {stat.maintenance > 0 && (
                  <span className="tnum">
                    <span className="text-warn font-semibold">{stat.maintenance}</span> shop
                  </span>
                )}
                {stat.active > 0 && (
                  <span className="tnum">
                    <span className="text-ok font-semibold">{stat.active}</span> running
                  </span>
                )}
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}

/**
 * A single equipment photo with a caption. Used as the header of the asset
 * drawer and the check-in/out panel, where knowing WHAT you are looking at
 * before you read the code speeds the whole interaction up.
 */
export function EquipmentBanner({
  productType,
  model,
  className = "",
  height = 128,
  children,
}: {
  productType: string;
  model?: string | null;
  className?: string;
  height?: number;
  children?: React.ReactNode;
}) {
  return (
    <div className={`relative overflow-hidden bg-base ${className}`} style={{ height }}>
      <img
        src={equipmentImage(productType, "card")}
        alt={productTypeLabel(productType)}
        className="w-full h-full object-cover opacity-70"
      />
      <div className="absolute inset-0 bg-gradient-to-r from-surface via-surface/60 to-surface/10" />
      <div className="absolute inset-0 p-4 flex flex-col justify-end">
        <div className="label text-[10px] mb-0.5">{productTypeLabel(productType)}</div>
        <div className="text-sm text-ink font-medium leading-tight">
          {model ?? TYPE_BLURB[productType.toUpperCase()] ?? ""}
        </div>
        {children}
      </div>
    </div>
  );
}
