"use client";

import { addDays, differenceInCalendarDays, format, subDays } from "date-fns";
import type { Locale as DateFnsLocale } from "date-fns";
import type { CancellationRule } from "@/lib/api";
import type { Currency } from "@/lib/currency-config";
import { formatPrice } from "@/lib/currency-config";

interface Segment {
  lowerDays: number;
  refundPercentage: number;
}

export type RGB = [number, number, number];

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

export function fillForRefund(refund: number): RGB {
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

export function inkForFill(rgb: RGB): string {
  const fillLum = relativeLuminance(rgb);
  const blackContrast = contrastRatio(fillLum, 0);
  const whiteContrast = contrastRatio(fillLum, 1);
  return blackContrast >= whiteContrast ? "#0b0b0b" : "#ffffff";
}

function buildSegments(rules: CancellationRule[]): Segment[] {
  if (rules.length === 0) return [];

  const sorted = [...rules].sort((a, b) => b.days_before_checkin - a.days_before_checkin);
  const raw: Segment[] = sorted.map((rule) => ({
    lowerDays: rule.days_before_checkin,
    refundPercentage: rule.refund_percentage,
  }));

  const lastDays = sorted[sorted.length - 1].days_before_checkin;
  if (lastDays > 0) {
    raw.push({ lowerDays: 0, refundPercentage: 0 });
  }

  // Merge adjacent bands that share the same refund rate into one line,
  // extending the kept band's lower bound down to absorb the merged one.
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

interface SegmentWindow {
  refundPercentage: number;
  start: Date;
  end: Date;
}

// Segments whose deadline has already passed (relative to today) are dropped
// entirely; the segment today falls inside (if any) has its start pulled
// forward to today rather than its original, already-past start date. Since
// segments are contiguous and chronologically ordered, at most one segment
// can straddle today, and it's always the first one left standing.
function visibleSegmentWindows(rules: CancellationRule[], checkInDate: Date, today: Date): SegmentWindow[] {
  const segments = buildSegments(rules);
  const windows = segments.map((seg, i) => ({
    refundPercentage: seg.refundPercentage,
    start: i === 0 ? today : addDays(subDays(checkInDate, segments[i - 1].lowerDays), 1),
    end: subDays(checkInDate, seg.lowerDays),
  }));
  const visible = windows.filter((w) => differenceInCalendarDays(w.end, today) >= 0);
  return visible.map((w, i) => (i === 0 ? { ...w, start: today } : w));
}

// A single highlight color for a plan, blending every still-relevant
// cancellation period's gradient color weighted by how many days that period
// actually spans. E.g. a long free-cancellation window outweighs a short
// non-refundable tail, biasing the blend toward green.
export function refundHighlightColor(rules: CancellationRule[], checkInDate: Date, today: Date): RGB {
  const windows = visibleSegmentWindows(rules, checkInDate, today);
  if (windows.length === 0) {
    const segments = buildSegments(rules);
    return fillForRefund(segments.length === 0 ? 0 : segments[segments.length - 1].refundPercentage);
  }

  let totalWeight = 0;
  let weightedSum: RGB = [0, 0, 0];
  windows.forEach((w) => {
    const days = Math.max(0, differenceInCalendarDays(w.end, w.start) + 1);
    const fill = fillForRefund(w.refundPercentage);
    totalWeight += days;
    weightedSum = [weightedSum[0] + fill[0] * days, weightedSum[1] + fill[1] * days, weightedSum[2] + fill[2] * days];
  });

  if (totalWeight === 0) return fillForRefund(windows[windows.length - 1].refundPercentage);
  return [weightedSum[0] / totalWeight, weightedSum[1] / totalWeight, weightedSum[2] / totalWeight];
}

interface CancellationTimelineProps {
  rules: CancellationRule[];
  checkInDate: Date;
  today: Date;
  dateLocale: DateFnsLocale;
  price: number;
  currency: Currency;
  cancellationLabel: string;
  tillTemplate: string;
  rangeTemplate: string;
  freeLabel: string;
  chargeTemplate: string;
}

export function CancellationTimeline({
  rules,
  checkInDate,
  today,
  dateLocale,
  price,
  currency,
  cancellationLabel,
  tillTemplate,
  rangeTemplate,
  freeLabel,
  chargeTemplate,
}: CancellationTimelineProps) {
  const windows = visibleSegmentWindows(rules, checkInDate, today);
  if (windows.length === 0) return null;

  const dateLabel = (date: Date) => format(date, "MMM d", { locale: dateLocale });

  return (
    <div className="mt-2 text-sm">
      <p className="font-semibold text-gray-600 dark:text-gray-300">{cancellationLabel}</p>
      <ul className="mt-1 space-y-0.5 text-gray-600 dark:text-gray-300">
        {windows.map((w, i) => {
          const datePart =
            i === 0
              ? tillTemplate.replace("{date}", dateLabel(w.end))
              : rangeTemplate.replace("{startDate}", dateLabel(w.start)).replace("{endDate}", dateLabel(w.end));
          const fill = fillForRefund(w.refundPercentage);
          const color = `rgb(${fill[0]}, ${fill[1]}, ${fill[2]})`;
          const valuePart =
            w.refundPercentage >= 1
              ? freeLabel
              : chargeTemplate.replace("{cost}", formatPrice(price * (1 - w.refundPercentage), currency));
          return (
            <li key={w.end.getTime()}>
              {datePart}:{" "}
              <span className="font-semibold" style={{ color }}>
                {valuePart}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
