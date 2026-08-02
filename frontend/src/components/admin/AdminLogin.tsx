"use client";

import { useState } from "react";
import { ApiError, requestOtp, verifyOtp } from "@/lib/api";
import { useAdminAuth } from "@/lib/admin-auth";
import { useOtpResendCooldown } from "@/lib/useOtpResendCooldown";
import { SubmitButton, TextField } from "./FormFields";

type Step = "identifier" | "otp" | "unauthorized";

export default function AdminLogin() {
  const { login } = useAdminAuth();
  const [step, setStep] = useState<Step>("identifier");
  const [identifier, setIdentifier] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [pending, setPending] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [resendMessage, setResendMessage] = useState<string | null>(null);
  const resendCooldown = useOtpResendCooldown();

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
      const result = await requestOtp(identifier.trim());
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
      const result = await requestOtp(identifier.trim());
      resendCooldown.start(result.retry_after_seconds);
      setResendMessage("A new code has been sent.");
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
      const result = await verifyOtp(identifier.trim(), otpCode.trim(), "admin");
      if (result.subject_type !== "admin") {
        setStep("unauthorized");
        return;
      }
      login({
        token: result.access_token,
        adminId: result.subject_id,
        expiresAt: Date.now() + result.expires_in * 1000,
      });
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : String(err));
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100 dark:bg-slate-900 px-4">
      <div className="w-full max-w-sm bg-white dark:bg-slate-800 rounded-xl shadow-lg border border-slate-200 dark:border-slate-700 p-8">
        <h1 className="text-lg font-bold text-slate-800 dark:text-slate-100 mb-1">Berg See Home admin</h1>

        {step === "identifier" && (
          <form onSubmit={handleRequestOtp} className="space-y-4 mt-6">
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Enter the email or phone number registered as an admin to receive a one-time code.
            </p>
            <TextField
              label="Email or phone number"
              value={identifier}
              onChange={setIdentifier}
              placeholder="you@example.com"
            />
            {errorMessage && <p className="text-sm text-red-600 dark:text-red-400">{errorMessage}</p>}
            <SubmitButton pending={pending} label="Send code" />
          </form>
        )}

        {step === "otp" && (
          <form onSubmit={handleVerifyOtp} className="space-y-4 mt-6">
            <p className="text-sm text-slate-500 dark:text-slate-400">Enter the code sent to {identifier}.</p>
            <TextField label="Verification code" value={otpCode} onChange={setOtpCode} placeholder="123456" />
            {errorMessage && <p className="text-sm text-red-600 dark:text-red-400">{errorMessage}</p>}
            {resendMessage && <p className="text-sm text-emerald-600 dark:text-emerald-400">{resendMessage}</p>}
            <SubmitButton pending={pending} label="Verify" />
            <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
              <button
                type="button"
                onClick={handleResendOtp}
                disabled={pending || resendCooldown.secondsLeft > 0}
                className="hover:text-indigo-700 dark:hover:text-indigo-400 disabled:opacity-60 disabled:cursor-not-allowed cursor-pointer"
              >
                {resendCooldown.secondsLeft > 0 ? `Resend code (${resendCooldown.secondsLeft}s)` : "Resend code"}
              </button>
              <button type="button" onClick={resetToIdentifier} className="hover:text-indigo-700 dark:hover:text-indigo-400 cursor-pointer">
                Use a different identifier
              </button>
            </div>
          </form>
        )}

        {step === "unauthorized" && (
          <div className="mt-6 space-y-4 text-center">
            <p className="text-sm text-red-600 dark:text-red-400">
              This identifier isn&apos;t recognized as an admin. You aren&apos;t authorized for admin access.
            </p>
            <button
              type="button"
              onClick={resetToIdentifier}
              className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2.5 rounded-lg text-sm transition-colors cursor-pointer"
            >
              Try another identifier
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
