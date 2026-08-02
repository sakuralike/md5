import type { BrowserTokenResponse, Session, User } from "@password-detective/api-contract";
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { apiRequest } from "../services/api";

const STORAGE_KEY = "password_detective_session_v2";

interface StoredSession {
  accessToken: string;
  user: User;
}

function readStoredSession(): StoredSession | null {
  const raw = sessionStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StoredSession;
  } catch {
    sessionStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export const useAuthStore = defineStore("auth", () => {
  const restored = readStoredSession();
  const accessToken = ref(restored?.accessToken ?? "");
  const user = ref<User | null>(restored?.user ?? null);
  const busy = ref(false);
  const error = ref("");
  const router = useRouter();

  const isAuthenticated = computed(() => Boolean(accessToken.value && user.value));

  function persist(tokens: BrowserTokenResponse): void {
    accessToken.value = tokens.access_token;
    user.value = tokens.user;
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        accessToken: tokens.access_token,
        user: tokens.user,
      } satisfies StoredSession),
    );
  }

  function clear(): void {
    accessToken.value = "";
    user.value = null;
    sessionStorage.removeItem(STORAGE_KEY);
  }

  async function login(loginName: string, password: string): Promise<void> {
    busy.value = true;
    error.value = "";
    try {
      const tokens = await apiRequest<BrowserTokenResponse>("/web/auth/login", {
        method: "POST",
        body: JSON.stringify({ login: loginName, password }),
      });
      persist(tokens);
      await router.push("/");
    } catch (caught) {
      error.value = caught instanceof Error ? caught.message : "登录失败";
      throw caught;
    } finally {
      busy.value = false;
    }
  }

  async function register(username: string, email: string, password: string): Promise<void> {
    busy.value = true;
    error.value = "";
    try {
      await apiRequest<User>("/auth/register", {
        method: "POST",
        body: JSON.stringify({ username, email, password }),
      });
      await login(username, password);
    } catch (caught) {
      error.value = caught instanceof Error ? caught.message : "注册失败";
      throw caught;
    } finally {
      busy.value = false;
    }
  }

  async function refresh(): Promise<boolean> {
    try {
      const tokens = await apiRequest<BrowserTokenResponse>("/web/auth/refresh", {
        method: "POST",
      });
      persist(tokens);
      return true;
    } catch {
      clear();
      return false;
    }
  }

  async function logout(): Promise<void> {
    try {
      await apiRequest(
        "/web/auth/logout",
        { method: "POST" },
        accessToken.value || undefined,
      );
    } catch {
      // 即使访问令牌过期，也要优先清理本地状态；服务端会依据 HttpOnly Cookie 撤销会话。
    }
    clear();
    await router.push("/login");
  }

  async function listSessions(): Promise<Session[]> {
    return apiRequest<Session[]>("/me/security/sessions", {}, accessToken.value);
  }

  async function revokeSession(id: string): Promise<void> {
    await apiRequest(`/me/security/sessions/${encodeURIComponent(id)}`, { method: "DELETE" }, accessToken.value);
    if ((await listSessions()).every((session) => !session.current)) clear();
  }

  return {
    accessToken,
    user,
    busy,
    error,
    isAuthenticated,
    login,
    register,
    refresh,
    logout,
    listSessions,
    revokeSession,
  };
});
