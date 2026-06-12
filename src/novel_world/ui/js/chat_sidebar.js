export function initChatSidebar() {
  const sidebar = document.querySelector(".chat-sidebar");
  if (!sidebar) return;

  sidebar.querySelectorAll(".sidebar-zone details.sidebar-panel").forEach((panel) => {
    if (panel.dataset.defaultOpen === "true") {
      panel.open = true;
    }
  });
}
