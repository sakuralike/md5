import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { apiRequest } from "../services/api";
const STORAGE_KEY = "password_detective_session_v1";
function readStoredSession() {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw)
        return null;
    try {
        return JSON.parse(raw);
    }
    catch {
        sessionStorage.removeItem(STORAGE_KEY);
        return null;
    }
}
export const useAuthStore = defineStore("auth", () => {
    const restored = readStoredSession();
    const accessToken = ref(restored?.accessToken ?? "");
    const refreshToken = ref(restored?.refreshToken ?? "");
    const user = ref(restored?.user ?? null);
    const busy = ref(false);
    const error = ref("");
    const router = useRouter();
    const isAuthenticated = computed(() => Boolean(accessToken.value && user.value));
    function persist(tokens) {
        accessToken.value = tokens.access_token;
        refreshToken.value = tokens.refresh_token;
        user.value = tokens.user;
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
            accessToken: tokens.access_token,
            refreshToken: tokens.refresh_token,
            user: tokens.user,
        }));
    }
    function clear() {
        accessToken.value = "";
        refreshToken.value = "";
        user.value = null;
        sessionStorage.removeItem(STORAGE_KEY);
    }
    async function login(loginName, password) {
        busy.value = true;
        error.value = "";
        try {
            const tokens = await apiRequest("/auth/login", {
                method: "POST",
                body: JSON.stringify({ login: loginName, password }),
            });
            persist(tokens);
            await router.push("/");
        }
        catch (caught) {
            error.value = caught instanceof Error ? caught.message : "登录失败";
            throw caught;
        }
        finally {
            busy.value = false;
        }
    }
    async function register(username, email, password) {
        busy.value = true;
        error.value = "";
        try {
            await apiRequest("/auth/register", {
                method: "POST",
                body: JSON.stringify({ username, email, password }),
            });
            await login(username, password);
        }
        catch (caught) {
            error.value = caught instanceof Error ? caught.message : "注册失败";
            throw caught;
        }
        finally {
            busy.value = false;
        }
    }
    async function refresh() {
        if (!refreshToken.value)
            return false;
        try {
            const tokens = await apiRequest("/auth/refresh", {
                method: "POST",
                body: JSON.stringify({ refresh_token: refreshToken.value }),
            });
            persist(tokens);
            return true;
        }
        catch {
            clear();
            return false;
        }
    }
    async function logout() {
        if (accessToken.value) {
            try {
                await apiRequest("/auth/logout", { method: "POST" }, accessToken.value);
            }
            catch {
                // 本地仍必须清理失效令牌。
            }
        }
        clear();
        await router.push("/login");
    }
    async function listSessions() {
        return apiRequest("/me/security/sessions", {}, accessToken.value);
    }
    async function revokeSession(id) {
        await apiRequest(`/me/security/sessions/${encodeURIComponent(id)}`, { method: "DELETE" }, accessToken.value);
        if ((await listSessions()).every((session) => !session.current))
            clear();
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
