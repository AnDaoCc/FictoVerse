/**

 * 主导航侧栏与会话侧栏独立收起/展开，状态持久化到 localStorage。

 */

(function () {

  const I18N = window.__I18N__ || {};

  const tr = (key, fallback = "") => I18N[key] || fallback || key;



  const NAV_KEY = "nw-nav-sidebar-collapsed";

  const CHAT_KEY = "nw-chat-sidebar-collapsed";



  const readFlag = (key) => {

    try {

      return localStorage.getItem(key) === "1";

    } catch (_e) {

      return false;

    }

  };



  const writeFlag = (key, collapsed) => {

    try {

      localStorage.setItem(key, collapsed ? "1" : "0");

    } catch (_e) {

      /* ignore */

    }

  };



  const setNavCollapsed = (collapsed) => {

    const shell = document.querySelector(".app-shell");

    const sidebar = document.getElementById("nav_sidebar");

    const btn = document.getElementById("nav_sidebar_toggle");

    if (!shell || !sidebar) return;

    shell.classList.toggle("nav-sidebar-collapsed", collapsed);

    sidebar.classList.toggle("is-collapsed", collapsed);

    if (btn) {

      btn.setAttribute("aria-expanded", collapsed ? "false" : "true");

      btn.setAttribute(

        "aria-label",

        collapsed ? tr("sidebar.expand_nav", "展开导航栏") : tr("sidebar.collapse_nav", "收起导航栏")

      );

      btn.textContent = collapsed ? "›" : "‹";

    }

    writeFlag(NAV_KEY, collapsed);

  };



  const setChatCollapsed = (collapsed) => {

    const layout = document.querySelector(".chat-layout");

    const sidebar = document.getElementById("chat_sidebar");

    const btn = document.getElementById("chat_sidebar_toggle");

    const expandBtn = document.getElementById("chat_sidebar_expand");

    if (!layout || !sidebar) return;

    layout.classList.toggle("chat-sidebar-collapsed", collapsed);

    sidebar.classList.toggle("is-collapsed", collapsed);

    if (btn) {

      btn.hidden = collapsed;

      btn.setAttribute("aria-expanded", collapsed ? "false" : "true");

      btn.setAttribute(

        "aria-label",

        collapsed ? tr("sidebar.expand_chat", "展开会话侧栏") : tr("sidebar.collapse_chat", "收起会话侧栏")

      );

      btn.textContent = collapsed ? "›" : "‹";

    }

    if (expandBtn) {

      expandBtn.hidden = !collapsed;

      expandBtn.setAttribute("aria-label", tr("sidebar.expand_chat", "展开会话侧栏"));

    }

    writeFlag(CHAT_KEY, collapsed);

  };



  const init = () => {

    const shell = document.querySelector(".app-shell");

    const navBtn = document.getElementById("nav_sidebar_toggle");

    if (navBtn && shell) {

      setNavCollapsed(readFlag(NAV_KEY));

      document.documentElement.classList.remove("nav-sidebar-collapsed-boot");

      navBtn.addEventListener("click", () => {

        setNavCollapsed(!shell.classList.contains("nav-sidebar-collapsed"));

      });

    }



    const layout = document.querySelector(".chat-layout");

    const chatBtn = document.getElementById("chat_sidebar_toggle");

    const chatExpand = document.getElementById("chat_sidebar_expand");

    if (layout && document.getElementById("chat_sidebar")) {

      setChatCollapsed(readFlag(CHAT_KEY));

      chatBtn?.addEventListener("click", () => {

        setChatCollapsed(!layout.classList.contains("chat-sidebar-collapsed"));

      });

      chatExpand?.addEventListener("click", () => setChatCollapsed(false));

    }

  };



  if (document.readyState === "loading") {

    document.addEventListener("DOMContentLoaded", init);

  } else {

    init();

  }

})();


