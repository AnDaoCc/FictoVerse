document.addEventListener("DOMContentLoaded", () => {
  const I18N = window.__I18N__ || {};
  const t = (key, fallback = "") => I18N[key] || fallback || key;

  const promptPanel = document.getElementById("prompt-panel");
  const memoryPanel = document.getElementById("memory-panel");
  const sessionId = promptPanel?.dataset.sessionId || memoryPanel?.dataset.sessionId;
  if (!sessionId) return;

  const inputEl = document.getElementById("roleplay_input")
    || document.getElementById("chat_input")
    || document.getElementById("group_input");

  const $ = (id) => document.getElementById(id);
  const saveBtn = document.getElementById("save_session_config");
  const previewBtn = document.getElementById("preview_prompt_btn");
  const modal = document.getElementById("prompt_preview_modal");

  const collectConfig = () => ({
    lore_token_budget: parseInt(document.getElementById("cfg_lore_budget")?.value || "2000", 10),
    generation: {
      temperature: parseFloat(document.getElementById("cfg_temperature")?.value || "0.8"),
      top_p: parseFloat(document.getElementById("cfg_top_p")?.value || "1"),
      max_tokens: parseInt(document.getElementById("cfg_max_tokens")?.value || "512", 10),
      repetition_penalty: 1.0,
      stop: [],
    },
    prompt_layers: {
      main: document.getElementById("cfg_layer_main")?.value || "",
      system_extra: document.getElementById("cfg_layer_system_extra")?.value || "",
      jailbreak: document.getElementById("cfg_layer_jailbreak")?.value || "",
      post_history: document.getElementById("cfg_layer_post")?.value || "",
      authors_note: {
        content: document.getElementById("cfg_authors_note")?.value || "",
        depth: parseInt(document.getElementById("cfg_authors_depth")?.value || "4", 10),
      },
      template: document.getElementById("cfg_template")?.value || "chat",
    },
  });

  document.getElementById("import_session_preset")?.addEventListener("change", async (ev) => {
    const file = ev.target.files && ev.target.files[0];
    ev.target.value = "";
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    const resp = await fetch(`/api/sessions/${sessionId}/import-preset`, {
      method: "POST",
      body: form,
    });
    const data = await resp.json();
    if (!data.ok) {
      alert(data.message || t("common.error", "错误"));
      return;
    }
    const cfg = data.config || {};
    const gen = cfg.generation || {};
    const layers = cfg.prompt_layers || {};
    const an = layers.authors_note || {};
    if ($("cfg_temperature")) $("cfg_temperature").value = gen.temperature ?? 0.8;
    if ($("cfg_top_p")) $("cfg_top_p").value = gen.top_p ?? 1;
    if ($("cfg_max_tokens")) $("cfg_max_tokens").value = gen.max_tokens ?? 512;
    if ($("cfg_layer_main")) $("cfg_layer_main").value = layers.main || "";
    if ($("cfg_layer_system_extra")) $("cfg_layer_system_extra").value = layers.system_extra || "";
    if ($("cfg_layer_jailbreak")) $("cfg_layer_jailbreak").value = layers.jailbreak || "";
    if ($("cfg_layer_post")) $("cfg_layer_post").value = layers.post_history || "";
    if ($("cfg_authors_note")) $("cfg_authors_note").value = an.content || "";
    if ($("cfg_authors_depth")) $("cfg_authors_depth").value = an.depth ?? 4;
    alert(t("session.st_preset_imported", "预设已导入到本会话"));
  });

  saveBtn?.addEventListener("click", async () => {
    const resp = await fetch(`/api/sessions/${sessionId}/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectConfig()),
    });
    const data = await resp.json();
    if (!data.ok) alert(data.message || t("common.error", "错误"));
  });

  const openModal = () => {
    if (modal) {
      modal.classList.remove("hidden");
      modal.setAttribute("aria-hidden", "false");
    }
  };
  const closeModal = () => {
    if (modal) {
      modal.classList.add("hidden");
      modal.setAttribute("aria-hidden", "true");
    }
  };

  modal?.querySelectorAll("[data-close-modal]").forEach((el) => {
    el.addEventListener("click", closeModal);
  });

  previewBtn?.addEventListener("click", async () => {
    const content = inputEl?.value?.trim() || "";
    const url = `/api/sessions/${sessionId}/prompt-preview?content=${encodeURIComponent(content)}`;
    const resp = await fetch(url);
    const data = await resp.json();
    document.getElementById("preview_system").textContent = data.system || "";
    document.getElementById("preview_messages").textContent = JSON.stringify(data.messages || [], null, 2);
    document.getElementById("preview_meta").textContent = `${t("session.estimated_tokens", "估算词元数")}: ${data.estimated_tokens || 0} · ${t("session.preview_lore_matched", "命中知识库")}: ${(data.lore_matched || []).length} · ${t("session.memory_injected", "记忆条数")}: ${(data.memory_injected || []).length}`;
    openModal();
  });

  const refreshMemories = async () => {
    const list = document.getElementById("memory_list");
    if (!list) return;
    const resp = await fetch(`/api/sessions/${sessionId}/memories`);
    const data = await resp.json();
    list.innerHTML = "";
    const items = data.memories || [];
    if (!items.length) {
      list.innerHTML = `<li class="muted memory-empty">${t("session.memory_empty", "暂无记忆")}</li>`;
      return;
    }
    for (const m of items) {
      const li = document.createElement("li");
      li.className = "memory-item";
      li.dataset.id = m.id;
      const text = m.content.length > 80 ? `${m.content.slice(0, 80)}…` : m.content;
      const pinLabel = m.pinned ? "📌" : "☆";
      li.innerHTML = `<span class="memory-content">${text}</span><button type="button" class="ghost memory-pin-toggle" data-id="${m.id}" data-pinned="${m.pinned ? "1" : "0"}" title="${t("session.toggle_pin", "切换固定")}">${pinLabel}</button><button type="button" class="icon-danger memory-delete" data-id="${m.id}">×</button>`;
      list.appendChild(li);
    }
    bindMemoryActions();
  };

  const bindMemoryActions = () => {
    document.querySelectorAll(".memory-delete").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.id;
        if (!id) return;
        await fetch(`/api/sessions/${sessionId}/memories/${id}/delete`, { method: "POST" });
        refreshMemories();
      });
    });
    document.querySelectorAll(".memory-pin-toggle").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.id;
        if (!id) return;
        const nextPinned = btn.dataset.pinned === "1" ? "0" : "1";
        const body = new URLSearchParams();
        body.set("pinned", nextPinned);
        await fetch(`/api/sessions/${sessionId}/memories/${id}/pin`, { method: "POST", body });
        refreshMemories();
      });
    });
  };
  bindMemoryActions();

  window.__sessionTools = {
    pinMemory: async (content, messageId = "") => {
      const body = new URLSearchParams();
      body.set("content", content);
      if (messageId) body.set("message_id", messageId);
      body.set("pinned", "1");
      await fetch(`/api/sessions/${sessionId}/memories`, { method: "POST", body });
      refreshMemories();
    },
    refreshMemories,
  };

  document.getElementById("remember_btn")?.addEventListener("click", async () => {
    const text = inputEl?.value?.trim();
    if (!text) return;
    await window.__sessionTools.pinMemory(text);
    if (inputEl) inputEl.value = "";
  });

  const lorePanel = document.getElementById("session-lore-panel");
  const loreList = document.getElementById("session_lore_list");
  const loreExport = document.getElementById("session_lore_export_st");

  const refreshSessionLore = async () => {
    if (!loreList) return;
    const resp = await fetch(`/api/sessions/${sessionId}/lore`);
    const data = await resp.json();
    const items = data.entries || [];
    loreList.innerHTML = "";
    if (!items.length) {
      loreList.innerHTML = `<li class="muted memory-empty">${t("session.session_lore_empty", "暂无会话 Lore")}</li>`;
      return;
    }
    for (const entry of items) {
      const li = document.createElement("li");
      li.className = "memory-item session-lore-item";
      li.dataset.id = entry.id;
      const keys = (entry.keys || []).join(", ") || t("session.session_lore_constant", "常驻");
      const preview = (entry.content || "").slice(0, 60);
      li.innerHTML = `<span class="memory-content"><strong>${keys}</strong> · ${preview}${(entry.content || "").length > 60 ? "…" : ""}</span><button type="button" class="ghost session-lore-edit" data-id="${entry.id}">✎</button><button type="button" class="icon-danger session-lore-delete" data-id="${entry.id}">×</button>`;
      loreList.appendChild(li);
    }
    loreList.querySelectorAll(".session-lore-delete").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.id;
        if (!id || !confirm(t("common.delete", "删除") + "?")) return;
        await fetch(`/api/sessions/${sessionId}/lore/${id}`, { method: "DELETE" });
        refreshSessionLore();
      });
    });
    loreList.querySelectorAll(".session-lore-edit").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.id;
        const item = items.find((e) => e.id === id);
        if (!item) return;
        const keys = prompt(t("session.session_lore_keys_prompt", "关键词（逗号分隔）"), (item.keys || []).join(", "));
        if (keys === null) return;
        const content = prompt(t("session.session_lore_content_prompt", "内容"), item.content || "");
        if (content === null) return;
        await fetch(`/api/sessions/${sessionId}/lore/${id}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ keys: keys.split(/[,，]/).map((s) => s.trim()).filter(Boolean), content }),
        });
        refreshSessionLore();
      });
    });
  };

  if (lorePanel) {
    if (loreExport) loreExport.href = `/api/sessions/${sessionId}/lore/export-st`;
    refreshSessionLore();
    document.getElementById("session_lore_add_btn")?.addEventListener("click", async () => {
      const keys = prompt(t("session.session_lore_keys_prompt", "关键词（逗号分隔）"), "");
      if (keys === null) return;
      const content = prompt(t("session.session_lore_content_prompt", "内容"), "");
      if (!content) return;
      await fetch(`/api/sessions/${sessionId}/lore`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          keys: keys.split(/[,，]/).map((s) => s.trim()).filter(Boolean),
          content,
          selective: true,
        }),
      });
      refreshSessionLore();
    });
    document.getElementById("session_lore_import_st")?.addEventListener("change", async (ev) => {
      const file = ev.target.files && ev.target.files[0];
      ev.target.value = "";
      if (!file) return;
      const form = new FormData();
      form.append("file", file);
      const resp = await fetch(`/api/sessions/${sessionId}/lore/import-st`, { method: "POST", body: form });
      const data = await resp.json();
      if (!data.ok) alert(data.message || t("common.error", "错误"));
      else refreshSessionLore();
    });
  }

  document.getElementById("save_display_scripts")?.addEventListener("click", async () => {
    const raw = document.getElementById("cfg_display_scripts")?.value?.trim() || "[]";
    let scripts;
    try {
      scripts = JSON.parse(raw);
      if (!Array.isArray(scripts)) throw new Error("must be array");
    } catch (_e) {
      alert(t("session.display_scripts_invalid", "JSON 格式不正确，需为数组。"));
      return;
    }
    const resp = await fetch(`/api/sessions/${sessionId}/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_scripts: scripts }),
    });
    const data = await resp.json();
    if (!data.ok) {
      alert(data.message || t("common.error", "错误"));
      return;
    }
    window.__DISPLAY_SCRIPTS__ = scripts;
  });
});
