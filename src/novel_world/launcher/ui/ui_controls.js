/**
 * 启动器统一下拉控件（与 Web ui_controls.js 同步，展开时 portal 到 body）
 */
(function () {
  const SKIP = "uiSelectSkip";
  const MENU_MAX_H = 240;

  const getWrap = (menu) => menu._nwPortalWrap || menu.closest(".ui-select");

  const restoreMenuToWrap = (menu) => {
    const wrap = menu._nwPortalWrap;
    if (!wrap || menu.parentNode === wrap) return;
    wrap.appendChild(menu);
  };

  const resetMenuPosition = (menu) => {
    menu.classList.remove("ui-select-menu--above", "is-floating", "ui-select-menu--portaled");
    menu.style.position = "";
    menu.style.top = "";
    menu.style.left = "";
    menu.style.width = "";
    menu.style.maxHeight = "";
    menu.style.zIndex = "";
    menu.style.right = "";
    menu.style.bottom = "";
    restoreMenuToWrap(menu);
    delete menu._nwPortalTrigger;
  };

  const closeAllMenus = (exceptMenu) => {
    document.querySelectorAll(".ui-select-menu").forEach((menu) => {
      if (menu === exceptMenu) return;
      menu.hidden = true;
      resetMenuPosition(menu);
      getWrap(menu)?.querySelector(".ui-select-trigger")?.setAttribute("aria-expanded", "false");
    });
  };

  const portalMenu = (menu) => {
    if (menu.classList.contains("ui-select-menu--portaled")) return;
    const wrap = menu.closest(".ui-select");
    if (!wrap) return;
    menu._nwPortalWrap = wrap;
    document.body.appendChild(menu);
    menu.classList.add("ui-select-menu--portaled");
  };

  const positionMenu = (trigger, menu) => {
    resetMenuPosition(menu);
    portalMenu(menu);
    menu.classList.add("is-floating");
    menu.hidden = false;
    menu._nwPortalTrigger = trigger;

    const rect = trigger.getBoundingClientRect();
    const gap = 4;
    const minW = Math.max(rect.width, 120);

    menu.style.position = "fixed";
    menu.style.zIndex = "10060";
    menu.style.left = `${rect.left}px`;
    menu.style.width = `${minW}px`;
    menu.style.right = "auto";
    menu.style.bottom = "auto";
    menu.style.maxHeight = `${MENU_MAX_H}px`;

    const spaceBelow = window.innerHeight - rect.bottom - gap - 8;
    const spaceAbove = rect.top - gap - 8;
    const contentH = menu.scrollHeight;

    const openAbove = contentH > spaceBelow && spaceAbove >= spaceBelow;
    if (openAbove) {
      menu.classList.add("ui-select-menu--above");
      const h = Math.min(MENU_MAX_H, spaceAbove, contentH);
      menu.style.top = `${Math.max(8, rect.top - h - gap)}px`;
      menu.style.maxHeight = `${Math.max(80, h)}px`;
    } else {
      menu.style.top = `${rect.bottom + gap}px`;
      menu.style.maxHeight = `${Math.max(80, Math.min(MENU_MAX_H, spaceBelow))}px`;
    }

    const menuRect = menu.getBoundingClientRect();
    if (menuRect.right > window.innerWidth - 8) {
      menu.style.left = `${Math.max(8, window.innerWidth - 8 - menuRect.width)}px`;
    }
    if (menuRect.left < 8) {
      menu.style.left = "8px";
    }
  };

  const repositionOpenMenus = () => {
    document.querySelectorAll(".ui-select-menu:not([hidden])").forEach((menu) => {
      const trigger = menu._nwPortalTrigger;
      if (trigger && menu.classList.contains("ui-select-menu--portaled")) {
        positionMenu(trigger, menu);
      }
    });
  };

  const syncTrigger = (select, trigger, valueEl) => {
    const opt = select.selectedOptions[0];
    valueEl.textContent = opt
      ? opt.textContent.trim()
      : select.getAttribute("placeholder") || "—";
    trigger.disabled = select.disabled;
    trigger.classList.toggle("is-disabled", select.disabled);
  };

  const buildMenu = (select, menu, trigger, valueEl) => {
    menu.innerHTML = "";

    const pick = (opt) => {
      if (opt.disabled) return;
      select.value = opt.value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
      closeAllMenus();
      menu.hidden = true;
      resetMenuPosition(menu);
      trigger.setAttribute("aria-expanded", "false");
      buildMenu(select, menu, trigger, valueEl);
      syncTrigger(select, trigger, valueEl);
    };

    const appendOption = (opt) => {
      const li = document.createElement("li");
      li.className = "ui-select-option";
      li.dataset.value = opt.value;
      li.textContent = opt.textContent.trim();
      li.setAttribute("role", "option");
      if (opt.selected) li.classList.add("is-selected");
      li.addEventListener("click", (e) => {
        e.stopPropagation();
        pick(opt);
      });
      menu.appendChild(li);
    };

    for (const child of select.children) {
      if (child.tagName === "OPTGROUP") {
        const group = document.createElement("li");
        group.className = "ui-select-group";
        group.textContent = child.label;
        menu.appendChild(group);
        for (const opt of child.children) {
          if (opt.tagName === "OPTION") appendOption(opt);
        }
      } else if (child.tagName === "OPTION") {
        appendOption(child);
      }
    }
  };

  const enhanceSelect = (select) => {
    if (select.dataset[SKIP] === "1") return;
    if (select.closest(".ui-select")) return;

    select.classList.add("ui-select-native");

    const wrap = document.createElement("div");
    wrap.className = "ui-select";
    if (select.closest(".wf, .worlds-panel, .settings-card, .card")) {
      wrap.classList.add("ui-select-sm");
    }

    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "ui-select-trigger";
    trigger.setAttribute("aria-haspopup", "listbox");
    trigger.setAttribute("aria-expanded", "false");

    const valueEl = document.createElement("span");
    valueEl.className = "ui-select-value";
    const icon = document.createElement("span");
    icon.className = "ui-select-icon";
    icon.innerHTML =
      '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path fill="currentColor" d="M4 6l4 4 4-4"/></svg>';
    trigger.append(valueEl, icon);

    const menu = document.createElement("ul");
    menu.className = "ui-select-menu";
    menu.hidden = true;
    menu.setAttribute("role", "listbox");

    select.parentNode.insertBefore(wrap, select);
    wrap.append(select, trigger, menu);

    const refresh = () => {
      buildMenu(select, menu, trigger, valueEl);
      syncTrigger(select, trigger, valueEl);
    };

    trigger.addEventListener("click", (e) => {
      e.stopPropagation();
      if (select.disabled) return;
      const willOpen = menu.hidden;
      closeAllMenus(willOpen ? menu : null);
      if (willOpen) {
        refresh();
        positionMenu(trigger, menu);
        trigger.setAttribute("aria-expanded", "true");
      } else {
        menu.hidden = true;
        resetMenuPosition(menu);
        trigger.setAttribute("aria-expanded", "false");
      }
    });

    select.addEventListener("change", refresh);
    new MutationObserver(refresh).observe(select, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["selected", "disabled"],
    });

    select._nwUiRefresh = refresh;
    refresh();
  };

  const syncSelect = (select) => {
    if (!select || typeof select._nwUiRefresh !== "function") return;
    select._nwUiRefresh();
  };

  const initUiSelects = (root = document) => {
    root.querySelectorAll("select:not(.ui-select-native)").forEach(enhanceSelect);
  };

  document.addEventListener("click", (e) => {
    if (e.target.closest(".ui-select-trigger, .ui-select-menu")) return;
    closeAllMenus();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeAllMenus();
  });

  window.addEventListener(
    "scroll",
    (e) => {
      if (e.target.closest?.(".ui-select-menu")) return;
      const hasOpen = document.querySelector(".ui-select-menu:not([hidden])");
      if (!hasOpen) return;
      if (e.target === document || e.target === document.documentElement || e.target === document.body) {
        closeAllMenus();
        return;
      }
      repositionOpenMenus();
    },
    true
  );

  window.addEventListener("resize", () => {
    const hasOpen = document.querySelector(".ui-select-menu:not([hidden])");
    if (hasOpen) repositionOpenMenus();
    else closeAllMenus();
  });

  document.addEventListener("DOMContentLoaded", () => initUiSelects());

  window.NWUi = { refreshSelects: initUiSelects, syncSelect };
})();
