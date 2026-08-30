"use client";

import { useState } from "react";
import { CardElement, Elements, useElements, useStripe } from "@stripe/react-stripe-js";
import type { StripeCardElementOptions } from "@stripe/stripe-js";
import { format, parse } from "date-fns";
import { enUS, de, fr, it } from "date-fns/locale";
import type { Locale as DateFnsLocale } from "date-fns";
import { getStripe } from "@/lib/stripe";
import type { PaymentIntentResponse } from "@/lib/api";
import type { Locale } from "@/lib/i18n-config";
import { useTheme } from "@/lib/theme-context";
import { formatPrice } from "@/lib/currency-config";
import PriceWithDiscount from "@/components/PriceWithDiscount";

const DATE_FNS_LOCALES: Record<Locale, DateFnsLocale> = { en: enUS, de, fr, it };

export interface PaymentStepDict {
  verifyCardTitle: string;
  verifyCardHint: string;
  payTitle: string;
  chargeSummary: string;
  upcomingChargesLabel: string;
  upcomingChargeLine: string;
  payButton: string;
  verifyButton: string;
  processing: string;
  cardholderNameLabel: string;
  cardholderNamePlaceholder: string;
  cardDetailsLabel: string;
  regularPrice: string;
  youSave: string;
}

export default function PaymentStep({
  intent,
  dict,
  lang,
  guestName,
  guestEmail,
  onSuccess,
  onBack,
  backLabel,
  onCancel,
  cancelLabel,
}: {
  intent: PaymentIntentResponse;
  dict: PaymentStepDict;
  lang: Locale;
  guestName: string;
  guestEmail: string;
  onSuccess: () => Promise<void>;
  onBack: () => void;
  backLabel: string;
  onCancel: () => void;
  cancelLabel: string;
}) {
  return (
    <Elements stripe={getStripe()} options={{ locale: lang }}>
      <PaymentForm
        intent={intent}
        dict={dict}
        lang={lang}
        guestName={guestName}
        guestEmail={guestEmail}
        onSuccess={onSuccess}
        onBack={onBack}
        backLabel={backLabel}
        onCancel={onCancel}
        cancelLabel={cancelLabel}
      />
    </Elements>
  );
}

function PaymentForm({
  intent,
  dict,
  lang,
  guestName,
  guestEmail,
  onSuccess,
  onBack,
  backLabel,
  onCancel,
  cancelLabel,
}: {
  intent: PaymentIntentResponse;
  dict: PaymentStepDict;
  lang: Locale;
  guestName: string;
  guestEmail: string;
  onSuccess: () => Promise<void>;
  onBack: () => void;
  backLabel: string;
  onCancel: () => void;
  cancelLabel: string;
}) {
  const stripe = useStripe();
  const elements = useElements();
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  const [cardholderName, setCardholderName] = useState(guestName);
  const [cardComplete, setCardComplete] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSubmit = async () => {
    const cardElement = elements?.getElement(CardElement);
    if (!stripe || !elements || !cardElement || !cardholderName.trim() || !cardComplete) return;
    setSubmitting(true);
    setErrorMessage(null);

    const paymentMethod = {
      card: cardElement,
      billing_details: { name: cardholderName.trim(), email: guestEmail },
    };
    const { error } =
      intent.mode === "setup"
        ? await stripe.confirmCardSetup(intent.client_secret, { payment_method: paymentMethod })
        : await stripe.confirmCardPayment(intent.client_secret, { payment_method: paymentMethod });

    if (error) {
      setSubmitting(false);
      setErrorMessage(error.message ?? dict.processing);
      return;
    }
    // Stripe accepting the card is not the booking being confirmed: the
    // server still has to apply that payment, and can refuse it if another
    // guest's payment claimed the same nights first. onSuccess is what waits
    // for that verdict, so the form stays submitting until it has moved this
    // step on — the guest must never see a Pay button go idle next to a
    // charged card.
    await onSuccess();
  };

  const cardElementOptions: StripeCardElementOptions = {
    hidePostalCode: true,
    disabled: submitting,
    disableLink: true,
    style: {
      base: {
        fontSize: "14px",
        fontFamily: "inherit",
        color: isDark ? "#f3f4f6" : "#1f2937",
        "::placeholder": { color: "#9ca3af" },
      },
      invalid: { color: "#dc2626" },
    },
  };

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
        {intent.mode === "setup" ? dict.verifyCardTitle : dict.payTitle}
      </h3>
      {intent.mode === "setup" && (
        <p className="text-sm text-gray-600 dark:text-gray-300">{dict.verifyCardHint}</p>
      )}

      {((intent.mode === "payment" && intent.total_price > 0) ||
        intent.total_discount > 0 ||
        intent.upcoming_charges.length > 0) && (
        <div className="text-sm bg-gray-50 dark:bg-gray-700/50 rounded-xl px-3 py-2.5 space-y-1.5">
          {/* The stay's total, with what the promotions took off it.
              intent.amount — what is being charged right now — keeps its
              own single-figure rendering in the line below: a discount
              applies to the stay, not to this one instalment. */}
          {intent.total_discount > 0 && (
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-gray-600 dark:text-gray-300">{dict.regularPrice}</span>
              <span className="inline-flex items-baseline text-gray-700 dark:text-gray-200">
                <PriceWithDiscount
                  price={intent.total_price}
                  regularPrice={intent.regular_total_price}
                  currency={intent.currency}
                />
              </span>
            </div>
          )}
          {intent.total_discount > 0 && (
            <p className="font-medium text-teal-700 dark:text-teal-400">
              {dict.youSave.replace("{amount}", formatPrice(intent.total_discount, intent.currency))}
            </p>
          )}

          {intent.mode === "payment" && intent.total_price > 0 && (
            <p className="font-medium text-gray-700 dark:text-gray-200">
              {dict.chargeSummary
                .replace("{amount}", formatPrice(intent.amount, intent.currency))
                .replace("{percent}", String(Math.round((intent.amount / intent.total_price) * 100)))
                .replace("{total}", formatPrice(intent.total_price, intent.currency))}
            </p>
          )}

          {intent.upcoming_charges.length > 0 && (
            <div className="text-gray-600 dark:text-gray-300">
              <p className="font-medium text-gray-700 dark:text-gray-200">{dict.upcomingChargesLabel}</p>
              <ul className="mt-1 space-y-0.5">
                {intent.upcoming_charges.map((charge) => (
                  <li key={charge.charge_date}>
                    {dict.upcomingChargeLine
                      .replace("{amount}", formatPrice(charge.amount, intent.currency))
                      .replace(
                        "{date}",
                        format(parse(charge.charge_date, "yyyy-MM-dd", new Date()), "MMM d, yyyy", {
                          locale: DATE_FNS_LOCALES[lang],
                        })
                      )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <div>
        <label htmlFor="cardholder-name" className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
          {dict.cardholderNameLabel}
        </label>
        <input
          id="cardholder-name"
          type="text"
          required
          autoComplete="cc-name"
          value={cardholderName}
          onChange={(e) => setCardholderName(e.target.value)}
          placeholder={dict.cardholderNamePlaceholder}
          className="w-full px-3 py-2.5 rounded-xl border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-teal-300 focus:border-teal-400"
        />
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">{dict.cardDetailsLabel}</label>
        <div className="w-full px-3 py-3 rounded-xl border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 focus-within:ring-1 focus-within:ring-teal-300 focus-within:border-teal-400">
          <CardElement options={cardElementOptions} onChange={(e) => setCardComplete(e.complete)} />
        </div>
      </div>

      {errorMessage && <p className="text-sm text-red-600 dark:text-red-400">{errorMessage}</p>}

      {/* Sticky rather than hoisted to the parent's own fixed footer (unlike
          the other booking-widget steps): this button calls handleSubmit,
          which needs useStripe()/useElements() — it can only render inside
          this component's <Elements> tree, not in a sibling owned by
          BookingWidget. Sticking it to the bottom of the shared scrollable
          area gets the same "always reachable" result without that hop. */}
      <div className="sticky bottom-0 -mx-6 px-6 pb-6 pt-4 bg-white dark:bg-gray-800 border-t border-gray-100 dark:border-gray-700 space-y-3">
        <div className="flex gap-3">
          <button
            type="button"
            disabled={submitting}
            onClick={onBack}
            className="flex-1 text-gray-600 dark:text-gray-300 font-semibold py-4 rounded-xl text-base transition-all border border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          >
            {backLabel}
          </button>
          <button
            type="button"
            disabled={!stripe || !elements || submitting || !cardComplete || !cardholderName.trim()}
            onClick={handleSubmit}
            className="flex-1 text-white font-semibold py-4 rounded-xl text-base transition-all shadow-lg active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}
          >
            {submitting ? dict.processing : intent.mode === "setup" ? dict.verifyButton : dict.payButton}
          </button>
        </div>
        <button
          type="button"
          disabled={submitting}
          onClick={onCancel}
          className="block w-full text-center text-xs text-gray-400 dark:text-gray-500 hover:text-teal-700 dark:hover:text-teal-400 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
        >
          {cancelLabel}
        </button>
      </div>
    </div>
  );
}
