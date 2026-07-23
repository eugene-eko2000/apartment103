"use client";

import { useState } from "react";
import { Elements, PaymentElement, useElements, useStripe } from "@stripe/react-stripe-js";
import { getStripe } from "@/lib/stripe";
import type { PaymentIntentResponse } from "@/lib/api";

export interface PaymentStepDict {
  verifyCardTitle: string;
  verifyCardHint: string;
  payTitle: string;
  payHint: string;
  payButton: string;
  verifyButton: string;
  processing: string;
}

export default function PaymentStep({
  intent,
  dict,
  onSuccess,
}: {
  intent: PaymentIntentResponse;
  dict: PaymentStepDict;
  onSuccess: () => void;
}) {
  return (
    <Elements
      stripe={getStripe()}
      options={{
        clientSecret: intent.client_secret,
        appearance: { theme: "stripe", variables: { colorPrimary: "#0f766e", borderRadius: "12px" } },
      }}
    >
      <PaymentForm intent={intent} dict={dict} onSuccess={onSuccess} />
    </Elements>
  );
}

function PaymentForm({
  intent,
  dict,
  onSuccess,
}: {
  intent: PaymentIntentResponse;
  dict: PaymentStepDict;
  onSuccess: () => void;
}) {
  const stripe = useStripe();
  const elements = useElements();
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!stripe || !elements) return;
    setSubmitting(true);
    setErrorMessage(null);
    // redirect: "if_required" keeps the guest on this same step for the card
    // payment methods this app offers server-side — only a redirect-based
    // method (not configured here) would ever need to leave the page.
    const { error } =
      intent.mode === "setup"
        ? await stripe.confirmSetup({ elements, redirect: "if_required" })
        : await stripe.confirmPayment({ elements, redirect: "if_required" });
    setSubmitting(false);
    if (error) {
      setErrorMessage(error.message ?? dict.processing);
      return;
    }
    onSuccess();
  };

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-widest">
        {intent.mode === "setup" ? dict.verifyCardTitle : dict.payTitle}
      </h3>
      <p className="text-sm text-gray-600 dark:text-gray-300">
        {intent.mode === "setup" ? dict.verifyCardHint : dict.payHint}
      </p>
      <PaymentElement />
      {errorMessage && <p className="text-sm text-red-600 dark:text-red-400">{errorMessage}</p>}
      <button
        type="button"
        disabled={!stripe || !elements || submitting}
        onClick={handleSubmit}
        className="w-full text-white font-semibold py-4 rounded-xl text-base transition-all shadow-lg active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
        style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}
      >
        {submitting ? dict.processing : intent.mode === "setup" ? dict.verifyButton : dict.payButton}
      </button>
    </div>
  );
}
