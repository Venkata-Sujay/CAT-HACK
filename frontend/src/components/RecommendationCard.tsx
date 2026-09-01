/**
 * Recommendation card.
 *
 * Recommendations carry their `rationale` -- the numbers behind the suggestion.
 * A recommendation a user cannot interrogate is a recommendation they will not
 * trust, so the reasoning is shown, not hidden behind a "why?" link.
 */

import { productTypeLabel } from "../lib/format";
import { useDismissRecommendation, useRequestRecommendation } from "../lib/queries";
import { useAuth } from "../lib/auth";
import type { Recommendation } from "../lib/types";

const TYPE_LABEL: Record<string, string> = {
  REQUEST_MORE_ASSETS: "Capacity",
  PREPOSITION_ASSET: "Pre-positioning",
  RETURN_UNDERUTILIZED: "Under-utilised",
  SCHEDULE_MAINTENANCE: "Maintenance",
  REASSIGN_OPERATOR: "Operator",
};

export function RecommendationCard({ recommendation }: { recommendation: Recommendation }) {
  const { isClient } = useAuth();
  const request = useRequestRecommendation();
  const dismiss = useDismissRecommendation();

  const isRequested = recommendation.status === "REQUESTED";
  const canRequest = isClient && recommendation.type === "REQUEST_MORE_ASSETS" && !isRequested;

  return (
    <div className="card p-4 relative overflow-hidden">
      <div className="absolute left-0 top-0 bottom-0 w-[3px] bg-accent" />

      <div className="pl-2">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap mb-1.5">
              <span className="chip bg-accent/10 text-accent border border-accent/25">
                {TYPE_LABEL[recommendation.type] ?? recommendation.type}
              </span>
              {recommendation.product_type && (
                <span className="chip bg-elevated text-muted border border-border normal-case tracking-normal">
                  {productTypeLabel(recommendation.product_type)}
                </span>
              )}
              {recommendation.site_code && (
                <span className="chip bg-elevated text-muted border border-border">
                  {recommendation.site_code}
                </span>
              )}
              {isRequested && (
                <span className="chip bg-ok/15 text-ok border border-ok/25">Requested</span>
              )}
            </div>

            <h3 className="text-sm font-medium text-ink">{recommendation.title}</h3>
            <p className="text-xs text-muted mt-1.5 leading-relaxed">{recommendation.description}</p>

            {recommendation.rationale.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5">
                {recommendation.rationale.map((line, index) => {
                  // "Label: value" splits into a compact stat pair.
                  const [label, ...rest] = line.split(":");
                  const value = rest.join(":").trim();
                  return (
                    <div key={index} className="text-2xs">
                      <span className="text-faint">{label}</span>
                      {value && <span className="text-ink ml-1.5 tnum font-medium">{value}</span>}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {recommendation.quantity > 0 && (
            <div className="text-right shrink-0">
              <div className="text-2xl font-semibold text-accent tnum leading-none">
                {recommendation.quantity}
              </div>
              <div className="text-2xs text-faint mt-1">units</div>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 mt-3.5">
          {canRequest && (
            <button
              className="btn-primary text-xs py-1.5"
              disabled={request.isPending}
              onClick={() => request.mutate(recommendation.id)}
            >
              {request.isPending ? "Submitting…" : "Request more assets"}
            </button>
          )}
          {isRequested && (
            <span className="text-xs text-ok">
              Request submitted — the rental company has been notified.
            </span>
          )}
          {!isRequested && (
            <button
              className="btn-ghost text-xs py-1.5"
              disabled={dismiss.isPending}
              onClick={() => dismiss.mutate(recommendation.id)}
            >
              Dismiss
            </button>
          )}
        </div>

        {request.error && (
          <p className="text-xs text-danger mt-2">{(request.error as Error).message}</p>
        )}
      </div>
    </div>
  );
}
