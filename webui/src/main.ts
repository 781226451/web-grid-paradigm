import { NMessageProvider } from "naive-ui";
import { createApp, h } from "vue";

import App from "./App.vue";
import "./styles/tokens.css";

createApp({
  render: () => h(NMessageProvider, null, { default: () => h(App) }),
}).mount("#app");
