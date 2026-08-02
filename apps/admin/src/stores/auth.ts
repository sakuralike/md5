import {
  ApiError,
  isPrivilegedRole,
  type BrowserTokenResponse,
  type User,
} from "@password-detective/api-contract";
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { apiRequest } from "../services/api";

const STORAGE_KEY = "password_detective_admin_session_v2";

interface StoredAdminSession {
  accessToken: string;
  user: User;
  enrollmentOnly: boolean;
}

interface TotpSetupResponse {
  secret: string;
  provisioning_uri: string;
  message: string;
}

function readStoredSession(): StoredAdminSession | null {
  const stored = sessionStorage.getItem(STORAGE_KEY);
  if (!stored) return null;
  try {
    return JSON.parse(stored) as StoredAdminSession;
  } catch {
    sessionStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export const useAdminAuthStore = defineStore("admin-auth", () => {
  const parsed = readStoredSession();
  const accessToken = ref(parsed?.accessToken ?? "");
  const user = ref<User | null>(parsed?.user ?? null);
  const enrollmentOnly = ref(parsed?.enrollmentOnly ?? false);
  const busy = ref(false);
  const error = ref("");
  const router = useRouter();
  const isAuthenticated = computed(
    () =>
      Boolean(accessToken.value && user.value && isPrivilegedRole(user.value.role)) &&
      !enrollmentOnly.value,
  );

  function persist(tokens: BrowserTokenResponse, onlyForEnrollment = false): void {
    accessToken.value = tokens.access_token;
    user.value = tokens.user;
    enrollmentOnly.value = onlyForEnrollment;
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        accessToken: tokens.access_token,
        user: tokens.user,
        enrollmentOnly: onlyForEnrollment,
      } satisfies StoredAdminSession),
    );
  }

  function clear(): void {
    accessToken.value = "";
    user.value = null;
    enrollmentOnly.value = false;
    sessionStorage.removeItem(STORAGE_KEY);
  }

  async function login(loginName: string, password: string, totpCode?: string): Promise<void> {
    busy.value = true;
    error.value = "";
    try {
      const tokens = await apiRequest<BrowserTokenResponse>("/admin/auth/login", {
        method: "POST",
        body: JSON.stringify({
          login: loginName,
          password,
          ...(totpCode ? { totp_code: totpCode } : {}),
        }),
      });
      if (!isPrivilegedRole(tokens.user.role)) {
        throw new Error("该账号没有管理端访问权限");
      }
      try {
        await apiRequest<{ status: string }>("/admin/access-check", {}, tokens.access_token);
      } catch (caught) {
        if (caught instanceof ApiError && caught.body.code === "auth.totp_setup_required") {
          persist(tokens, true);
          await router.push("/totp-setup");
          return;
        }
        throw caught;
      }
      persist(tokens);
      await router.push("/");
    } catch (caught) {
      error.value = caught instanceof Error ? caught.message : "登录失败";
      throw caught;
    } finally {
      busy.value = false;
    }
  }

  async function beginTotpSetup(): Promise<TotpSetupResponse> {
    return apiRequest<TotpSetupResponse>(
      "/admin/totp/setup",
      { method: "POST" },
      accessToken.value,
    );
  }

  async function confirmTotpSetup(code: string): Promise<void> {
    await apiRequest(
      "/admin/totp/confirm",
      { method: "POST", body: JSON.stringify({ code }) },
      accessToken.value,
    );
    clear();
    await router.push("/login");
  }

  async function logout(): Promise<void> {
    try {
      await apiRequest(
        "/admin/auth/logout",
        { method: "POST" },
        accessToken.value || undefined,
      );
    } catch {
      // 即使访问令牌过期，也要优先清理本地状态；服务端会依据 HttpOnly Cookie 撤销会话。
    }
    clear();
    await router.push("/login");
  }

  return {
    accessToken,
    user,
    busy,
    error,
    enrollmentOnly,
    isAuthenticated,
    login,
    beginTotpSetup,
    confirmTotpSetup,
    logout,
  };
});
