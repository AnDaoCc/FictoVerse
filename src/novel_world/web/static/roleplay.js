document.addEventListener("DOMContentLoaded", () => {
  const I18N = window.__I18N__ || {};
  const t = (key, fallback = "") => I18N[key] || fallback || key;
  const showThinking = !!(window.__USER_PREFS__ && window.__USER_PREFS__.show_thinking);

  const composer = document.getElementById("roleplay-composer");
  const messagesEl = document.getElementById("messages");
  const inputEl = document.getElementById("roleplay_input");
  const sendBtn = document.getElementById("send_btn");

  const avatarUrl = messagesEl?.dataset.avatarUrl || "";
  const charName = messagesEl?.dataset.charName || "";
  const charId = messagesEl?.dataset.characterId || "";
  const charTtsVoice = messagesEl?.dataset.charTtsVoice || "";
  const worldId = messagesEl?.dataset.worldId || "";
  const personaName = messagesEl?.dataset.personaName || t("chat.role_user", "你");

  const scrollToBottom = () => {
    if (messagesEl) messagesEl.scrollTop = messagesEl.scrollHeight;
  };

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

  const escapeHtml = (text) => {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  };

  document.getElementById("greeting_select")?.addEventListener("change", async (ev) => {
    const select = ev.target;
    const sid = select.dataset.sessionId;
    const index = parseInt(select.value, 10);
    const resp = await fetch(`/api/roleplay/sessions/${sid}/greeting`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ greeting_index: index }),
    });
    const data = await resp.json();
    if (!data.ok) {
      alert(data.message || t("common.error", "错误"));
      return;
    }
    const firstBubble = messagesEl?.querySelector(".rp-message.assistant .content");
    if (firstBubble && data.first_message) {
      firstBubble.innerHTML = renderMarkdown(data.first_message);
    }
    scrollToBottom();
  });

  if (!composer) return;

  const sessionId = composer.dataset.sessionId;

  const avatarHtml = (url, name, extraClass = "") => {
    const titleAttr = name ? ` title="${escapeHtml(name)}"` : "";
    if (url) {
      return `<img class="rp-avatar ${extraClass}" src="${escapeHtml(url)}" alt=""${titleAttr} />`;
    }
    const letter = (name || "?")[0];
    return `<div class="rp-avatar fallback ${extraClass}"${titleAttr}>${escapeHtml(letter)}</div>`;
  };

  const appendUser = (content) => {
    const wrap = document.createElement("div");
    wrap.className = "rp-message message user";
    wrap.innerHTML = `
      <div class="rp-row user-row">
        <div class="bubble">
          <div class="role-label">${escapeHtml(personaName)}</div>
          <div class="content">${escapeHtml(content)}</div>
        </div>
        ${avatarHtml("", personaName, "user-fallback")}
      </div>`;
    messagesEl.appendChild(wrap);
    scrollToBottom();
  };

  const appendAssistantShell = () => {
    const wrap = document.createElement("div");
    wrap.className = "rp-message message assistant";
    wrap.innerHTML = `
      <div class="rp-row assistant-row">
        ${avatarHtml(avatarUrl, charName)}
        <div class="bubble">
          <div class="role-label">${escapeHtml(charName)}</div>
          <div class="content">${escapeHtml(t("chat.sending", "正在思考…"))}</div>
        </div>
      </div>`;
    if (charId) wrap.dataset.characterId = charId;
    if (worldId) wrap.dataset.worldId = worldId;
    if (charTtsVoice) wrap.dataset.ttsVoice = charTtsVoice;
    messagesEl.appendChild(wrap);
    scrollToBottom();
    return wrap;
  };

  const finishAssistantMessage = (wrap) => {
    window.__NWMedia?.injectSpeakButtons?.(wrap);
    window.__NWMedia?.autoSpeakMessage?.(wrap);
  };

  const setSending = (on) => {
    sendBtn.disabled = on;
    sendBtn.textContent = on ? t("chat.sending", "正在思考…") : t("chat.send", "发送");
    inputEl.disabled = on;
  };

  const streamChat = async (content) => {
    window.__NWMedia?.stopAll?.();
    appendUser(content);
    const assistantWrap = appendAssistantShell();
    const bubble = assistantWrap.querySelector(".bubble");
    const contentEl = assistantWrap.querySelector(".content");
    let thinkingEl = null;
    let thinkingText = "";
    let contentText = "";

    const body = new URLSearchParams();
    body.set("content", content);

    const resp = await fetch(`/api/roleplay/sessions/${sessionId}/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });

    if (!resp.ok || !resp.body) {
      contentEl.textContent = t("common.error", "错误");
      return;
    }

    contentEl.textContent = "";
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    const processEvent = (event, dataLine) => {
      if (!dataLine) return;
      let payload;
      try {
        payload = JSON.parse(dataLine);
      } catch (_e) {
        return;
      }
      if (event === "thinking" || payload.kind === "thinking") {
        if (!showThinking) return;
        thinkingText += payload.text || "";
        if (!thinkingEl) {
          thinkingEl = document.createElement("details");
          thinkingEl.className = "thinking-block";
          thinkingEl.innerHTML = `<summary>${t("chat.thinking", "思考过程")}</summary><div class="thinking-content"></div>`;
          bubble.insertBefore(thinkingEl, contentEl);
        }
        thinkingEl.querySelector(".thinking-content").textContent = thinkingText;
      } else if (event === "content" || payload.kind === "content") {
        contentText += payload.text || "";
        contentEl.innerHTML = renderMarkdown(contentText);
      } else if (event === "display" || payload.kind === "display") {
        contentText = payload.text || contentText;
        contentEl.innerHTML = renderMarkdown(contentText);
      } else if (event === "done" || payload.kind === "done") {
        contentEl.innerHTML = renderMarkdown(contentText);
        finishAssistantMessage(assistantWrap);
      } else if (event === "error" || payload.kind === "error") {
        contentEl.textContent = payload.text || t("common.error", "错误");
      }
      scrollToBottom();
    };

    const parseSSE = (chunk) => {
      const parts = (buffer + chunk).split("\n\n");
      buffer = parts.pop() || "";
      for (const part of parts) {
        const lines = part.split("\n");
        let event = "message";
        let dataLine = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) event = line.slice(7).trim();
          if (line.startsWith("data: ")) dataLine = line.slice(6);
        }
        processEvent(event, dataLine);
      }
    };

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        parseSSE(decoder.decode(value, { stream: true }));
      }
      if (buffer.trim()) parseSSE("");
    } catch (_err) {
      /* keep partial */
    }
  };

  sendBtn.addEventListener("click", async () => {
    const text = inputEl.value.trim();
    if (!text) return;
    setSending(true);
    try {
      await streamChat(text);
      inputEl.value = "";
    } catch (err) {
      alert(err.message || String(err));
    } finally {
      setSending(false);
    }
  });

  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendBtn.click();
    }
  });

  if (messagesEl) {
    messagesEl.querySelectorAll(".message.assistant .content").forEach((el) => {
      el.innerHTML = renderMarkdown(el.textContent || "");
    });
  }
  scrollToBottom();
});
