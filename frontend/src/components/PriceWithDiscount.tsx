"use client";

import { formatPrice } from "@/lib/currency-config";
import type { Currency } from "@/lib/api";

/**
 * A price, with its undiscounted "regular" figure struck through beside it
 * when a promotion took something off.
 *
 * Defined once and used everywhere a discounted amount appears (plan cards,
 * the widget header, the payment step, booking details, my bookings) so the
 * treatment is identical throughout — and, when nothing was discounted,
 * renders exactly the plain price it would have rendered before promotions
 * existed.
 *
 * Both figures come from the server already formatted in the same currency;
 * this component only decides what to show, never what a price is.
 */
export default function PriceWithDiscount({
  price,
  regularPrice,
  currency,
  className = "",
  regularClassName = "",
}: {
  price: number;
  regularPrice: number;
  currency: Currency;
  /** Applied to the payable figure — the caller owns its size and weight. */
  className?: string;
  /** Extra classes for the struck-through figure, e.g. a lighter tone on a coloured header. */
  regularClassName?: string;
}) {
  // `<=` rather than `<`: an equal regular price means no promotion applied,
  // and a struck-through copy of the same number reads as a bug.
  const discounted = regularPrice > price;
  return (
    <>
      {discounted && (
        <s className={`text-gray-400 dark:text-gray-500 text-[0.8em] mr-2 ${regularClassName}`}>
          {formatPrice(regularPrice, currency)}
        </s>
      )}
      <b className={className}>{formatPrice(price, currency)}</b>
    </>
  );
}
