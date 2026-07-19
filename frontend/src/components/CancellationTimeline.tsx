"use client";

import { format, subDays } from "date-fns";
import type { Locale as DateFnsLocale } from "date-fns";
import type { CancellationRule } from "@/lib/api";

interface Segment {
  lowerDays: number;
  upperDays: number | null;
  refundPercentage: number;
}

type RGB = [number, number, number];

// Gradient stops, same scale in light/dark (mode-invariant): red at 0% refund,
// through yellow at 50%, to green at 100%.
const GRADIENT_STOPS: { stop: number; rgb: RGB }[] = [
  { stop: 1, rgb: [12, 163, 12] }, // #0ca30c
  { stop: 0.5, rgb: [250, 178, 25] }, // #fab219
  { stop: 0, rgb: [208, 59, 59] }, // #d03b3b
];

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function fillForRefund(refund: number): RGB {
  const r = Math.min(1, Math.max(0, refund));
  const [hi, mid, lo] = GRADIENT_STOPS;
  const [from, to] = r >= mid.stop ? [mid, hi] : [lo, mid];
  const t = (r - from.stop) / (to.stop - from.stop);
  return [0, 1, 2].map((i) => lerp(from.rgb[i], to.rgb[i], t)) as RGB;
}

// WCAG relative luminance, used to pick whichever of black/white ink has the
// stronger contrast against a given gradient fill.
function relativeLuminance([r, g, b]: RGB): number {
  const linear = [r, g, b].map((c) => {
    const cs = c / 255;
    return cs <= 0.03928 ? cs / 12.92 : Math.pow((cs + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

function contrastRatio(l1: number, l2: number): number {
  const [lighter, darker] = l1 > l2 ? [l1, l2] : [l2, l1];
  return (lighter + 0.05) / (darker + 0.05);
}

function inkForFill(rgb: RGB): string {
  const fillLum = relativeLuminance(rgb);
  const blackContrast = contrastRatio(fillLum, 0);
  const whiteContrast = contrastRatio(fillLum, 1);
  return blackContrast >= whiteContrast ? "#0b0b0b" : "#ffffff";
}

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
  checkInDate: Date;
  dateLocale: DateFnsLocale;
  refundRuleTemplate: string;
  daysBeforeCheckInLabel: string;
}

export function CancellationTimeline({
  rules,
  visualMaxDays,
  checkInDate,
  dateLocale,
  refundRuleTemplate,
  daysBeforeCheckInLabel,
}: CancellationTimelineProps) {
  const segments = buildSegments(rules);
  if (segments.length === 0) return null;

  const visualMax = visualMaxDays > 0 ? visualMaxDays : 1;
  const leftPercent = (days: number) => ((visualMax - days) / visualMax) * 100;
  const dateLabel = (daysBefore: number) =>
    format(subDays(checkInDate, daysBefore), "MMM d", { locale: dateLocale });

  const allTicks = segments.slice(0, -1).map((seg) => ({
    key: `boundary-${seg.lowerDays}`,
    label: dateLabel(seg.lowerDays),
    position: leftPercent(seg.lowerDays),
  }));
  allTicks.push({ key: "check-in", label: dateLabel(0), position: 100 });

  // Every cancellation point must stay visible, so instead of dropping labels
  // that would crowd their neighbor, stagger them across two rows: each tick
  // takes the top row unless it's too close to the last tick placed there, in
  // which case it drops to the bottom row.
  const MIN_TICK_GAP_PERCENT = 16;
  const laneLastPosition: [number | null, number | null] = [null, null];
  const ticks = allTicks.map((tick) => {
    const lane =
      laneLastPosition[0] === null || tick.position - laneLastPosition[0] >= MIN_TICK_GAP_PERCENT ? 0 : 1;
    laneLastPosition[lane] = tick.position;
    return { ...tick, lane };
  });

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
          const fill = fillForRefund(seg.refundPercentage);
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
                backgroundColor: `rgb(${fill[0]}, ${fill[1]}, ${fill[2]})`,
                color: inkForFill(fill),
              }}
            >
              {widthPercent >= 12 && <span>{percentLabel}</span>}
            </div>
          );
        })}
      </div>
      <div className="relative mt-1 h-6 text-[10px] text-gray-400 dark:text-gray-500">
        {ticks.map((tick) => {
          const translate = tick.position <= 0 ? "0%" : tick.position >= 100 ? "-100%" : "-50%";
          return (
            <span
              key={tick.key}
              className="absolute whitespace-nowrap"
              style={{
                left: `${tick.position}%`,
                top: tick.lane === 0 ? 0 : "12px",
                transform: `translateX(${translate})`,
              }}
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
