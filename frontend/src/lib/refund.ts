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

// Two plans are only interchangeable if their cancellation terms match for
// every day remaining between now and check-in, not just today. Rule
// thresholds beyond daysBeforeCheckIn can never be reached (the guest is
// already past them at booking time), so they're excluded from the
// comparison; a plan is uniquely identified by the thresholds it can still
// hit plus the refund each one pays out.
function scheduleFingerprint(rules: CancellationRule[], daysBeforeCheckIn: number): string {
  return [...rules]
    .filter((rule) => rule.days_before_checkin <= daysBeforeCheckIn)
    .sort((a, b) => b.days_before_checkin - a.days_before_checkin)
    .map((rule) => `${rule.days_before_checkin}:${rule.refund_percentage}`)
    .join("|");
}

// When two or more plans have the exact same cancellation schedule for the
// remaining time until check-in, only the cheapest of them is worth showing
// as a distinct rate option — the rest are strictly worse choices with no
// upside for these dates. Ties keep the first plan encountered.
export function cheapestPerCancellationFee(plans: Plan[], daysBeforeCheckIn: number): Plan[] {
  const keyOf = (plan: Plan) => scheduleFingerprint(plan.cancellation_policy.rules, daysBeforeCheckIn);
  const cheapestForKey = new Map<string, Plan>();
  for (const plan of plans) {
    const key = keyOf(plan);
    const current = cheapestForKey.get(key);
    if (!current || plan.price_ratio < current.price_ratio) {
      cheapestForKey.set(key, plan);
    }
  }
  return plans.filter((plan) => cheapestForKey.get(keyOf(plan)) === plan);
}
