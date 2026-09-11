import { createPinia } from "pinia";
import { createApp } from "vue";
import { initializeTheme } from "@password-detective/web-ui/theme";
import "./index.css";
import App from "./App.vue";
import router from "./router";

initializeTheme();
createApp(App).use(createPinia()).use(router).mount("#app");
