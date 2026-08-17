"use client";

import { useEffect, useState } from "react";
import { ApiError, getGuest, requestOtp, verifyOtp, type Guest, type GuestInput, type SubjectType } from "@/lib/api";
import type { PaymentStepDict } from "@/components/PaymentStep";
import { useOtpResendCooldown } from "@/lib/useOtpResendCooldown";
import type { Locale } from "@/lib/i18n-config";
import type { Currency } from "@/lib/currency-config";

export interface BookingModalDict {
  close: string;
  identifierTitle: string;
  identifierHint: string;
  identifierLabel: string;
  identifierPlaceholder: string;
  sendCode: string;
  otpTitle: string;
  otpHint: string;
  otpLabel: string;
  otpPlaceholder: string;
  verifyCode: string;
  resendCode: string;
  codeResent: string;
  back: string;
  cancel: string;
  guestTitleCreate: string;
  guestTitleUpdate: string;
  familyName: string;
  firstName: string;
  streetAddress: string;
  zip: string;
  city: string;
  state: string;
  stateOptional: string;
  country: string;
  selectCountry: string;
  noMatchesCountry: string;
  phoneNumber: string;
  email: string;
  preferredLanguage: string;
  preferredCurrency: string;
  noPreference: string;
  continue: string;
  summaryTitle: string;
  confirmBooking: string;
  submitting: string;
  successTitle: string;
  successMessage: string;
  emailNotice: string;
  done: string;
  errorTitle: string;
  tryAgain: string;
  noPlan: string;
  selectDatesFirst: string;
  choosePlanTitle: string;
  cancellationLabel: string;
  cancellationTill: string;
  cancellationRange: string;
  cancellationFree: string;
  cancellationCharge: string;
  next: string;
  payment: PaymentStepDict;
}

export interface VerifiedIdentity {
  authToken: string;
  expiresAt: number;
  guestId: string | null;
  guestMode: "create" | "update";
  isAdminBooking: boolean;
  guestForm: GuestInput;
}

type Step = "identifier" | "otp";

export const emptyGuestForm: GuestInput = {
  family_name: "",
  first_name: "",
  residence_address: { street_address: "", zip: "", city: "", state: "", country: "" },
  phone_number: "",
  email: "",
  preferred_language: null,
  preferred_currency: null,
};

// fallbackLang pre-fills preferred_language from the site's current locale
// when the guest has never set one, without ever overriding a language
// they've deliberately chosen before.
export function guestToForm(guest: Guest, fallbackLang: Locale | null = null): GuestInput {
  return {
    family_name: guest.family_name,
    first_name: guest.first_name,
    residence_address: { ...guest.residence_address, state: guest.residence_address.state ?? "" },
    phone_number: guest.phone_number,
    email: guest.email,
    preferred_language: guest.preferred_language ?? fallbackLang,
    preferred_currency: guest.preferred_currency ?? null,
  };
}

export default function BookingModal({
  dict,
  lang,
  currency,
  onClose,
  onVerified,
}: {
  dict: BookingModalDict;
  lang: Locale;
  currency: Currency;
  onClose: () => void;
  onVerified: (identity: VerifiedIdentity) => void;
}) {
  const [step, setStep] = useState<Step>("identifier");
  const [identifier, setIdentifier] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [pending, setPending] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [resendMessage, setResendMessage] = useState<string | null>(null);
  const resendCooldown = useOtpResendCooldown();

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const resetToIdentifier = () => {
    setStep("identifier");
    setOtpCode("");
    setErrorMessage(null);
    setResendMessage(null);
    resendCooldown.reset();
  };

  const handleRequestOtp = async (e: React.SubmitEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!identifier.trim()) return;
    setPending(true);
    setErrorMessage(null);
    try {
      const result = await requestOtp(identifier.trim(), lang);
      setOtpCode("");
      setResendMessage(null);
      resendCooldown.start(result.retry_after_seconds);
      setStep("otp");
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : String(err));
    } finally {
      setPending(false);
    }
  };

  const handleResendOtp = async () => {
    if (resendCooldown.secondsLeft > 0) return;
    setPending(true);
    setErrorMessage(null);
    setResendMessage(null);
    try {
      const result = await requestOtp(identifier.trim(), lang);
      resendCooldown.start(result.retry_after_seconds);
      setResendMessage(dict.codeResent);
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : String(err));
    } finally {
      setPending(false);
    }
  };

  const handleVerifyOtp = async (e: React.SubmitEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!otpCode.trim()) return;
    setPending(true);
    setErrorMessage(null);
    try {
      const result = await verifyOtp(identifier.trim(), otpCode.trim());
      const subjectType: SubjectType = result.subject_type;
      const expiresAt = Date.now() + result.expires_in * 1000;

      if (subjectType === "guest") {
        const guest = await getGuest(result.subject_id, result.access_token);
        onVerified({
          authToken: result.access_token,
          expiresAt,
          guestId: guest._id,
          guestMode: "update",
          isAdminBooking: false,
          guestForm: guestToForm(guest, lang),
        });
        return;
      }

      // admin / pending_guest: no guest profile yet under this identifier.
      // Pre-fill the verified identifier; admins register a guest profile for
      // themselves while brand-new visitors self-register.
      const isEmail = identifier.includes("@");
      onVerified({
        authToken: result.access_token,
        expiresAt,
        guestId: null,
        guestMode: "create",
        isAdminBooking: subjectType === "admin",
        guestForm: {
          ...emptyGuestForm,
          email: isEmail ? identifier.trim() : "",
          phone_number: isEmail ? "" : identifier.trim(),
          preferred_language: lang,
          preferred_currency: currency,
        },
      });
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : String(err));
    } finally {
      setPending(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-md max-h-[90vh] flex flex-col overflow-hidden">
        <div
          className="px-6 py-4 rounded-t-2xl flex items-center justify-between shrink-0"
          style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}
        >
          <h2 className="text-lg font-bold text-white">
            {step === "otp" ? dict.otpTitle : dict.identifierTitle}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={dict.close}
            className="text-white/80 hover:text-white text-xl leading-none cursor-pointer"
          >
            ×
          </button>
        </div>

        {step === "identifier" && (
          <form onSubmit={handleRequestOtp} className="flex flex-col min-h-0">
            <div className="p-6 space-y-4 overflow-y-auto">
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">{dict.identifierHint}</p>
              </div>
              <div>
                <label htmlFor="booking-identifier" className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                  {dict.identifierLabel}
                </label>
                <input
                  id="booking-identifier"
                  type="text"
                  required
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  placeholder={dict.identifierPlaceholder}
                  className="w-full px-3 py-2.5 rounded-xl border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-teal-300 focus:border-teal-400"
                />
              </div>
              {errorMessage && <p className="text-sm text-red-600 dark:text-red-400">{errorMessage}</p>}
            </div>
            <div className="flex gap-3 px-6 pb-6 pt-4 border-t border-gray-100 dark:border-gray-700 shrink-0">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 text-gray-600 dark:text-gray-300 font-semibold py-3 rounded-xl text-sm transition-all border border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 active:scale-[0.98] cursor-pointer"
              >
                {dict.cancel}
              </button>
              <SubmitButton pending={pending} label={dict.sendCode} />
            </div>
          </form>
        )}

        {step === "otp" && (
          <form onSubmit={handleVerifyOtp} className="flex flex-col min-h-0">
            <div className="p-6 space-y-4 overflow-y-auto">
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">{dict.otpHint.replace("{identifier}", identifier)}</p>
              </div>
              <div>
                <label htmlFor="booking-otp" className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                  {dict.otpLabel}
                </label>
                <input
                  id="booking-otp"
                  type="text"
                  inputMode="numeric"
                  required
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value)}
                  placeholder={dict.otpPlaceholder}
                  className="w-full px-3 py-2.5 rounded-xl border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 text-sm tracking-widest focus:outline-none focus:ring-1 focus:ring-teal-300 focus:border-teal-400"
                />
              </div>
              {errorMessage && <p className="text-sm text-red-600 dark:text-red-400">{errorMessage}</p>}
              {resendMessage && <p className="text-sm text-teal-600 dark:text-teal-400">{resendMessage}</p>}
            </div>
            <div className="px-6 pb-6 pt-4 border-t border-gray-100 dark:border-gray-700 shrink-0 space-y-4">
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={resetToIdentifier}
                  className="flex-1 text-gray-600 dark:text-gray-300 font-semibold py-3 rounded-xl text-sm transition-all border border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 active:scale-[0.98] cursor-pointer"
                >
                  {dict.back}
                </button>
                <SubmitButton pending={pending} label={dict.verifyCode} />
              </div>
              <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
                <button
                  type="button"
                  onClick={handleResendOtp}
                  disabled={pending || resendCooldown.secondsLeft > 0}
                  className="hover:text-teal-700 dark:hover:text-teal-400 disabled:opacity-60 disabled:cursor-not-allowed cursor-pointer"
                >
                  {resendCooldown.secondsLeft > 0 ? `${dict.resendCode} (${resendCooldown.secondsLeft}s)` : dict.resendCode}
                </button>
                <button type="button" onClick={onClose} className="hover:text-teal-700 dark:hover:text-teal-400 cursor-pointer">
                  {dict.cancel}
                </button>
              </div>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

function SubmitButton({ pending, label }: { pending: boolean; label: string }) {
  return (
    <button
      type="submit"
      disabled={pending}
      className="flex-1 text-white font-semibold py-3 rounded-xl text-sm transition-all shadow-lg active:scale-[0.98] disabled:opacity-60 cursor-pointer"
      style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}
    >
      {label}
    </button>
  );
}
