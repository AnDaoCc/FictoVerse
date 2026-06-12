document.addEventListener("DOMContentLoaded", () => {
  const I18N = window.__I18N__ || {};
  const tr = (key, fallback = "") => I18N[key] || fallback || key;

  const messages = document.getElementById("messages");
  if (messages) {
    messages.scrollTop = messages.scrollHeight;
  }

  // 主题切换（暗/明）+ 记忆
  const themeToggle = document.getElementById("theme_toggle");
  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      const root = document.documentElement;
      const next = root.dataset.theme === "light" ? "dark" : "light";
      root.dataset.theme = next;
      try {
        localStorage.setItem("nw-theme", next);
      } catch (_err) {
        /* ignore storage errors */
      }
    });
  }

  // 世界详情：标签分区切换（事件委托）
  for (const tabBar of document.querySelectorAll("[data-tabs]")) {
    const scope = tabBar.closest("[data-tabs-scope]") || document;
    tabBar.addEventListener("click", (e) => {
      const btn = e.target.closest(".tab-btn");
      if (!btn) return;
      const target = btn.dataset.tab;
      if (!target) return;
      for (const b of tabBar.querySelectorAll(".tab-btn")) {
        b.classList.toggle("active", b === btn);
      }
      for (const panel of scope.querySelectorAll(".tab-panel")) {
        panel.classList.toggle("active", panel.dataset.panel === target);
      }
    });
    const tabParam = new URLSearchParams(window.location.search).get("tab");
    if (tabParam) {
      const btn = tabBar.querySelector(`.tab-btn[data-tab="${tabParam}"]`);
      if (btn) btn.click();
    }
  }

  const toastRoot = document.getElementById("toast_root");

  const showToast = (kind, text) => {
    if (!toastRoot || !text) return;
    const toast = document.createElement("div");
    toast.className = `toast toast-${kind}`;
    toast.textContent = text;
    toastRoot.appendChild(toast);
    window.setTimeout(() => toast.classList.add("show"), 10);
    window.setTimeout(() => {
      toast.classList.remove("show");
      window.setTimeout(() => toast.remove(), 220);
    }, 4200);
  };

  const showStoppedScreen = () => {
    document.body.innerHTML = `
      <main class="stop-screen">
        <section class="stop-screen-card">
          <h1>${tr("common.stopped_title", "服务已停止")}</h1>
          <p>${tr("common.stopped_hint", "可以关闭此标签页；需要再次使用时，重新双击 启动器.bat。")}</p>
        </section>
      </main>
    `;
  };

  const closeCurrentTab = () => {
    window.open("", "_self");
    window.close();
    window.setTimeout(showStoppedScreen, 350);
  };

  const stopForm = document.getElementById("stop-server-form");
  if (stopForm) {
    stopForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!confirm(tr("common.stop_confirm", "确定要停止服务吗？停止后需要重新双击启动器。"))) return;

      const btn = stopForm.querySelector("button[type='submit']");
      if (btn) {
        btn.disabled = true;
        btn.textContent = tr("common.stopping", "正在停止...");
      }

      try {
        const resp = await fetch("/api/server/stop", { method: "POST" });
        if (resp.ok) {
          closeCurrentTab();
        } else {
          alert(tr("common.stop_failed", "停止失败，请稍后再试。"));
        }
      } catch (_err) {
        closeCurrentTab();
      }
    });
  }

  const pageParams = new URLSearchParams(window.location.search);
  const pageStatus = pageParams.get("status");
  const pageMsg = pageParams.get("msg");
  if (pageStatus && pageMsg) {
    showToast(pageStatus === "success" ? "success" : "error", pageMsg);
    pageParams.delete("status");
    pageParams.delete("msg");
    const nextQuery = pageParams.toString();
    const nextUrl = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ""}`;
    window.history.replaceState({}, "", nextUrl);
  }

  const CUSTOM_VALUE = "__custom__";

  const populateModelSelect = (select, input, models, defaultModel) => {
    if (!select) return;
    const cleaned = [];
    const seen = new Set();
    for (const model of models || []) {
      const value = (model || "").trim();
      if (!value || seen.has(value)) continue;
      seen.add(value);
      cleaned.push(value);
    }

    select.innerHTML = "";
    for (const model of cleaned) {
      const option = document.createElement("option");
      option.value = model;
      option.textContent = model;
      select.appendChild(option);
    }

    let chosen = (defaultModel || "").trim();
    if (chosen && !seen.has(chosen)) {
      const extra = document.createElement("option");
      extra.value = chosen;
      extra.textContent = chosen;
      select.appendChild(extra);
      seen.add(chosen);
    }

    const customOption = document.createElement("option");
    customOption.value = CUSTOM_VALUE;
    customOption.textContent = tr("chat.model_custom", "✏️ 自定义（手动输入）");
    select.appendChild(customOption);

    if (chosen && seen.has(chosen)) {
      select.value = chosen;
    } else if (cleaned.length > 0) {
      chosen = cleaned[0];
      select.value = chosen;
    } else {
      select.value = CUSTOM_VALUE;
      chosen = "";
    }

    if (input) {
      if (select.value === CUSTOM_VALUE && (defaultModel || "").trim()) {
        input.value = (defaultModel || "").trim();
      } else if (chosen) {
        input.value = chosen;
      }
    }

    if (window.NWUi && typeof window.NWUi.syncSelect === "function") {
      window.NWUi.syncSelect(select);
    }
  };

  const bindModelSelect = (select, input) => {
    if (!select || !input) return;
    select.addEventListener("change", () => {
      if (select.value === CUSTOM_VALUE) {
        input.focus();
        input.select();
      } else {
        input.value = select.value;
      }
    });
  };

  const fetchProviderModels = async (providerId) => {
    const resp = await fetch(`/api/providers/${providerId}/models`);
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      throw new Error(data.message || tr("js.models_fetch_fail", "获取模型列表失败"));
    }
    return data;
  };

  const providerSelect = document.getElementById("provider_select");
  const modelInput = document.getElementById("model_input");
  const modelSelect = document.getElementById("model_select");
  const providerHint = document.getElementById("provider_hint");
  const modelSourceHint = document.getElementById("model_source_hint");

  bindModelSelect(modelSelect, modelInput);

  const syncChatProvider = async () => {
    if (!providerSelect) return;
    const option = providerSelect.selectedOptions[0];
    if (!option) return;

    const fallbackModels = (option.dataset.models || "")
      .split("|")
      .map((item) => item.trim())
      .filter(Boolean);
    const defaultModel = option.dataset.defaultModel || "";
    const providerRef = option.value;

    populateModelSelect(modelSelect, modelInput, fallbackModels, defaultModel);

    if (providerHint) {
      providerHint.textContent = tr("chat.provider_hint_ok", "已配置，可直接新建对话。");
    }

    if (modelSourceHint) {
      modelSourceHint.textContent = tr("chat.provider_hint_fetching", "正在从 API 拉取可用模型...");
    }

    try {
      const data = await fetchProviderModels(providerRef);
      populateModelSelect(modelSelect, modelInput, data.models || [], data.default_model || defaultModel);
      if (modelSourceHint) {
        modelSourceHint.textContent =
          data.source === "api"
            ? tr("js.models_fetched", "已从 API 获取 {count} 个模型，可在下拉中选择。").replace(
                "{count}",
                String((data.models || []).length)
              )
            : tr("js.catalog_fallback", "API 不可用，使用预设列表。") +
              (data.error ? `（${data.error}）` : "");
      }
    } catch (err) {
      if (modelSourceHint) {
        const msg = err.message || String(err);
        modelSourceHint.textContent = tr("js.models_fetch_fail_fallback", "拉取失败：{message}，已使用预设列表。").replace(
          "{message}",
          msg
        );
      }
    }
  };

  if (providerSelect) {
    providerSelect.addEventListener("change", () => {
      syncChatProvider();
    });
    syncChatProvider();
  }

  const providerForm = document.getElementById("provider_form");
  const vendorGrid = document.getElementById("vendor_grid");
  const presetSlugInput = document.getElementById("preset_slug");
  const providerNameInput = document.getElementById("provider_name");
  const providerTypeSelect = document.getElementById("provider_type");
  const providerApiKeyInput = document.getElementById("provider_api_key");
  const providerModelInput = document.getElementById("provider_model");
  const providerBaseUrlInput = document.getElementById("provider_base_url");
  const providerModelSelect = document.getElementById("provider_model_select");
  const discoverModelsBtn = document.getElementById("discover_models_btn");
  const modelFetchHint = document.getElementById("model_fetch_hint");

  bindModelSelect(providerModelSelect, providerModelInput);

  const applyPreset = (preset) => {
    if (!preset || !providerForm) return;
    if (presetSlugInput) presetSlugInput.value = preset.slug || "";
    if (providerNameInput) providerNameInput.value = preset.name || "";
    if (providerTypeSelect) providerTypeSelect.value = preset.provider_type || "openai_compatible";
    if (providerBaseUrlInput) providerBaseUrlInput.value = preset.base_url || "";
    if (providerApiKeyInput) {
      providerApiKeyInput.placeholder = preset.api_key_hint || "sk-...";
      providerApiKeyInput.focus();
    }
    populateModelSelect(providerModelSelect, providerModelInput, preset.models || [], preset.default_model || "");
    if (modelFetchHint) modelFetchHint.textContent = "";

    if (vendorGrid) {
      for (const card of vendorGrid.querySelectorAll(".vendor-card")) {
        try {
          const cardPreset = JSON.parse(card.dataset.preset || "{}");
          card.classList.toggle("active", cardPreset.slug === preset.slug);
        } catch (_err) {
          card.classList.remove("active");
        }
      }
    }
    providerForm.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  if (vendorGrid) {
    for (const card of vendorGrid.querySelectorAll(".vendor-card")) {
      card.addEventListener("click", () => {
        try {
          applyPreset(JSON.parse(card.dataset.preset || "{}"));
        } catch (_err) {
          /* ignore malformed preset payload */
        }
      });
    }
  }

  const initialPreset = presetSlugInput?.value?.trim();
  if (initialPreset && vendorGrid) {
    for (const card of vendorGrid.querySelectorAll(".vendor-card")) {
      try {
        const preset = JSON.parse(card.dataset.preset || "{}");
        if (preset.slug === initialPreset) {
          applyPreset(preset);
          break;
        }
      } catch (_err) {
        /* ignore malformed preset payload */
      }
    }
  }

  const setProviderStatus = (providerId, text, kind = "") => {
    const item = document.querySelector(`.provider-item[data-provider-id="${providerId}"]`);
    if (!item) return;
    const status = item.querySelector(".provider-status");
    if (!status) return;
    status.textContent = text;
    status.className = `provider-status${kind ? ` ${kind}` : ""}`;
  };

  for (const btn of document.querySelectorAll(".btn-test-provider")) {
    btn.addEventListener("click", async () => {
      const providerId = btn.dataset.providerId;
      const model = btn.dataset.model || "";
      const originalText = btn.textContent;
      btn.disabled = true;
      btn.textContent = "测试中...";
      setProviderStatus(providerId, "正在测试连接...", "pending");

      try {
        const body = new URLSearchParams();
        if (model) body.set("model", model);
        const resp = await fetch(`/api/providers/${providerId}/test`, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body,
        });
        const data = await resp.json();
        if (!resp.ok || !data.ok) {
          throw new Error(data.message || "连接测试失败");
        }
        const detail = data.reply ? `：${data.reply}` : "";
        setProviderStatus(providerId, `✓ 连接成功${detail}`, "ok");
        showToast("success", `连接成功${detail}`);
      } catch (err) {
        const message = err.message || String(err);
        setProviderStatus(providerId, `✗ ${message}`, "error");
        showToast("error", message);
      } finally {
        btn.disabled = false;
        btn.textContent = originalText;
      }
    });
  }

  for (const btn of document.querySelectorAll(".btn-fetch-provider-models")) {
    btn.addEventListener("click", async () => {
      const providerId = btn.dataset.providerId;
      const originalText = btn.textContent;
      btn.disabled = true;
      btn.textContent = "拉取中...";
      setProviderStatus(providerId, "正在从 API 拉取模型列表...", "pending");

      try {
        const data = await fetchProviderModels(providerId);
        const models = data.models || [];
        setProviderStatus(
          providerId,
          `✓ 获取到 ${models.length} 个模型${models.length ? `，例如 ${models.slice(0, 3).join("、")}` : ""}`,
          "ok",
        );
        showToast("success", `已从 API 获取 ${models.length} 个模型`);
      } catch (err) {
        const message = err.message || String(err);
        setProviderStatus(providerId, `✗ ${message}`, "error");
        showToast("error", message);
      } finally {
        btn.disabled = false;
        btn.textContent = originalText;
      }
    });
  }

  for (const editor of document.querySelectorAll("[data-rel-editor]")) {
    const rowsEl = editor.querySelector(".rel-rows");
    const tpl = editor.querySelector(".rel-row-tpl");
    const hidden = editor.querySelector('input[name="relationships_json"]');
    const form = editor.closest("form");
    if (!rowsEl || !hidden) continue;

    const addBtn = editor.querySelector(".rel-add");
    if (addBtn && tpl) {
      addBtn.addEventListener("click", () => {
        const node = tpl.content.firstElementChild.cloneNode(true);
        rowsEl.appendChild(node);
        window.NWUi?.refreshSelects?.(node);
      });
    }
    rowsEl.addEventListener("click", (e) => {
      const rm = e.target.closest(".rel-remove");
      if (rm) rm.closest(".rel-row")?.remove();
    });
    if (form) {
      form.addEventListener("submit", () => {
        const rels = [];
        for (const row of rowsEl.querySelectorAll(".rel-row")) {
          const target = (row.querySelector(".rel-target")?.value || "").trim();
          if (!target) continue;
          rels.push({
            target,
            type: (row.querySelector(".rel-type")?.value || "").trim(),
            note: (row.querySelector(".rel-note")?.value || "").trim(),
          });
        }
        hidden.value = JSON.stringify(rels);
      });
    }
  }

  const fillImportedValue = (target, mode, text) => {
    if (mode === "json") {
      const trimmed = (text || "").trim();
      try {
        const parsed = JSON.parse(trimmed);
        target.value = JSON.stringify(parsed, null, 2);
      } catch (_err) {
        target.value = JSON.stringify({ 说明: text }, null, 2);
      }
    } else {
      target.value = text || "";
    }
  };

  for (const fileInput of document.querySelectorAll(".import-file")) {
    fileInput.addEventListener("change", async () => {
      const file = fileInput.files && fileInput.files[0];
      if (!file) return;
      const target = document.getElementById(fileInput.dataset.target);
      if (!target) return;
      const mode = fileInput.dataset.mode || "text";
      const wrapper = fileInput.closest(".import-btn");
      const originalLabel = wrapper ? wrapper.firstChild.textContent : "";
      if (wrapper) wrapper.firstChild.textContent = tr("common.importing", "正在解析文件...");

      try {
        const body = new FormData();
        body.append("file", file);
        const resp = await fetch("/api/documents/extract-text", { method: "POST", body });
        const data = await resp.json();
        if (!resp.ok || !data.ok) {
          throw new Error(data.message || tr("common.import_fail", "导入失败"));
        }
        fillImportedValue(target, mode, data.text || "");
        const doneMsg = (tr("common.import_done", "已导入「{filename}」") || "").replace(
          "{filename}",
          data.filename || file.name,
        );
        showToast("success", doneMsg);
      } catch (err) {
        showToast("error", err.message || tr("common.import_fail", "导入失败"));
      } finally {
        if (wrapper) wrapper.firstChild.textContent = originalLabel;
        fileInput.value = "";
      }
    });
  }

  if (discoverModelsBtn) {
    discoverModelsBtn.addEventListener("click", async () => {
      const providerType = providerTypeSelect?.value || "";
      const apiKey = providerApiKeyInput?.value?.trim() || "";
      const baseUrl = providerBaseUrlInput?.value?.trim() || "";

      discoverModelsBtn.disabled = true;
      discoverModelsBtn.textContent = "拉取中...";
      if (modelFetchHint) modelFetchHint.textContent = "正在从 API 拉取模型列表...";

      try {
        const body = new URLSearchParams();
        body.set("provider_type", providerType);
        body.set("api_key", apiKey);
        body.set("base_url", baseUrl);
        const resp = await fetch("/api/providers/discover/models", {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body,
        });
        const data = await resp.json();
        if (!resp.ok || !data.ok) {
          throw new Error(data.message || tr("js.models_fetch_fail", "获取模型列表失败"));
        }
        populateModelSelect(
          providerModelSelect,
          providerModelInput,
          data.models || [],
          data.default_model || "",
        );
        const count = (data.models || []).length;
        if (modelFetchHint) {
          modelFetchHint.textContent = `已从 API 获取 ${count} 个模型，可在下拉中选择。`;
        }
        showToast("success", `已获取 ${count} 个可用模型`);
      } catch (err) {
        const message = err.message || String(err);
        if (modelFetchHint) modelFetchHint.textContent = message;
        showToast("error", message);
      } finally {
        discoverModelsBtn.disabled = false;
        discoverModelsBtn.textContent = "从 API 获取";
      }
    });
  }

  document.querySelectorAll(".card-import-form input[type='file']").forEach((input) => {
    input.addEventListener("change", () => {
      const form = input.closest("form");
      if (form && input.files?.length) form.submit();
    });
  });
});
