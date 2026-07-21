import type { CancellationRule } from "@/lib/api";

// Mirrors the band logic in CancellationTimeline.buildSegments: rules sorted
// by descending threshold, the first one at or below the actual number of
// days before check-in wins. Cancelling with fewer days left than the
// smallest threshold falls through to a 0% refund.
export function applicableRefundPercentage(rules: CancellationRule[], daysBeforeCheckIn: number): number {
  if (rules.length === 0) return 0;
  const sorted = [...rules].sort((a, b) => b.days_before_checkin - a.days_before_checkin);
  const applicable = sorted.find((rule) => daysBeforeCheckIn >= rule.days_before_checkin);
  return applicable ? applicable.refund_percentage : 0;
}
