import { ref } from "vue";
import { useAuthStore } from "../stores/auth";
const auth = useAuthStore();
const username = ref("");
const email = ref("");
const password = ref("");
async function submit() {
    try {
        await auth.register(username.value, email.value, password.value);
    }
    catch { /* store 已处理 */ }
}
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
    for: "username",
});
__VLS_asFunctionalElement1(__VLS_intrinsics.input)({
    id: "username",
    minlength: "3",
    maxlength: "32",
    pattern: "[A-Za-z0-9_]+",
    autocomplete: "username",
    required: true,
});
(__VLS_ctx.username);
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "field" },
});
/** @type {__VLS_StyleScopedClasses['field']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({
    for: "email",
});
__VLS_asFunctionalElement1(__VLS_intrinsics.input)({
    id: "email",
    type: "email",
    autocomplete: "email",
    required: true,
});
(__VLS_ctx.email);
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "field" },
});
/** @type {__VLS_StyleScopedClasses['field']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({
    for: "new-password",
});
__VLS_asFunctionalElement1(__VLS_intrinsics.input)({
    id: "new-password",
    type: "password",
    minlength: "12",
    maxlength: "128",
    autocomplete: "new-password",
    required: true,
});
(__VLS_ctx.password);
__VLS_asFunctionalElement1(__VLS_intrinsics.small, __VLS_intrinsics.small)({
    ...{ class: "muted" },
});
/** @type {__VLS_StyleScopedClasses['muted']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
    ...{ class: "button" },
    disabled: (__VLS_ctx.auth.busy),
});
/** @type {__VLS_StyleScopedClasses['button']} */ ;
(__VLS_ctx.auth.busy ? "创建中…" : "注册并登录");
// @ts-ignore
[submit, auth, auth, auth, auth, username, email, password,];
const __VLS_export = (await import('vue')).defineComponent({});
export default {};
