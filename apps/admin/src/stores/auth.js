import { isPrivilegedRole } from "@password-detective/api-contract";
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { apiRequest } from "../services/api";
const STORAGE_KEY = "password_detective_admin_session_v1";
function readStoredSession() {
    const stored = sessionStorage.getItem(STORAGE_KEY);
    if (!stored)
        return null;
    try {
        return JSON.parse(stored);
    }
    catch {
        sessionStorage.removeItem(STORAGE_KEY);
        return null;
    }
}
export const useAdminAuthStore = defineStore("admin-auth", () => {
    const parsed = readStoredSession();
    const accessToken = ref(parsed?.accessToken ?? "");
    const user = ref(parsed?.user ?? null);
    const busy = ref(false);
    const error = ref("");
    const router = useRouter();
    const isAuthenticated = computed(() => Boolean(accessToken.value && user.value && isPrivilegedRole(user.value.role)));
    async function login(loginName, password) {
        busy.value = true;
        error.value = "";
        try {
            const tokens = await apiRequest("/auth/login", {
                method: "POST",
                body: JSON.stringify({ login: loginName, password }),
            });
            if (!isPrivilegedRole(tokens.user.role)) {
                throw new Error("该账号没有管理端访问权限");
            }
            await apiRequest("/admin/access-check", {}, tokens.access_token);
            accessToken.value = tokens.access_token;
            user.value = tokens.user;
            sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ accessToken: tokens.access_token, user: tokens.user }));
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
    async function logout() {
        if (accessToken.value) {
            try {
                await apiRequest("/auth/logout", { method: "POST" }, accessToken.value);
            }
            catch { /* 清理本地状态 */ }
        }
        accessToken.value = "";
        user.value = null;
        sessionStorage.removeItem(STORAGE_KEY);
        await router.push("/login");
    }
    return { accessToken, user, busy, error, isAuthenticated, login, logout };
});
