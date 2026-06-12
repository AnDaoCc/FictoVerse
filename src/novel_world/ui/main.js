import "./app.css";
import { initSettingsNav } from "./js/settings_nav.js";
import { initChatSidebar } from "./js/chat_sidebar.js";

document.addEventListener("DOMContentLoaded", () => {
  initSettingsNav();
  initChatSidebar();
});
