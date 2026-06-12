document.addEventListener("DOMContentLoaded", () => {
  const I18N = window.__I18N__ || {};
  const t = (key, fallback = "") => I18N[key] || fallback || key;

  const composer = document.getElementById("roleplay-composer")
    || document.getElementById("chat-composer")
    || document.getElementById("group-composer");
  const sessionId = composer?.dataset.sessionId;
  const messagesEl = document.getElementById("messages");
  if (!sessionId || !messagesEl) return;

  const isGroup = !!document.getElementById("group-composer");
  const showThinking = !!(window.__USER_PREFS__ && window.__USER_PREFS__.show_thinking);

  const renderMarkdown = (text) => {
    if (!text) return "";
    try {
      if (typeof marked !== "undefined" && marked.parse) {
        return marked.parse(text, { breaks: true, gfm: true });
      }
    } catch (_e) { /* fall through */ }
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  };

  const attachActions = (wrap) => {
    if (!wrap || wrap.querySelector(".msg-actions")) return;
    const mid = wrap.dataset.messageId;
    if (!mid) return;
    const role = wrap.classList.contains("user") ? "user" : "assistant";
    const isCharMsg = wrap.classList.contains("group-msg") || wrap.querySelector(".assistant-row");
    if (role === "assistant" && isGroup && !wrap.classList.contains("group-msg") && !wrap.querySelector("[data-speaker-name]")) {
      /* group: only character assistant messages */
    }

    const bar = document.createElement("div");
    bar.className = "msg-actions";
    bar.innerHTML = `
      <button type="button" data-op="edit" title="${t("msg_ops.edit", "编辑")}">✎</button>
      <button type="button" data-op="delete" title="${t("msg_ops.delete", "删除")}">🗑</button>
      <button type="button" data-op="regen" title="${t("msg_ops.regenerate", "重新生成")}">↻</button>
      <button type="button" data-op="swipe-prev" title="${t("msg_ops.swipe_prev", "上一条")}">‹</button>
      <button type="button" data-op="swipe-next" title="${t("msg_ops.swipe_next", "下一条")}">›</button>
      <button type="button" data-op="remember" title="${t("msg_ops.remember", "记住")}">★</button>
    `;
    if (role === "user") {
      bar.querySelector('[data-op="regen"]')?.remove();
      bar.querySelector('[data-op="swipe-prev"]')?.remove();
      bar.querySelector('[data-op="swipe-next"]')?.remove();
    }
    if (isGroup && role === "assistant" && !wrap.classList.contains("group-msg")) {
      bar.querySelector('[data-op="regen"]')?.remove();
    }
    wrap.classList.add("msg-wrap");
    wrap.appendChild(bar);

    bar.addEventListener("click", async (e) => {
      const btn = e.target.closest("button[data-op]");
      if (!btn) return;
      const op = btn.dataset.op;
      const contentEl = wrap.querySelector(".content");
      const text = contentEl?.textContent?.trim() || "";

      if (op === "remember" && window.__sessionTools) {
        await window.__sessionTools.pinMemory(text, mid);
        return;
      }
      if (op === "delete") {
        if (!confirm(t("msg_ops.delete_confirm", "删除此消息？"))) return;
        const cascade = confirm(t("msg_ops.delete_cascade", "同时删除后续消息（分支）？"));
        const body = new URLSearchParams();
        body.set("cascade", cascade ? "1" : "0");
        await fetch(`/api/sessions/${sessionId}/messages/${mid}/delete`, { method: "POST", body });
        if (cascade) {
          let found = false;
          messagesEl.querySelectorAll(".message, .rp-message").forEach((el) => {
            if (el.dataset.messageId === mid) found = true;
            if (found) el.remove();
          });
        } else {
          wrap.remove();
        }
        return;
      }
      if (op === "edit") {
        if (wrap.querySelector(".msg-edit-form")) return;
        const form = document.createElement("div");
        form.className = "msg-edit-form";
        const ta = document.createElement("textarea");
        ta.className = "msg-edit-input";
        ta.value = text;
        const actions = document.createElement("div");
        actions.className = "msg-edit-actions";
        const forkLabel = document.createElement("label");
        forkLabel.className = "msg-fork-label";
        forkLabel.innerHTML = `<input type="checkbox" id="msg_fork_${mid}" /> ${t("msg_ops.fork_branch", "创建分支")}`;
        const saveBtn = document.createElement("button");
        saveBtn.type = "button";
        saveBtn.textContent = t("common.save", "保存");
        const cancelBtn = document.createElement("button");
        cancelBtn.type = "button";
        cancelBtn.className = "ghost";
        cancelBtn.textContent = t("common.cancel", "取消");
        actions.append(forkLabel, saveBtn, cancelBtn);
        form.append(ta, actions);
        if (contentEl) contentEl.style.display = "none";
        wrap.appendChild(form);
        ta.focus();

        const closeEdit = () => {
          form.remove();
          if (contentEl) contentEl.style.display = "";
        };
        cancelBtn.addEventListener("click", closeEdit);
        saveBtn.addEventListener("click", async () => {
          const next = ta.value.trim();
          if (!next || next === text) {
            closeEdit();
            return;
          }
          const body = new URLSearchParams();
          body.set("content", next);
          const forkEl = document.getElementById(`msg_fork_${mid}`);
          if (forkEl && forkEl.checked) body.set("fork", "1");
          const resp = await fetch(`/api/sessions/${sessionId}/messages/${mid}/edit`, { method: "POST", body });
          const data = await resp.json();
          if (data.ok && contentEl) {
            if (wrap.classList.contains("user")) {
              contentEl.textContent = next;
            } else {
              contentEl.innerHTML = renderMarkdown(next);
            }
          }
          closeEdit();
        });
        return;
      }
      if (op === "swipe-prev" || op === "swipe-next") {
        const body = new URLSearchParams();
        body.set("direction", op === "swipe-prev" ? "prev" : "next");
        const resp = await fetch(`/api/sessions/${sessionId}/messages/${mid}/swipe`, { method: "POST", body });
        const data = await resp.json();
        if (data.ok && contentEl) {
          contentEl.innerHTML = renderMarkdown(data.message.content);
        }
        return;
      }
      if (op === "regen") {
        await streamRegenerate(mid, wrap);
      }
    });
  };

  const streamRegenerate = async (mid, wrap) => {
    const contentEl = wrap.querySelector(".content");
    if (contentEl) contentEl.textContent = t("chat.sending", "正在思考…");
    const body = new URLSearchParams();
    body.set("swipe", "1");
    const resp = await fetch(`/api/sessions/${sessionId}/messages/${mid}/regenerate`, { method: "POST", body });
    if (!resp.ok || !resp.body) {
      if (contentEl) contentEl.textContent = t("common.error", "错误");
      return;
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let contentText = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const part of parts) {
        const dataLine = part.split("\n").find((l) => l.startsWith("data: "));
        if (!dataLine) continue;
        let payload;
        try {
          payload = JSON.parse(dataLine.slice(6));
        } catch (_e) {
          continue;
        }
        if (payload.kind === "content" || payload.text) {
          contentText += payload.text || "";
          if (contentEl) contentEl.innerHTML = renderMarkdown(contentText);
        }
      }
    }
  };

  messagesEl.querySelectorAll(".message[data-message-id], .rp-message[data-message-id]").forEach(attachActions);

  const observer = new MutationObserver((mutations) => {
    for (const m of mutations) {
      m.addedNodes.forEach((node) => {
        if (node.nodeType !== 1) return;
        if (node.matches?.("[data-message-id]")) attachActions(node);
        node.querySelectorAll?.("[data-message-id]").forEach(attachActions);
      });
    }
  });
  observer.observe(messagesEl, { childList: true, subtree: true });
});
