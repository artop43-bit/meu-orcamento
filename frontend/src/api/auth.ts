import { useQuery } from "@tanstack/react-query";

import { api, ApiError } from "./client";

export type User = {
  id: string;
  email: string;
  email_verified: boolean;
  totp_enabled: boolean;
  created_at: string;
};

export type LoginResult =
  | { status: "ok"; user: User; challenge: null }
  | { status: "2fa_required"; user: null; challenge: string };

type Message = { message: string };

export const authApi = {
  me: () => api.get<User>("/auth/me"),
  register: (email: string, password: string) =>
    api.post<Message>("/auth/register", { email, password }),
  verifyEmail: (token: string) => api.post<Message>("/auth/verify-email", { token }),
  resendVerification: (email: string) =>
    api.post<Message>("/auth/resend-verification", { email }),
  login: (email: string, password: string) =>
    api.post<LoginResult>("/auth/login", { email, password }),
  login2fa: (challenge: string, code: string) =>
    api.post<LoginResult>("/auth/login/2fa", { challenge, code }),
  logout: () => api.post<void>("/auth/logout"),
  forgotPassword: (email: string) => api.post<Message>("/auth/forgot-password", { email }),
  resetPassword: (token: string, password: string) =>
    api.post<Message>("/auth/reset-password", { token, password }),
  changePassword: (current_password: string, new_password: string) =>
    api.post<void>("/auth/change-password", { current_password, new_password }),
  twoFactorStatus: () =>
    api.get<{ enabled: boolean; recovery_codes_remaining: number }>("/auth/2fa"),
  twoFactorSetup: () => api.post<{ secret: string; otpauth_uri: string }>("/auth/2fa/setup"),
  twoFactorEnable: (code: string) =>
    api.post<{ recovery_codes: string[] }>("/auth/2fa/enable", { code }),
  twoFactorDisable: (password: string, code: string) =>
    api.post<void>("/auth/2fa/disable", { password, code }),
  regenerateRecoveryCodes: (code: string) =>
    api.post<{ recovery_codes: string[] }>("/auth/2fa/recovery-codes", { code }),
};

export const ME_KEY = ["auth", "me"] as const;

/** Usuário logado, ou null se não houver sessão. */
export function useMe() {
  return useQuery({
    queryKey: ME_KEY,
    queryFn: async () => {
      try {
        return await authApi.me();
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    retry: false,
    staleTime: 60_000,
  });
}
