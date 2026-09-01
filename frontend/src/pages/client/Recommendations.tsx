/** Client recommendations -- capacity suggestions with a request action. */

import { PageHeader } from "../../components/AppShell";
import { RecommendationCard } from "../../components/RecommendationCard";
import { Card, EmptyState, ErrorState, Spinner } from "../../components/ui";
import { useRecommendations } from "../../lib/queries";

export function ClientRecommendations() {
  const { data, isLoading, error, refetch } = useRecommendations();

  const open = (data ?? []).filter((r) => r.status === "OPEN");
  const actioned = (data ?? []).filter((r) => r.status !== "OPEN");

  return (
    <div className="p-6">
      <PageHeader
        title="Recommendations"
        subtitle="Capacity and utilization suggestions based on your recent operations"
      />

      {isLoading && <Card><Spinner label="Loading recommendations…" /></Card>}
      {error && <Card><ErrorState error={error} onRetry={() => refetch()} /></Card>}

      {data && data.length === 0 && (
        <Card>
          <EmptyState
            title="No recommendations right now"
            hint="Recommendations appear when utilization patterns suggest an action — for example when your fleet runs consistently near capacity."
          />
        </Card>
      )}

      {open.length > 0 && (
        <div className="space-y-3 mb-6">
          {open.map((recommendation) => (
            <RecommendationCard key={recommendation.id} recommendation={recommendation} />
          ))}
        </div>
      )}

      {actioned.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-2.5">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-faint">
              Already actioned
            </h2>
            <div className="flex-1 h-px bg-border" />
          </div>
          <div className="space-y-3 opacity-70">
            {actioned.map((recommendation) => (
              <RecommendationCard key={recommendation.id} recommendation={recommendation} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
