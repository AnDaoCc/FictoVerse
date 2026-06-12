document.addEventListener("DOMContentLoaded", () => {
  const I18N = window.__I18N__ || {};
  const t = (key, fallback = "") => I18N[key] || fallback || key;
  const showThinking = !!(window.__USER_PREFS__ && window.__USER_PREFS__.show_thinking);

  const composer = document.getElementById("chat-composer");
  if (!composer) return;

  const sessionId = composer.dataset.sessionId;
  const worldId = composer.dataset.worldId || "";
  const messagesEl = document.getElementById("messages");
  const personaName = messagesEl?.dataset.personaName || t("chat.role_user", "你");
  const isWorldChat = messagesEl?.dataset.worldChat === "1";
  const worldName = messagesEl?.dataset.worldName || "";
  let worldCharacters = [];
  if (isWorldChat && messagesEl?.dataset.characters) {
    try {
      worldCharacters = JSON.parse(messagesEl.dataset.characters);
    } catch (_e) {
      worldCharacters = [];
    }
  }
  window.__WORLD_CHARACTERS__ = worldCharacters;
  window.__WORLD_CHARACTERS__ = worldCharacters;
  const media = () => window.__NWMedia || {};

  const inferSpeakerFromContent = (content) => {
    const text = String(content || "").trim();
    if (!text || !worldCharacters.length) return null;
    const sorted = [...worldCharacters].sort(
      (a, b) => (b.name || "").length - (a.name || "").length
    );
    for (const c of sorted) {
      if (c.name && c.name.length >= 2 && text.includes(c.name)) {
        return {
          character_id: c.id,
          name: c.name,
          avatar_url: c.avatar_url || "",
          tts_voice: c.tts_voice || "",
          world_id: worldId,
        };
      }
    }
    const roleOrder = [
      "hero_male",
      "hero_female",
      "party_male",
      "party_female",
      "npc_important",
      "npc_story",
      "npc_passerby",
    ];
    for (const role of roleOrder) {
      const hit = worldCharacters.find((c) => c.role === role);
      if (hit) {
        return {
          character_id: hit.id,
          name: hit.name,
          avatar_url: hit.avatar_url || "",
          tts_voice: hit.tts_voice || "",
          world_id: worldId,
        };
      }
    }
    const first = worldCharacters[0];
    return first
      ? {
          character_id: first.id,
          name: first.name,
          avatar_url: first.avatar_url || "",
          tts_voice: first.tts_voice || "",
          world_id: worldId,
        }
      : null;
  };
  const inputEl = document.getElementById("chat_input");
  const sendBtn = document.getElementById("send_btn");
  const continueBtn = document.getElementById("continue_btn");
  const pendingEl = document.getElementById("pending_attachments");
  const messageFileInput = document.getElementById("message_file_input");
  const sessionFileInput = document.getElementById("session_file_input");

  let pendingMessageAttachments = [];

  // ---- helpers ----

  const scrollToBottom = () => {
    if (messagesEl) messagesEl.scrollTop = messagesEl.scrollHeight;
  };

  const renderMarkdown = (text) => {
    if (!text) return "";
    try {
      if (typeof marked !== "undefined" && marked.parse) {
        return marked.parse(text, { breaks: true, gfm: true });
      }
    } catch (_e) { /* fall through to plain-text escape */ }
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  };

  const escapeHtml = (text) => {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  };

  const avatarHtml = (speaker) => {
    const name = (speaker && speaker.name) || t("chat.role_assistant", "助手");
    const url = speaker && speaker.avatar_url;
    if (url) {
      return `<img class="rp-avatar" src="${escapeHtml(url)}" alt="" />`;
    }
    return `<div class="rp-avatar fallback">${escapeHtml(name[0] || "?")}</div>`;
  };

  const appendMessageBubble = (role, content, thinking = "", speaker = null) => {
    const wrap = document.createElement("div");
    wrap.className = `message ${role}${isWorldChat ? " rp-message" : ""}`;
    let thinkingHtml = "";
    if (thinking) {
      thinkingHtml = `<details class="thinking-block" open><summary>${t("chat.thinking", "思考过程")}</summary><div class="thinking-content">${escapeHtml(thinking)}</div></details>`;
    }
    const contentHtml = role === "user" ? escapeHtml(content) : renderMarkdown(content);
    if (isWorldChat) {
      if (role === "user") {
        const initial = personaName[0] || "你";
        wrap.innerHTML = `<div class="rp-row user-row"><div class="bubble"><div class="role-label">${escapeHtml(personaName)}</div>${thinkingHtml}<div class="content">${contentHtml}</div></div><div class="rp-avatar fallback user-fallback" title="${escapeHtml(personaName)}">${escapeHtml(initial)}</div></div>`;
      } else {
        const spName = (speaker && speaker.name) || t("chat.role_assistant", "助手");
        const worldTag = worldName
          ? `<span class="speaker-world">${escapeHtml(worldName)}</span>`
          : "";
        wrap.innerHTML = `<div class="rp-row assistant-row">${avatarHtml(speaker)}<div class="bubble"><div class="role-label">${escapeHtml(spName)}${worldTag}</div>${thinkingHtml}<div class="content">${contentHtml}</div></div></div>`;
        if (speaker) wrap._speaker = speaker;
      }
    } else {
      const roleLabel =
        role === "user" ? personaName : t("chat.role_assistant", "助手");
      wrap.innerHTML = `<div class="bubble"><div class="role-label">${roleLabel}</div>${thinkingHtml}<div class="content">${contentHtml}</div></div>`;
    }
    messagesEl.appendChild(wrap);
    if (window.NovelWorldMods) {
      window.NovelWorldMods.runHooks("chat.message.render", wrap, {
        element: wrap,
        message: { role, content, thinking, speaker },
        sessionId: sessionId,
      });
    }
    scrollToBottom();
    return wrap;
  };

  const applySpeakerToBubble = (wrap, speaker) => {
    if (!wrap || !speaker || !isWorldChat) return;
    const row = wrap.querySelector(".assistant-row");
    if (!row) return;
    const oldAvatar = row.querySelector(".rp-avatar");
    if (oldAvatar) oldAvatar.remove();
    row.insertAdjacentHTML("afterbegin", avatarHtml(speaker));
    const label = row.querySelector(".role-label");
    if (label) {
      const worldTag = worldName
        ? `<span class="speaker-world">${escapeHtml(worldName)}</span>`
        : "";
      label.innerHTML = `${escapeHtml(speaker.name || t("chat.role_assistant", "助手"))}${worldTag}`;
    }
    wrap._speaker = speaker;
    if (window.__NWMedia?.applySpeakerAttrs) {
      window.__NWMedia.applySpeakerAttrs(wrap, speaker);
    }
    if (worldId) wrap.dataset.worldId = worldId;
  };

  const finishAssistantMessage = (wrap) => {
    if (window.__NWMedia?.injectSpeakButtons) {
      window.__NWMedia.injectSpeakButtons(wrap);
    }
    if (window.__NWMedia?.autoSpeakMessage) {
      window.__NWMedia.autoSpeakMessage(wrap);
    }
  };

  // ---- file upload ----

  const uploadFile = async (file, scope) => {
    const body = new FormData();
    body.append("file", file);
    body.append("scope", scope);
    const resp = await fetch(`/api/chat/sessions/${sessionId}/attachments`, { method: "POST", body });
    const data = await resp.json();
    if (!resp.ok || !data.ok) throw new Error(data.message || "上传失败");
    return data;
  };

  const refreshPendingLabel = () => {
    if (!pendingEl) return;
    if (pendingMessageAttachments.length === 0) {
      pendingEl.textContent = "";
      return;
    }
    pendingEl.textContent = `${t("chat.message_attachments", "本条消息附件")}：${pendingMessageAttachments.map((a) => a.filename).join("、")}`;
  };

  if (messageFileInput) {
    messageFileInput.addEventListener("change", async () => {
      const file = messageFileInput.files?.[0];
      if (!file) return;
      try {
        const data = await uploadFile(file, "message");
        pendingMessageAttachments.push({ id: data.id, filename: data.filename });
        refreshPendingLabel();
      } catch (err) {
        alert(err.message || String(err));
      }
      messageFileInput.value = "";
    });
  }

  if (sessionFileInput) {
    sessionFileInput.addEventListener("change", async () => {
      const file = sessionFileInput.files?.[0];
      if (!file) return;
      try {
        await uploadFile(file, "session");
        window.location.reload();
      } catch (err) {
        alert(err.message || String(err));
      }
      sessionFileInput.value = "";
    });
  }

  // ---- streaming ----

  const setSending = (on) => {
    sendBtn.disabled = on;
    sendBtn.textContent = on ? t("chat.sending", "正在思考…") : t("chat.send", "发送");
    inputEl.disabled = on;
    if (continueBtn) continueBtn.disabled = on;
  };

  const streamChat = async (content, mode = "chat") => {
    window.__NWMedia?.stopAll?.();
    const userDisplay =
      mode === "continue"
        ? t("chat.continue_writing_placeholder", "（继续写作）") + (content ? `：${content}` : "")
        : content || t("chat.message_attachments", "（附件）");
    appendMessageBubble("user", userDisplay);
    const assistantWrap = appendMessageBubble(
      "assistant",
      isWorldChat ? t("chat.sending", "正在思考…") : t("chat.sending", "正在思考…")
    );
    const contentEl = assistantWrap.querySelector(".content");
    const bubble = assistantWrap.querySelector(".bubble");
    let pendingSpeaker = null;
    let thinkingEl = null;
    let thinkingText = "";
    let contentText = "";

    const body = new URLSearchParams();
    body.set("content", content);
    body.set("mode", mode);
    if (pendingMessageAttachments.length) {
      body.set("message_attachment_ids", pendingMessageAttachments.map((a) => a.id).join(","));
    }

    const resp = await fetch(`/api/chat/sessions/${sessionId}/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });

    if (!resp.ok || !resp.body) {
      contentEl.textContent = "发送失败";
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
        if (!showThinking) {
          scrollToBottom();
          return;
        }
        thinkingText += payload.text || "";
        if (!thinkingEl) {
          thinkingEl = document.createElement("details");
          thinkingEl.className = "thinking-block";
          thinkingEl.open = true;
          thinkingEl.innerHTML = `<summary>${t("chat.thinking", "思考过程")}</summary><div class="thinking-content"></div>`;
          bubble.insertBefore(thinkingEl, contentEl);
        }
        thinkingEl.querySelector(".thinking-content").textContent = thinkingText;
      } else if (event === "content" || payload.kind === "content") {
        contentText += payload.text || "";
        renderContent(contentEl, contentText);
      } else if (event === "display" || payload.kind === "display") {
        contentText = payload.text || contentText;
        renderContent(contentEl, contentText);
      } else if (event === "speaker" || payload.kind === "speaker") {
        try {
          pendingSpeaker = JSON.parse(payload.text || "{}");
        } catch (_e) {
          pendingSpeaker = null;
        }
        applySpeakerToBubble(assistantWrap, pendingSpeaker);
      } else if (event === "done" || payload.kind === "done") {
        renderContent(contentEl, contentText);
        if (!pendingSpeaker && isWorldChat) {
          pendingSpeaker = inferSpeakerFromContent(contentText);
        }
        if (pendingSpeaker) applySpeakerToBubble(assistantWrap, pendingSpeaker);
        clearTimeout(_renderTimer);
        contentEl.innerHTML = renderMarkdown(contentText);
        finishAssistantMessage(assistantWrap);
      } else if (event === "error" || payload.kind === "error") {
        contentEl.textContent = payload.text || "错误";
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
      // Flush remaining buffer
      if (buffer.trim()) {
        parseSSE("");
      }
    } catch (_err) {
      // connection dropped — keep what we have
    }

    pendingMessageAttachments = [];
    refreshPendingLabel();
  };

  // Lazy re-render: only render full markdown when streaming pauses or ends.
  // During fast streaming, use a simple textContent update to avoid jank.
  let _renderTimer = null;
  const renderContent = (el, text) => {
    // Debounce markdown rendering during streaming
    clearTimeout(_renderTimer);
    _renderTimer = setTimeout(() => {
      el.innerHTML = renderMarkdown(text);
    }, 120);
    // Immediate text fallback for the first 120ms
    el.textContent = text;
  };

  // ---- send / continue buttons ----

  sendBtn.addEventListener("click", async () => {
    let text = inputEl.value.trim();
    if (window.NovelWorldMods) {
      text = String(
        window.NovelWorldMods.runHooks("chat.input.before_send", text, {
          text,
          sessionId,
        }) || ""
      ).trim();
    }
    if (!text && pendingMessageAttachments.length === 0) return;
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

  if (messagesEl && window.NovelWorldMods) {
    messagesEl.querySelectorAll(".message").forEach((wrap) => {
      window.NovelWorldMods.runHooks("chat.message.render", wrap, {
        element: wrap,
        sessionId,
      });
    });
  }

  if (continueBtn) {
    continueBtn.addEventListener("click", async () => {
      const text = inputEl.value.trim();
      setSending(true);
      try {
        await streamChat(text, "continue");
        inputEl.value = "";
      } catch (err) {
        alert(err.message || String(err));
      } finally {
        setSending(false);
      }
    });
  }

  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendBtn.click();
    }
  });

  // Render existing messages as markdown on page load
  if (messagesEl) {
    messagesEl.querySelectorAll(".message.assistant .content").forEach((el) => {
      const raw = el.textContent || "";
      el.innerHTML = renderMarkdown(raw);
    });
  }

  scrollToBottom();
});