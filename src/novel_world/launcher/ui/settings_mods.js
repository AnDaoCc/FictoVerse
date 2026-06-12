(function () {
  const $ = (id) => document.getElementById(id);

  let mods = [];

  function api() {
    return window.pywebview && window.pywebview.api;
  }

  function setStatus(text, isErr) {
    const el = $("mod_status");
    if (!el) return;
    el.textContent = text || "";
    el.className = "mod-status" + (isErr ? " err" : text ? " ok" : "");
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function typeLabel(type) {
    const map = {
      python_hooks: "Python",
      frontend: "前端",
      composite: "复合",
      world_content: "世界包",
    };
    return map[type] || type || "—";
  }

  function statusLabel(mod) {
    if (mod.status === "ok" && mod.enabled) return "已启用";
    if (mod.status === "disabled") return "已禁用";
    if (mod.status === "incompatible") return "不兼容";
    if (mod.status === "error") return "错误";
    return mod.status || "—";
  }

  function renderModList(items) {
    const list = $("mod_list");
    if (!list) return;
    if (!items || items.length === 0) {
      list.innerHTML =
        '<p class="muted mod-empty">暂无 MOD。可将 mod.json + 入口文件放入 data/mods/ 目录，或安装 .zip 包。</p>';
      return;
    }
    list.innerHTML = "";
    items.forEach((mod) => {
      const row = document.createElement("div");
      row.className = "mod-row";
      const canToggle = mod.status === "ok" || mod.status === "disabled";
      const errText = mod.error ? `<span class="mod-row-error">${escapeHtml(mod.error)}</span>` : "";
      row.innerHTML = `
        <div class="mod-row-info">
          <strong>${escapeHtml(mod.name || mod.id)}</strong>
          <span class="mod-row-meta">
            <span class="mod-type-tag">${escapeHtml(typeLabel(mod.type))}</span>
            ${mod.version ? `v${escapeHtml(mod.version)}` : ""}
            · ${escapeHtml(statusLabel(mod))}
          </span>
          ${mod.description ? `<span class="mod-row-desc">${escapeHtml(mod.description)}</span>` : ""}
          ${errText}
        </div>
        <div class="mod-row-actions">
          ${
            canToggle
              ? `<label class="mod-toggle"><input type="checkbox" class="mod-enable-cb" data-id="${escapeHtml(mod.id)}" ${
                  mod.enabled ? "checked" : ""
                } /><span>启用</span></label>`
              : ""
          }
          ${
            !mod.builtin && mod.source === "mods"
              ? `<button type="button" class="danger btn-uninstall-mod" data-id="${escapeHtml(mod.id)}">卸载</button>`
              : ""
          }
        </div>
      `;
      list.appendChild(row);
    });
    list.querySelectorAll(".mod-enable-cb").forEach((cb) => {
      cb.addEventListener("change", () => toggleMod(cb.dataset.id, cb.checked, cb));
    });
    list.querySelectorAll(".btn-uninstall-mod").forEach((btn) => {
      btn.addEventListener("click", () => uninstallMod(btn.dataset.id));
    });
  }

  async function loadMods() {
    const a = api();
    if (!a || !a.list_mods) return;
    setStatus("加载中…");
    try {
      const res = await a.list_mods();
      if (!res.ok) {
        setStatus(res.message || "加载失败", true);
        return;
      }
      mods = (res.data && res.data.mods) || [];
      renderModList(mods);
      setStatus("");
    } catch (e) {
      setStatus(String(e), true);
    }
  }

  async function toggleMod(id, enabled, cb) {
    const a = api();
    if (!a || !a.set_mod_enabled) return;
    setStatus("保存中…");
    try {
      const res = await a.set_mod_enabled(id, enabled);
      if (!res.ok) {
        if (cb) cb.checked = !enabled;
        setStatus(res.message || "保存失败", true);
        return;
      }
      setStatus(res.message || "已保存");
      await loadMods();
    } catch (e) {
      if (cb) cb.checked = !enabled;
      setStatus(String(e), true);
    }
  }

  async function openModsDir() {
    const a = api();
    if (!a || !a.open_mods_directory) return;
    try {
      const res = await a.open_mods_directory();
      setStatus(res.ok ? res.message : res.message, !res.ok);
    } catch (e) {
      setStatus(String(e), true);
    }
  }

  async function installZip(file) {
    if (!file) return;
    const a = api();
    if (!a || !a.install_mod_zip) return;
    setStatus("安装中…");
    try {
      const b64 = await fileToBase64(file);
      const res = await a.install_mod_zip(file.name, b64);
      if (!res.ok) {
        setStatus(res.message || "安装失败", true);
        return;
      }
      setStatus(res.message || "已安装");
      await loadMods();
    } catch (e) {
      setStatus(String(e), true);
    }
  }

  async function uninstallMod(id) {
    if (!id || !confirm(`确定卸载 MOD「${id}」？`)) return;
    const a = api();
    if (!a || !a.uninstall_mod) return;
    setStatus("卸载中…");
    try {
      const res = await a.uninstall_mod(id);
      if (!res.ok) {
        setStatus(res.message || "卸载失败", true);
        return;
      }
      setStatus(res.message || "已卸载");
      await loadMods();
    } catch (e) {
      setStatus(String(e), true);
    }
  }

  function fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const dataUrl = reader.result || "";
        const b64 = String(dataUrl).split(",")[1] || "";
        resolve(b64);
      };
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
  }

  function bind() {
    $("btn_refresh_mods")?.addEventListener("click", () => loadMods());
    $("btn_open_mods_dir")?.addEventListener("click", () => openModsDir());
    $("mod_zip_input")?.addEventListener("change", (ev) => {
      const file = ev.target.files && ev.target.files[0];
      if (file) installZip(file);
      ev.target.value = "";
    });
    document.addEventListener("launcher-api-ready", () => loadMods());
    if (api() && api().list_mods) loadMods();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
