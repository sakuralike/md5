import { ref } from "vue";
import { useAdminAuthStore } from "../stores/auth";
const auth = useAdminAuthStore();
const loginName = ref("");
const password = ref("");
async function submit() { try {
    await auth.login(loginName.value, password.value);
}
catch { /* store 已处理 */ } }
const __VLS_ctx = {
    ...{},
    ...{},
};
let __VLS_components;
let __VLS_intrinsics;
let __VLS_directives;
__VLS_asFunctionalElement1(__VLS_intrinsics.form, __VLS_intrinsics.form)({
    ...{ onSubmit: (__VLS_ctx.submit) },
    ...{ class: "panel form stack" },
});
/** @type {__VLS_StyleScopedClasses['panel']} */ ;
/** @type {__VLS_StyleScopedClasses['form']} */ ;
/** @type {__VLS_StyleScopedClasses['stack']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "eyebrow" },
});
/** @type {__VLS_StyleScopedClasses['eyebrow']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.h1, __VLS_intrinsics.h1)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({
    ...{ class: "muted" },
});
/** @type {__VLS_StyleScopedClasses['muted']} */ ;
if (__VLS_ctx.auth.error) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({
        ...{ class: "error" },
        role: "alert",
    });
    /** @type {__VLS_StyleScopedClasses['error']} */ ;
    (__VLS_ctx.auth.error);
}
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "field" },
});
/** @type {__VLS_StyleScopedClasses['field']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({
    for: "login",
});
__VLS_asFunctionalElement1(__VLS_intrinsics.input)({
    id: "login",
    autocomplete: "username",
    required: true,
});
(__VLS_ctx.loginName);
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "field" },
});
/** @type {__VLS_StyleScopedClasses['field']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({
    for: "password",
});
__VLS_asFunctionalElement1(__VLS_intrinsics.input)({
    id: "password",
    type: "password",
    autocomplete: "current-password",
    required: true,
});
(__VLS_ctx.password);
__VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
    ...{ class: "button" },
    disabled: (__VLS_ctx.auth.busy),
});
/** @type {__VLS_StyleScopedClasses['button']} */ ;
(__VLS_ctx.auth.busy ? "验证中…" : "登录管理端");
// @ts-ignore
[submit, auth, auth, auth, auth, loginName, password,];
const __VLS_export = (await import('vue')).defineComponent({});
export default {};
