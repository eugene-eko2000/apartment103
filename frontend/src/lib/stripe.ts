import { loadStripe, type Stripe } from "@stripe/stripe-js";

let stripePromise: Promise<Stripe | null> | null = null;

// Loaded lazily (not at module scope) so importing this file never triggers
// Stripe.js to fetch/execute before it's actually needed.
export function getStripe(): Promise<Stripe | null> {
  if (!stripePromise) {
    const publishableKey = process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY ?? "";
    stripePromise = loadStripe(publishableKey);
  }
  return stripePromise;
}
