import type {
  BrowserLoginRequest,
  BrowserTokenResponse,
  EmailTokenRequest,
  MessageResponse,
  PasswordForgotRequest,
  PasswordResetRequest,
} from "@password-detective/api-contract";
import { apiRequest } from "./api";

function idempotencyHeaders(): HeadersInit {
  return { "Idempotency-Key": crypto.randomUUID() };
}

export function loginBrowser(payload: BrowserLoginRequest): Promise<BrowserTokenResponse> {
  return apiRequest<BrowserTokenResponse>("/web/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function verifyEmail(payload: EmailTokenRequest): Promise<MessageResponse> {
  return apiRequest<MessageResponse>("/auth/email/verify", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function resendEmailVerification(accessToken: string): Promise<MessageResponse> {
  return apiRequest<MessageResponse>(
    "/auth/email/resend",
    { method: "POST" },
    accessToken,
  );
}

export function requestPasswordReset(payload: PasswordForgotRequest): Promise<MessageResponse> {
  return apiRequest<MessageResponse>("/auth/password/forgot", {
    method: "POST",
    headers: idempotencyHeaders(),
    body: JSON.stringify(payload),
  });
}

export function resetPassword(payload: PasswordResetRequest): Promise<MessageResponse> {
  return apiRequest<MessageResponse>("/auth/password/reset", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
