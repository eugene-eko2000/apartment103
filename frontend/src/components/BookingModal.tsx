"use client";

import { useEffect, useId, useState } from "react";
import { format } from "date-fns";
import {
  ApiError,
  createBooking,
  getGuest,
  listPublicPlans,
  listPublicPrices,
  registerGuestSelf,
  requestOtp,
  updateGuest,
  verifyOtp,
  type Currency,
  type Guest,
  type GuestInput,
  type Language,
  type Plan,
  type Price,
  type SubjectType,
} from "@/lib/api";
import { findDailyRate, FALLBACK_CURRENCY, FALLBACK_DAILY_RATE } from "@/lib/pricing";

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
  changeIdentifier: string;
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
  done: string;
  errorTitle: string;
  tryAgain: string;
  adminUnsupported: string;
  noPlan: string;
  selectDatesFirst: string;
}

type Step = "identifier" | "otp" | "guest" | "submitting" | "success" | "error";

const LANGUAGES: Language[] = ["en", "de", "fr", "it"];
const CURRENCIES: Currency[] = ["EUR", "CHF", "USD", "GBP"];

const emptyGuestForm: GuestInput = {
  family_name: "",
  first_name: "",
  residence_address: { street_address: "", zip: "", city: "", state: "", country: "" },
  phone_number: "",
  email: "",
  preferred_language: null,
  preferred_currency: null,
};

function guestToForm(guest: Guest): GuestInput {
  return {
    family_name: guest.family_name,
    first_name: guest.first_name,
    residence_address: { ...guest.residence_address, state: guest.residence_address.state ?? "" },
    phone_number: guest.phone_number,
    email: guest.email,
    preferred_language: guest.preferred_language ?? null,
    preferred_currency: guest.preferred_currency ?? null,
  };
}

export default function BookingModal({
  dict,
  checkIn,
  checkOut,
  nights,
  onClose,
}: {
  dict: BookingModalDict;
  checkIn: Date;
  checkOut: Date;
  nights: number;
  onClose: () => void;
}) {
  const [plan, setPlan] = useState<Plan | null | undefined>(undefined);
  const [prices, setPrices] = useState<Price[]>([]);
  const [step, setStep] = useState<Step>("identifier");
  const [identifier, setIdentifier] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [guestId, setGuestId] = useState<string | null>(null);
  const [guestMode, setGuestMode] = useState<"create" | "update" | null>(null);
  const [guestForm, setGuestForm] = useState<GuestInput>(emptyGuestForm);
  const [guestName, setGuestName] = useState("");
  const [pending, setPending] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    listPublicPlans()
      .then((plans) => setPlan(plans[0] ?? null))
      .catch(() => setPlan(null));
    listPublicPrices()
      .then(setPrices)
      .catch(() => setPrices([]));
  }, []);

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
    setAuthToken(null);
    setGuestId(null);
    setGuestMode(null);
    setGuestForm(emptyGuestForm);
    setErrorMessage(null);
  };

  const handleRequestOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!identifier.trim()) return;
    setPending(true);
    setErrorMessage(null);
    try {
      await requestOtp(identifier.trim());
      setOtpCode("");
      setStep("otp");
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : String(err));
    } finally {
      setPending(false);
    }
  };

  const handleResendOtp = async () => {
    setPending(true);
    setErrorMessage(null);
    try {
      await requestOtp(identifier.trim());
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : String(err));
    } finally {
      setPending(false);
    }
  };

  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!otpCode.trim()) return;
    setPending(true);
    setErrorMessage(null);
    try {
      const result = await verifyOtp(identifier.trim(), otpCode.trim());
      const subjectType: SubjectType = result.subject_type;

      if (subjectType === "admin") {
        setErrorMessage(dict.adminUnsupported);
        setStep("error");
        return;
      }

      if (subjectType === "guest") {
        const guest = await getGuest(result.subject_id, result.access_token);
        setAuthToken(result.access_token);
        setGuestId(guest._id);
        setGuestMode("update");
        setGuestForm(guestToForm(guest));
        setStep("guest");
        return;
      }

      // pending_guest: brand-new visitor, empty form with the verified
      // identifier pre-filled into whichever field it corresponds to.
      const isEmail = identifier.includes("@");
      setAuthToken(result.access_token);
      setGuestMode("create");
      setGuestForm({
        ...emptyGuestForm,
        email: isEmail ? identifier.trim() : "",
        phone_number: isEmail ? "" : identifier.trim(),
      });
      setStep("guest");
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : String(err));
    } finally {
      setPending(false);
    }
  };

  const submitBooking = async (finalGuestId: string, token: string) => {
    if (!plan) return;
    setStep("submitting");
    try {
      const matchedRate = findDailyRate(prices, format(checkIn, "yyyy-MM-dd"));
      const dailyRate = matchedRate?.dailyRate ?? FALLBACK_DAILY_RATE;
      const currency: Currency = matchedRate?.currency ?? FALLBACK_CURRENCY;
      await createBooking(token, {
        guest_id: finalGuestId,
        cancellation_policy_id: plan.cancellation_policy.id,
        currency,
        date_ranges: [
          {
            begin_date: format(checkIn, "yyyy-MM-dd"),
            end_date: format(checkOut, "yyyy-MM-dd"),
            price: nights * dailyRate * plan.price_ratio,
          },
        ],
      });
      setStep("success");
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : String(err));
      setStep("error");
    }
  };

  const handleGuestFormSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!authToken) return;
    setPending(true);
    setErrorMessage(null);
    try {
      if (guestMode === "create") {
        const result = await registerGuestSelf(authToken, guestForm);
        setGuestName(result.guest.first_name);
        await submitBooking(result.guest._id, result.access_token);
      } else if (guestMode === "update" && guestId) {
        const guest = await updateGuest(guestId, authToken, guestForm);
        setGuestName(guest.first_name);
        await submitBooking(guestId, authToken);
      }
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : String(err));
      setStep("error");
    } finally {
      setPending(false);
    }
  };

  const updateAddress = (field: keyof GuestInput["residence_address"], value: string) => {
    setGuestForm((prev) => ({ ...prev, residence_address: { ...prev.residence_address, [field]: value } }));
  };

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div
          className="px-6 py-4 rounded-t-2xl flex items-center justify-between sticky top-0"
          style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}
        >
          <h2 className="text-lg font-bold text-white">
            {step === "success" ? dict.successTitle : step === "error" ? dict.errorTitle : dict.summaryTitle}
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

        <div className="p-6">
          {plan === null && step !== "success" ? (
            <p className="text-sm text-gray-600">{dict.noPlan}</p>
          ) : (
            <>
              {step === "identifier" && (
                <form onSubmit={handleRequestOtp} className="space-y-4">
                  <div>
                    <h3 className="font-semibold text-gray-800 mb-1">{dict.identifierTitle}</h3>
                    <p className="text-sm text-gray-500">{dict.identifierHint}</p>
                  </div>
                  <div>
                    <label htmlFor="booking-identifier" className="block text-xs font-medium text-gray-500 mb-1">
                      {dict.identifierLabel}
                    </label>
                    <input
                      id="booking-identifier"
                      type="text"
                      required
                      value={identifier}
                      onChange={(e) => setIdentifier(e.target.value)}
                      placeholder={dict.identifierPlaceholder}
                      className="w-full px-3 py-2.5 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-1 focus:ring-teal-300 focus:border-teal-400"
                    />
                  </div>
                  {errorMessage && <p className="text-sm text-red-600">{errorMessage}</p>}
                  <SubmitButton pending={pending} label={dict.sendCode} />
                </form>
              )}

              {step === "otp" && (
                <form onSubmit={handleVerifyOtp} className="space-y-4">
                  <div>
                    <h3 className="font-semibold text-gray-800 mb-1">{dict.otpTitle}</h3>
                    <p className="text-sm text-gray-500">{dict.otpHint.replace("{identifier}", identifier)}</p>
                  </div>
                  <div>
                    <label htmlFor="booking-otp" className="block text-xs font-medium text-gray-500 mb-1">
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
                      className="w-full px-3 py-2.5 rounded-xl border border-gray-200 text-sm tracking-widest focus:outline-none focus:ring-1 focus:ring-teal-300 focus:border-teal-400"
                    />
                  </div>
                  {errorMessage && <p className="text-sm text-red-600">{errorMessage}</p>}
                  <SubmitButton pending={pending} label={dict.verifyCode} />
                  <div className="flex items-center justify-between text-xs text-gray-500">
                    <button type="button" onClick={handleResendOtp} className="hover:text-teal-700 cursor-pointer">
                      {dict.resendCode}
                    </button>
                    <button type="button" onClick={resetToIdentifier} className="hover:text-teal-700 cursor-pointer">
                      {dict.changeIdentifier}
                    </button>
                  </div>
                </form>
              )}

              {step === "guest" && (
                <form onSubmit={handleGuestFormSubmit} className="space-y-3">
                  <h3 className="font-semibold text-gray-800 mb-1">
                    {guestMode === "create" ? dict.guestTitleCreate : dict.guestTitleUpdate}
                  </h3>
                  <div className="grid grid-cols-2 gap-3">
                    <TextField
                      label={dict.firstName}
                      value={guestForm.first_name}
                      onChange={(v) => setGuestForm((p) => ({ ...p, first_name: v }))}
                    />
                    <TextField
                      label={dict.familyName}
                      value={guestForm.family_name}
                      onChange={(v) => setGuestForm((p) => ({ ...p, family_name: v }))}
                    />
                  </div>
                  <TextField
                    label={dict.email}
                    type="email"
                    value={guestForm.email}
                    onChange={(v) => setGuestForm((p) => ({ ...p, email: v }))}
                    disabled={guestMode === "create" && identifier.includes("@")}
                  />
                  <TextField
                    label={dict.phoneNumber}
                    value={guestForm.phone_number}
                    onChange={(v) => setGuestForm((p) => ({ ...p, phone_number: v }))}
                    disabled={guestMode === "create" && !identifier.includes("@")}
                  />
                  <TextField
                    label={dict.streetAddress}
                    value={guestForm.residence_address.street_address}
                    onChange={(v) => updateAddress("street_address", v)}
                  />
                  <div className="grid grid-cols-2 gap-3">
                    <TextField label={dict.zip} value={guestForm.residence_address.zip} onChange={(v) => updateAddress("zip", v)} />
                    <TextField label={dict.city} value={guestForm.residence_address.city} onChange={(v) => updateAddress("city", v)} />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <TextField
                      label={dict.stateOptional}
                      value={guestForm.residence_address.state ?? ""}
                      onChange={(v) => updateAddress("state", v)}
                      required={false}
                    />
                    <TextField label={dict.country} value={guestForm.residence_address.country} onChange={(v) => updateAddress("country", v)} />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <SelectField
                      label={dict.preferredLanguage}
                      value={guestForm.preferred_language ?? ""}
                      noneLabel={dict.noPreference}
                      options={LANGUAGES}
                      onChange={(v) => setGuestForm((p) => ({ ...p, preferred_language: (v || null) as Language | null }))}
                    />
                    <SelectField
                      label={dict.preferredCurrency}
                      value={guestForm.preferred_currency ?? ""}
                      noneLabel={dict.noPreference}
                      options={CURRENCIES}
                      onChange={(v) => setGuestForm((p) => ({ ...p, preferred_currency: (v || null) as Currency | null }))}
                    />
                  </div>
                  {errorMessage && <p className="text-sm text-red-600">{errorMessage}</p>}
                  <SubmitButton pending={pending} label={dict.confirmBooking} />
                </form>
              )}

              {step === "submitting" && (
                <p className="text-sm text-gray-600 text-center py-8">{dict.submitting}</p>
              )}

              {step === "success" && (
                <div className="text-center py-4 space-y-4">
                  <p className="text-sm text-gray-700">{dict.successMessage.replace("{name}", guestName)}</p>
                  <button
                    type="button"
                    onClick={onClose}
                    className="w-full text-white font-semibold py-3 rounded-xl text-sm transition-all shadow-lg cursor-pointer"
                    style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}
                  >
                    {dict.done}
                  </button>
                </div>
              )}

              {step === "error" && (
                <div className="text-center py-4 space-y-4">
                  <p className="text-sm text-red-600">{errorMessage}</p>
                  <button
                    type="button"
                    onClick={resetToIdentifier}
                    className="w-full text-white font-semibold py-3 rounded-xl text-sm transition-all shadow-lg cursor-pointer"
                    style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}
                  >
                    {dict.tryAgain}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function SubmitButton({ pending, label }: { pending: boolean; label: string }) {
  return (
    <button
      type="submit"
      disabled={pending}
      className="w-full text-white font-semibold py-3 rounded-xl text-sm transition-all shadow-lg active:scale-[0.98] disabled:opacity-60 cursor-pointer"
      style={{ background: "linear-gradient(135deg, #0f766e 0%, #0891b2 100%)" }}
    >
      {label}
    </button>
  );
}

function TextField({
  label,
  value,
  onChange,
  type = "text",
  disabled = false,
  required = true,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  disabled?: boolean;
  required?: boolean;
}) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium text-gray-500 mb-1">
        {label}
      </label>
      <input
        id={id}
        type={type}
        required={required}
        disabled={disabled}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-1 focus:ring-teal-300 focus:border-teal-400 disabled:bg-gray-50 disabled:text-gray-400"
      />
    </div>
  );
}

function SelectField({
  label,
  value,
  options,
  noneLabel,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  noneLabel: string;
  onChange: (v: string) => void;
}) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium text-gray-500 mb-1">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 rounded-xl border border-gray-200 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-teal-300 focus:border-teal-400 cursor-pointer"
      >
        <option value="">{noneLabel}</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </div>
  );
}
