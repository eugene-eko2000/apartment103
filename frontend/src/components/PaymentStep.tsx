"use client";

import { useState } from "react";
import { CardElement, Elements, useElements, useStripe } from "@stripe/react-stripe-js";
import type { StripeCardElementOptions } from "@stripe/stripe-js";
import { getStripe } from "@/lib/stripe";
import type { PaymentIntentResponse } from "@/lib/api";
import type { Locale } from "@/lib/i18n-config";
import { useTheme } from "@/lib/theme-context";
import { formatPrice } from "@/lib/currency-config";

export interface PaymentStepDict {
  verifyCardTitle: string;
  verifyCardHint: string;
  payTitle: string;
  payHint: string;
  chargeSummary: string;
  payButton: string;
  verifyButton: string;
  processing: string;
  cardholderNameLabel: string;
  cardholderNamePlaceholder: string;
  cardDetailsLabel: string;
}

export default function PaymentStep({
  intent,
  dict,
  lang,
  guestName,
  guestEmail,
  onSuccess,
}: {
  intent: PaymentIntentResponse;
  dict: PaymentStepDict;
  lang: Locale;
  guestName: string;
  guestEmail: string;
  onSuccess: () => void;
}) {
  return (
    <Elements stripe={getStripe()} options={{ locale: lang }}>
      <PaymentForm intent={intent} dict={dict} guestName={guestName} guestEmail={guestEmail} onSuccess={onSuccess} />
    </Elements>
  );
}

function PaymentForm({
  intent,
  dict,
  guestName,
  guestEmail,
  onSuccess,
}: {
  intent: PaymentIntentResponse;
  dict: PaymentStepDict;
  guestName: string;
  guestEmail: string;
  onSuccess: () => void;
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

    setSubmitting(false);
    if (error) {
      setErrorMessage(error.message ?? dict.processing);
      return;
    }
    onSuccess();
  };

  const cardElementOptions: StripeCardElementOptions = {
    hidePostalCode: true,
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
      <p className="text-sm text-gray-600 dark:text-gray-300">
        {intent.mode === "setup" ? dict.verifyCardHint : dict.payHint}
      </p>

      {intent.mode === "payment" && intent.total_price > 0 && (
        <p className="text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-50 dark:bg-gray-700/50 rounded-xl px-3 py-2.5">
          {dict.chargeSummary
            .replace("{amount}", formatPrice(intent.amount, intent.currency))
            .replace("{percent}", String(Math.round((intent.amount / intent.total_price) * 100)))
            .replace("{total}", formatPrice(intent.total_price, intent.currency))}
        </p>
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
      <button
        type="button"
        disabled={!stripe || !elements || submitting || !cardComplete || !cardholderName.trim()}
        onClick={handleSubmit}
        className="w-full text-white font-semibold py-4 rounded-xl text-base transition-all shadow-lg active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
        style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}
      >
        {submitting ? dict.processing : intent.mode === "setup" ? dict.verifyButton : dict.payButton}
      </button>
    </div>
  );
}
