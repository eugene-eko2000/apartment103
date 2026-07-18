"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { ApiError, requestOtp, verifyOtp } from "@/lib/api";
import { saveGuestSession } from "@/lib/guest-auth";

export interface LoginModalDict {
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
}

type Step = "identifier" | "otp";

export default function LoginModal({
  dict,
  onClose,
  onLoggedIn,
}: {
  dict: LoginModalDict;
  onClose: () => void;
  onLoggedIn: () => void;
}) {
  const [step, setStep] = useState<Step>("identifier");
  const [identifier, setIdentifier] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [pending, setPending] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

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
  };

  const handleRequestOtp = async (e: React.SubmitEvent<HTMLFormElement>) => {
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

  const handleVerifyOtp = async (e: React.SubmitEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!otpCode.trim()) return;
    setPending(true);
    setErrorMessage(null);
    try {
      const result = await verifyOtp(identifier.trim(), otpCode.trim());
      saveGuestSession({
        token: result.access_token,
        guestId: result.subject_type === "guest" ? result.subject_id : null,
        guestMode: result.subject_type === "guest" ? "update" : "create",
        isAdminBooking: result.subject_type === "admin",
        expiresAt: Date.now() + result.expires_in * 1000,
      });
      onLoggedIn();
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : String(err));
    } finally {
      setPending(false);
    }
  };

  // Portaled to the document body: this modal can be opened from inside the
  // header, whose backdrop-blur establishes a containing block for
  // position:fixed descendants — without the portal, "fixed inset-0" would
  // be positioned relative to the (much smaller) header bar instead of the
  // viewport.
  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div
          className="px-6 py-4 rounded-t-2xl flex items-center justify-between sticky top-0"
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

        <div className="p-6">
          {step === "identifier" && (
            <form onSubmit={handleRequestOtp} className="space-y-4">
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">{dict.identifierHint}</p>
              </div>
              <div>
                <label htmlFor="login-identifier" className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                  {dict.identifierLabel}
                </label>
                <input
                  id="login-identifier"
                  type="text"
                  required
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  placeholder={dict.identifierPlaceholder}
                  className="w-full px-3 py-2.5 rounded-xl border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 text-sm focus:outline-none focus:ring-1 focus:ring-teal-300 focus:border-teal-400"
                />
              </div>
              {errorMessage && <p className="text-sm text-red-600 dark:text-red-400">{errorMessage}</p>}
              <SubmitButton pending={pending} label={dict.sendCode} />
            </form>
          )}

          {step === "otp" && (
            <form onSubmit={handleVerifyOtp} className="space-y-4">
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">{dict.otpHint.replace("{identifier}", identifier)}</p>
              </div>
              <div>
                <label htmlFor="login-otp" className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                  {dict.otpLabel}
                </label>
                <input
                  id="login-otp"
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
              <SubmitButton pending={pending} label={dict.verifyCode} />
              <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
                <button type="button" onClick={handleResendOtp} className="hover:text-teal-700 dark:hover:text-teal-400 cursor-pointer">
                  {dict.resendCode}
                </button>
                <button type="button" onClick={resetToIdentifier} className="hover:text-teal-700 dark:hover:text-teal-400 cursor-pointer">
                  {dict.changeIdentifier}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>,
    document.body
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
