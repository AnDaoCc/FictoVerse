(function () {
  const $ = (id) => document.getElementById(id);

  let catalog = [];
  let busy = false;

  function api() {
    return window.pywebview && window.pywebview.api;
  }

  function setStatus(text, isErr) {
    const el = $("provider_status");
    if (!el) return;
    el.textContent = text || "";
    el.className = "provider-status" + (isErr ? " err" : text ? " ok" : "");
  }

  function applyPreset(slug) {
    const preset = catalog.find((p) => p.slug === slug);
    if (!preset) return;
    if ($("prov_name")) $("prov_name").value = preset.name || "";
    if ($("prov_type")) $("prov_type").value = preset.provider_type || "";
    if ($("prov_base_url")) $("prov_base_url").value = preset.base_url || "";
    if ($("prov_model")) $("prov_model").value = preset.default_model || "";
    if ($("prov_preset_slug")) $("prov_preset_slug").value = preset.slug || "";
    const hint = $("prov_api_key_hint");
    if (hint) hint.textContent = preset.api_key_hint ? `提示：${preset.api_key_hint}` : "";
  }

  function renderCatalogSelect(items) {
    const sel = $("prov_vendor_select");
    if (!sel) return;
    sel.innerHTML = '<option value="">— 选择厂商预设 —</option>';
    items.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.slug;
      opt.textContent = p.name + (p.vendor ? ` (${p.vendor})` : "");
      sel.appendChild(opt);
    });
  }

  function renderProviderList(items) {
    const list = $("provider_list");
    if (!list) return;
    if (!items || items.length === 0) {
      list.innerHTML = '<p class="muted provider-empty">尚未配置 API 提供商。添加后即可在 Web 聊天中使用。</p>';
      return;
    }
    list.innerHTML = "";
    items.forEach((p) => {
      const row = document.createElement("div");
      row.className = "provider-row";
      row.innerHTML = `
        <div class="provider-row-info">
          <strong>${escapeHtml(p.name)}</strong>
          <span class="provider-row-meta">${escapeHtml(p.type)} · ${escapeHtml(p.model || "未指定模型")}</span>
          ${p.api_key_masked ? `<span class="provider-row-meta">Key: ${escapeHtml(p.api_key_masked)}</span>` : ""}
        </div>
        <div class="provider-row-actions">
          <button type="button" class="ghost btn-test-prov" data-id="${escapeAttr(p.id)}">测试</button>
          <button type="button" class="danger btn-del-prov" data-id="${escapeAttr(p.id)}">删除</button>
        </div>
      `;
      list.appendChild(row);
    });
    list.querySelectorAll(".btn-test-prov").forEach((btn) => {
      btn.addEventListener("click", () => testProvider(btn.dataset.id, btn));
    });
    list.querySelectorAll(".btn-del-prov").forEach((btn) => {
      btn.addEventListener("click", () => deleteProvider(btn.dataset.id));
    });
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, "&#39;");
  }

  async function loadProviders() {
    const a = api();
    if (!a) return;
    setStatus("加载中…", false);
    try {
      const [catRes, listRes] = await Promise.all([
        a.list_vendor_catalog(),
        a.list_providers(),
      ]);
      if (catRes && catRes.ok) {
        catalog = catRes.data || [];
        renderCatalogSelect(catalog);
      }
      if (listRes && listRes.ok) {
        renderProviderList(listRes.data || []);
        setStatus("", false);
      } else {
        setStatus((listRes && listRes.message) || "加载失败", true);
      }
    } catch (e) {
      setStatus(String(e), true);
    }
    updateWebSettingsLink();
  }

  function updateWebSettingsLink() {
    const link = $("link_web_settings");
    if (!link || !api()) return;
    api()
      .get_status()
      .then((st) => {
        if (st && st.running && st.url) {
          link.href = st.url.replace(/\/$/, "") + "/settings";
          link.hidden = false;
        } else {
          link.hidden = true;
        }
      })
      .catch(() => {
        link.hidden = true;
      });
  }

  async function createProvider() {
    if (busy || !api()) return;
    busy = true;
    setStatus("保存中…", false);
    const btn = $("btn_add_provider");
    if (btn) btn.disabled = true;
    try {
      const res = await api().create_provider(
        $("prov_name")?.value || "",
        $("prov_type")?.value || "",
        $("prov_api_key")?.value || "",
        $("prov_base_url")?.value || "",
        $("prov_model")?.value || "",
        $("prov_preset_slug")?.value || $("prov_vendor_select")?.value || ""
      );
      if (res && res.ok) {
        setStatus(res.message || "已添加", false);
        if ($("prov_api_key")) $("prov_api_key").value = "";
        await loadProviders();
      } else {
        setStatus((res && res.message) || "添加失败", true);
      }
    } catch (e) {
      setStatus(String(e), true);
    } finally {
      busy = false;
      if (btn) btn.disabled = false;
    }
  }

  async function testProvider(id, btn) {
    if (busy || !api()) return;
    busy = true;
    if (btn) btn.disabled = true;
    setStatus("测试连接中…", false);
    try {
      const res = await api().test_provider(id, $("prov_model")?.value || "");
      setStatus((res && res.message) || (res && res.ok ? "连接成功" : "测试失败"), !(res && res.ok));
    } catch (e) {
      setStatus(String(e), true);
    } finally {
      busy = false;
      if (btn) btn.disabled = false;
    }
  }

  async function deleteProvider(id) {
    if (busy || !api() || !confirm("确定删除该 API 提供商？关联对话将被清理。")) return;
    busy = true;
    setStatus("删除中…", false);
    try {
      const res = await api().delete_provider(id);
      setStatus((res && res.message) || (res && res.ok ? "已删除" : "删除失败"), !(res && res.ok));
      if (res && res.ok) await loadProviders();
    } catch (e) {
      setStatus(String(e), true);
    } finally {
      busy = false;
    }
  }

  function fileToB64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const raw = String(reader.result || "");
        const comma = raw.indexOf(",");
        resolve(comma >= 0 ? raw.slice(comma + 1) : raw);
      };
      reader.onerror = () => reject(reader.error || new Error("read failed"));
      reader.readAsDataURL(file);
    });
  }

  async function importStPreset(file) {
    const statusEl = $("st_preset_status");
    if (!api() || !file) return;
    if (busy) return;
    busy = true;
    if (statusEl) {
      statusEl.textContent = "导入中…";
      statusEl.className = "provider-status";
    }
    try {
      const b64 = await fileToB64(file);
      const res = await api().import_st_preset(file.name || "preset.json", b64);
      const ok = res && res.ok;
      if (statusEl) {
        statusEl.textContent = (res && res.message) || (ok ? "预设已导入" : "导入失败");
        statusEl.className = "provider-status" + (ok ? " ok" : " err");
      }
    } catch (e) {
      if (statusEl) {
        statusEl.textContent = String(e);
        statusEl.className = "provider-status err";
      }
    } finally {
      busy = false;
    }
  }

  function bindEvents() {
    const presetInput = $("st_preset_input");
    if (presetInput) {
      presetInput.addEventListener("change", async (ev) => {
        const file = ev.target.files && ev.target.files[0];
        ev.target.value = "";
        if (file) await importStPreset(file);
      });
    }
    const vendorSel = $("prov_vendor_select");
    if (vendorSel) {
      vendorSel.addEventListener("change", () => {
        applyPreset(vendorSel.value);
      });
    }
    const addBtn = $("btn_add_provider");
    if (addBtn) addBtn.addEventListener("click", createProvider);
    const webLink = $("link_web_settings");
    if (webLink) {
      webLink.addEventListener("click", (e) => {
        e.preventDefault();
        if (webLink.hidden || !api()) return;
        api().open_browser("/settings");
      });
    }
  }

  document.addEventListener("DOMContentLoaded", bindEvents);

  window.NWSettings = { onShow: loadProviders, refresh: loadProviders };
})();
