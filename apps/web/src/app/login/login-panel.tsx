"use client";

import { useSearchParams } from "next/navigation";

import { buttonClass } from "@/components/ui/button";

const MESSAGES: Record<string, { text: string; tone: "critical" | "healthy" }> = {
  callback: { text: "Sign-in could not be completed. Please try again.", tone: "critical" },
  signed_out: { text: "You have been signed out.", tone: "healthy" },
};

export function LoginPanel() {
  const params = useSearchParams();
  const returnTo = params.get("returnTo") ?? "/";
  const message = params.get("error") ? MESSAGES.callback : params.get("signed_out") ? MESSAGES.signed_out : null;

  return (
    <>
      {message && (
        <p
          role={message.tone === "critical" ? "alert" : "status"}
          className={`mt-6 rounded-card border border-border bg-surface-1 px-3 py-2 text-sm ${message.tone === "critical" ? "text-critical" : "text-healthy"}`}
        >
          {message.text}
        </p>
      )}
      {/* A full navigation, not a client transition: the server starts the OIDC flow. */}
      <a
        href={`/auth/login?returnTo=${encodeURIComponent(returnTo)}`}
        className={buttonClass({ size: "lg", className: "mt-8 w-full" })}
      >
        Continue with single sign-on
      </a>
    </>
  );
}
