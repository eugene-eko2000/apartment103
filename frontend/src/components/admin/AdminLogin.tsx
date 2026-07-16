"use client";

import { useState } from "react";
import { ApiError, requestOtp, verifyOtp } from "@/lib/api";
import { useAdminAuth } from "@/lib/admin-auth";
import { SubmitButton, TextField } from "./FormFields";

type Step = "identifier" | "otp" | "unauthorized";

export default function AdminLogin() {
  const { login } = useAdminAuth();
  const [step, setStep] = useState<Step>("identifier");
  const [identifier, setIdentifier] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [pending, setPending] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const resetToIdentifier = () => {
    setStep("identifier");
    setOtpCode("");
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
    <div className="min-h-screen flex items-center justify-center bg-slate-100 px-4">
      <div className="w-full max-w-sm bg-white rounded-xl shadow-lg border border-slate-200 p-8">
        <h1 className="text-lg font-bold text-slate-800 mb-1">apartment103 admin</h1>

        {step === "identifier" && (
          <form onSubmit={handleRequestOtp} className="space-y-4 mt-6">
            <p className="text-sm text-slate-500">
              Enter the email or phone number registered as an admin to receive a one-time code.
            </p>
            <TextField
              label="Email or phone number"
              value={identifier}
              onChange={setIdentifier}
              placeholder="you@example.com"
            />
            {errorMessage && <p className="text-sm text-red-600">{errorMessage}</p>}
            <SubmitButton pending={pending} label="Send code" />
          </form>
        )}

        {step === "otp" && (
          <form onSubmit={handleVerifyOtp} className="space-y-4 mt-6">
            <p className="text-sm text-slate-500">Enter the code sent to {identifier}.</p>
            <TextField label="Verification code" value={otpCode} onChange={setOtpCode} placeholder="123456" />
            {errorMessage && <p className="text-sm text-red-600">{errorMessage}</p>}
            <SubmitButton pending={pending} label="Verify" />
            <div className="flex items-center justify-between text-xs text-slate-500">
              <button type="button" onClick={handleResendOtp} className="hover:text-indigo-700 cursor-pointer">
                Resend code
              </button>
              <button type="button" onClick={resetToIdentifier} className="hover:text-indigo-700 cursor-pointer">
                Use a different identifier
              </button>
            </div>
          </form>
        )}

        {step === "unauthorized" && (
          <div className="mt-6 space-y-4 text-center">
            <p className="text-sm text-red-600">
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
