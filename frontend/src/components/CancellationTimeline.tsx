"use client";

import type { CancellationRule } from "@/lib/api";

interface Segment {
  lowerDays: number;
  upperDays: number | null;
  refundPercentage: number;
}

type StatusTier = "good" | "warning" | "serious" | "critical";

const TIER_BY_REFUND = (refund: number): StatusTier => {
  if (refund >= 0.75) return "good";
  if (refund >= 0.4) return "warning";
  if (refund > 0) return "serious";
  return "critical";
};

// Fixed status scale, same steps in light/dark (mode-invariant).
const FILL_BY_TIER: Record<StatusTier, string> = {
  good: "#0ca30c",
  warning: "#fab219",
  serious: "#ec835a",
  critical: "#d03b3b",
};

// Dark ink clears WCAG contrast on good/warning/serious; critical reads better with white.
// (computed against the fill hexes above, not eyeballed)
const INK_BY_TIER: Record<StatusTier, string> = {
  good: "#0b0b0b",
  warning: "#0b0b0b",
  serious: "#0b0b0b",
  critical: "#ffffff",
};

function buildSegments(rules: CancellationRule[]): Segment[] {
  if (rules.length === 0) return [];

  const sorted = [...rules].sort((a, b) => b.days_before_checkin - a.days_before_checkin);
  const raw: Segment[] = sorted.map((rule, i) => ({
    lowerDays: rule.days_before_checkin,
    upperDays: i === 0 ? null : sorted[i - 1].days_before_checkin,
    refundPercentage: rule.refund_percentage,
  }));

  const lastDays = sorted[sorted.length - 1].days_before_checkin;
  if (lastDays > 0) {
    raw.push({ lowerDays: 0, upperDays: lastDays, refundPercentage: 0 });
  }

  // Merge adjacent bands that share the same refund rate into one visual segment.
  const merged: Segment[] = [];
  for (const seg of raw) {
    const prev = merged[merged.length - 1];
    if (prev && prev.refundPercentage === seg.refundPercentage) {
      prev.lowerDays = seg.lowerDays;
    } else {
      merged.push({ ...seg });
    }
  }
  return merged;
}

// Highest day threshold a policy's rules reach — callers combine this across
// every plan being shown side by side so all timelines share one day scale.
export function getMaxThresholdDays(rules: CancellationRule[]): number {
  return rules.reduce((max, rule) => Math.max(max, rule.days_before_checkin), 0);
}

// Padding so the open-ended top segment doesn't visually end flush at the bar's edge.
export function getVisualMaxDays(maxThresholdDays: number): number {
  return maxThresholdDays > 0 ? Math.ceil(maxThresholdDays * 1.3) : 1;
}

interface CancellationTimelineProps {
  rules: CancellationRule[];
  visualMaxDays: number;
  checkInLabel: string;
  refundRuleTemplate: string;
  daysBeforeCheckInLabel: string;
}

export function CancellationTimeline({
  rules,
  visualMaxDays,
  checkInLabel,
  refundRuleTemplate,
  daysBeforeCheckInLabel,
}: CancellationTimelineProps) {
  const segments = buildSegments(rules);
  if (segments.length === 0) return null;

  const visualMax = visualMaxDays > 0 ? visualMaxDays : 1;
  const leftPercent = (days: number) => ((visualMax - days) / visualMax) * 100;

  const allTicks = segments.slice(0, -1).map((seg, i) => ({
    key: `boundary-${seg.lowerDays}`,
    label: i === 0 ? `${seg.lowerDays}+` : `${seg.lowerDays}`,
    position: leftPercent(seg.lowerDays),
  }));
  allTicks.push({ key: "check-in", label: checkInLabel, position: 100 });

  // Drop labels that would crowd their neighbor — walk right to left so the
  // fixed check-in anchor always wins over an interior tick squeezed against it.
  const MIN_TICK_GAP_PERCENT = 18;
  const ticks: typeof allTicks = [];
  for (let i = allTicks.length - 1; i >= 0; i--) {
    const tick = allTicks[i];
    const nextKept = ticks[0];
    if (!nextKept || nextKept.position - tick.position >= MIN_TICK_GAP_PERCENT) {
      ticks.unshift(tick);
    }
  }

  return (
    <div className="mt-2.5">
      <div className="flex h-6 w-full gap-0.5" role="img" aria-label={segments.map((seg) =>
        refundRuleTemplate
          .replace("{percent}", String(Math.round(seg.refundPercentage * 100)))
          .replace("{days}", String(seg.lowerDays))
      ).join("; ")}>
        {segments.map((seg, i) => {
          const upper = seg.upperDays ?? visualMax;
          const widthPercent = ((upper - seg.lowerDays) / visualMax) * 100;
          const tier = TIER_BY_REFUND(seg.refundPercentage);
          const percentLabel = `${Math.round(seg.refundPercentage * 100)}%`;
          const title = refundRuleTemplate
            .replace("{percent}", String(Math.round(seg.refundPercentage * 100)))
            .replace("{days}", String(seg.lowerDays));
          return (
            <div
              key={i}
              title={title}
              className={`flex items-center justify-center overflow-hidden text-[10px] font-semibold ${
                i === 0 ? "rounded-l-md" : ""
              } ${i === segments.length - 1 ? "rounded-r-md" : ""}`}
              style={{
                width: `${widthPercent}%`,
                backgroundColor: FILL_BY_TIER[tier],
                color: INK_BY_TIER[tier],
              }}
            >
              {widthPercent >= 12 && <span>{percentLabel}</span>}
            </div>
          );
        })}
      </div>
      <div className="relative mt-1 h-3.5 text-[10px] text-gray-400 dark:text-gray-500">
        {ticks.map((tick) => {
          const translate = tick.position <= 0 ? "0%" : tick.position >= 100 ? "-100%" : "-50%";
          return (
            <span
              key={tick.key}
              className="absolute whitespace-nowrap"
              style={{ left: `${tick.position}%`, transform: `translateX(${translate})` }}
            >
              {tick.label}
            </span>
          );
        })}
      </div>
      <p className="mt-2.5 text-[9px] uppercase tracking-wide text-gray-400 dark:text-gray-500">
        {daysBeforeCheckInLabel}
      </p>
    </div>
  );
}
