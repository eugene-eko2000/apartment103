import type { CancellationRule, Plan } from "@/lib/api";

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

// When two or more plans would charge the same cancellation fee *right now*
// for this check-in (i.e. applicableRefundPercentage resolves to the same
// value, even if their underlying rule schedules differ elsewhere), only the
// cheapest of them is worth showing as a distinct rate option — the rest are
// strictly worse choices with no upside for these dates. Ties keep the first
// plan encountered.
export function cheapestPerCancellationFee(plans: Plan[], daysBeforeCheckIn: number): Plan[] {
  const feeOf = (plan: Plan) => applicableRefundPercentage(plan.cancellation_policy.rules, daysBeforeCheckIn);
  const cheapestForFee = new Map<number, Plan>();
  for (const plan of plans) {
    const fee = feeOf(plan);
    const current = cheapestForFee.get(fee);
    if (!current || plan.price_ratio < current.price_ratio) {
      cheapestForFee.set(fee, plan);
    }
  }
  return plans.filter((plan) => cheapestForFee.get(feeOf(plan)) === plan);
}
