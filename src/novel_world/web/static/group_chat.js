document.addEventListener("DOMContentLoaded", () => {
  const I18N = window.__I18N__ || {};
  const t = (key, fallback = "") => I18N[key] || fallback || key;

  const membersInput = document.getElementById("members_input");
  const membersHint = document.getElementById("members_hint");
  const createForm = document.getElementById("group-create-form");

  const collectMembers = () => {
    if (!createForm) return [];
    return Array.from(createForm.querySelectorAll(".member-checkbox"))
      .filter((cb) => cb.checked)
      .map((cb) => ({
        world_id: (cb.dataset.worldId || "").trim(),
        character_id: (cb.dataset.charId || "").trim(),
      }))
      .filter((m) => m.world_id && m.character_id);
  };

  const refreshMembers = () => {
    if (!membersInput) return;
    const selected = collectMembers();
    membersInput.value = JSON.stringify(selected);
    if (membersHint) {
      membersHint.textContent =
        selected.length >= 2
          ? `${selected.length} ${t("group_chat.pick_members", "成员")}`
          : t("group_chat.no_members_hint", "请至少勾选两个角色。");
      membersHint.classList.toggle("warn", selected.length < 2);
    }
  };

  if (createForm) {
    createForm.addEventListener("change", (e) => {
      if (e.target.classList.contains("member-checkbox")) refreshMembers();
    });
    refreshMembers();

    createForm.addEventListener("submit", (e) => {
      const selected = collectMembers();
      membersInput.value = JSON.stringify(selected);
      if (selected.length < 2) {
        e.preventDefault();
        const incomplete = Array.from(createForm.querySelectorAll(".member-checkbox:checked")).some(
          (cb) => !(cb.dataset.worldId || "").trim() || !(cb.dataset.charId || "").trim()
        );
        if (incomplete) {
          alert(
            t(
              "group_chat.members_invalid",
              "部分勾选的角色数据无效，请刷新页面后重新勾选。"
            )
          );
        } else {
          alert(t("group_chat.no_members_hint", "请至少勾选两个角色。"));
        }
      }
    });
  }

  const membersPanel = document.getElementById("group-members-panel");
  if (membersPanel) {
    const sessionId = membersPanel.dataset.sessionId;

    document.getElementById("add_members_btn")?.addEventListener("click", async () => {
      const selected = Array.from(document.querySelectorAll(".add-member-checkbox:checked")).map(
        (cb) => ({
          world_id: (cb.dataset.worldId || "").trim(),
          character_id: (cb.dataset.charId || "").trim(),
        })
      ).filter((m) => m.world_id && m.character_id);
      if (!selected.length) return;
      const resp = await fetch(`/api/group-chat/sessions/${sessionId}/members/add`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ members: selected }),
      });
      if (resp.ok) window.location.reload();
      else {
        const data = await resp.json().catch(() => ({}));
        alert(data.message || t("common.error", "错误"));
      }
    });

    membersPanel.addEventListener("click", async (e) => {
      const removeBtn = e.target.closest(".member-remove-btn");
      if (removeBtn) {
        const chip = removeBtn.closest(".member-chip");
        if (!chip || !confirm(t("group_chat.remove_confirm", "确定移出该成员吗？"))) return;
        const resp = await fetch(`/api/group-chat/sessions/${sessionId}/members/remove`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            world_id: chip.dataset.worldId,
            character_id: chip.dataset.charId,
          }),
        });
        if (resp.ok) window.location.reload();
        else {
          const data = await resp.json().catch(() => ({}));
          alert(data.message || t("common.error", "错误"));
        }
        return;
      }

      const muteBtn = e.target.closest(".member-mute-btn");
      if (muteBtn) {
        const chip = muteBtn.closest(".member-chip");
        if (!chip) return;
        const muted = !chip.classList.contains("is-muted");
        const resp = await fetch(`/api/group-chat/sessions/${sessionId}/members/mute`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ character_id: chip.dataset.charId, muted }),
        });
        if (resp.ok) window.location.reload();
      }
    });
  }

  const composer = document.getElementById("group-composer");
  if (!composer) return;

  const sessionId = composer.dataset.sessionId;
  const personaName = composer.dataset.personaName || t("chat.role_user", "你");
  const messagesEl = document.getElementById("messages");
  const inputEl = document.getElementById("group_input");
  const sendBtn = document.getElementById("group_send_btn");
  const replyBtn = document.getElementById("group_reply_btn");
  const autoBtn = document.getElementById("group_auto_btn");
  const stopBtn = document.getElementById("group_stop_btn");
  const maxRoundEl = document.getElementById("group_max_round");
  const maxPerCharacterEl = document.getElementById("group_max_per_character");
  const forceSpeakerEl = document.getElementById("group_force_speaker");
  const statusEl = document.getElementById("group_status");
  const progressEl = document.getElementById("group_progress");
  const progressFillEl = document.getElementById("group_progress_fill");
  const progressLabelEl = document.getElementById("group_progress_label");

  const updateProgress = (current, total, show) => {
    if (!progressEl || !show || total <= 0) {
      if (progressEl) progressEl.hidden = true;
      return;
    }
    progressEl.hidden = false;
    const pct = Math.min(100, Math.round((current / total) * 100));
    if (progressFillEl) progressFillEl.style.width = `${pct}%`;
    if (progressLabelEl) {
      progressLabelEl.textContent = t("group_chat.auto_progress", "已接话 {current}/{total}")
        .replace("{current}", String(current))
        .replace("{total}", String(total));
    }
  };

  const scrollToBottom = () => {
    if (messagesEl) messagesEl.scrollTop = messagesEl.scrollHeight;
  };

  const renderMarkdown = (text) => {
    if (!text) return "";
    try {
      if (typeof marked !== "undefined" && marked.parse) {
        return marked.parse(text, { breaks: true, gfm: true });
      }
    } catch (_e) {
      /* fall through */
    }
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

  const appendUser = (content) => {
    const wrap = document.createElement("div");
    wrap.className = "message user rp-message";
    const initial = personaName[0] || "你";
    wrap.innerHTML = `<div class="rp-row user-row"><div class="bubble"><div class="role-label">${escapeHtml(personaName)}</div><div class="content">${escapeHtml(content)}</div></div><div class="rp-avatar fallback user-fallback" title="${escapeHtml(personaName)}">${escapeHtml(initial)}</div></div>`;
    messagesEl.appendChild(wrap);
    window.__NWMedia?.injectSpeakButtons?.(wrap);
    scrollToBottom();
  };

  const appendAssistant = (speaker, content, messageId) => {
    const wrap = document.createElement("div");
    wrap.className = "message assistant rp-message";
    if (messageId) wrap.dataset.messageId = messageId;
    const worldName = (speaker && (speaker.world_name || speaker.world)) || "";
    const world = worldName ? `<span class="speaker-world">${escapeHtml(worldName)}</span>` : "";
    const sp = speaker || {};
    wrap.innerHTML = `<div class="rp-row assistant-row">${avatarHtml(sp)}<div class="bubble"><div class="role-label">${escapeHtml(sp.name || t("chat.role_assistant", "助手"))}${world}</div><div class="content">${renderMarkdown(content)}</div></div></div>`;
    if (window.__NWMedia?.applySpeakerAttrs) {
      window.__NWMedia.applySpeakerAttrs(wrap, sp);
    }
    messagesEl.appendChild(wrap);
    window.__NWMedia?.injectSpeakButtons?.(messagesEl);
    window.__NWMedia?.autoSpeakMessage?.(wrap);
    scrollToBottom();
    return wrap;
  };

  let busy = false;

  const setBusy = (on) => {
    busy = on;
    if (sendBtn) sendBtn.disabled = on;
    if (replyBtn) replyBtn.disabled = on;
    if (autoBtn) autoBtn.disabled = on;
    if (inputEl) inputEl.disabled = on;
    if (stopBtn) stopBtn.hidden = !on;
    if (!on && statusEl) statusEl.textContent = "";
  };

  const applyDisplay = (messageId, displayContent) => {
    if (!messageId || !messagesEl) return;
    const row = messagesEl.querySelector(`.message[data-message-id="${messageId}"] .content`);
    if (row) row.innerHTML = renderMarkdown(displayContent);
  };

  const runRound = async (mode) => {
    if (busy) return;
    const content = (inputEl?.value || "").trim();
    if (mode === "send" && !content) return;

    if (mode === "send") window.__NWMedia?.stopAll?.();
    setBusy(true);
    if (statusEl) statusEl.textContent = t("group_chat.round_running", "角色接话中…");

    const maxRound = parseInt(maxRoundEl?.value || "5", 10);
    const maxPerCharacter = parseInt(maxPerCharacterEl?.value || "0", 10);
    const forceSpeaker = forceSpeakerEl?.value || "";

    const body = new URLSearchParams();
    body.set("content", content);
    body.set("mode", mode);
    body.set("max_round", String(maxRound));
    body.set("max_per_character", String(maxPerCharacter));
    body.set("force_character_id", forceSpeaker);

    let roundCurrent = 0;
    updateProgress(0, maxRound, true);

    try {
      const resp = await fetch(`/api/group-chat/sessions/${sessionId}/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body,
      });

      if (!resp.ok || !resp.body) {
        const data = await resp.json().catch(() => ({}));
        alert(data.message || t("common.error", "错误"));
        return;
      }

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
        if (event === "user_message") {
          if (inputEl) inputEl.value = "";
          appendUser(payload.content || content);
        } else if (event === "character_message") {
          appendAssistant(payload.speaker, payload.content, payload.message_id);
          roundCurrent += 1;
          updateProgress(roundCurrent, maxRound, true);
        } else if (event === "display") {
          applyDisplay(payload.message_id, payload.content);
        } else if (event === "done") {
          updateProgress(0, 0, false);
        } else if (event === "error") {
          alert(payload.message || payload.text || t("common.error", "错误"));
        }
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

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        parseSSE(decoder.decode(value, { stream: true }));
      }
      if (buffer.trim()) parseSSE("");
    } catch (err) {
      alert(String(err));
    } finally {
      setBusy(false);
      if (progressEl) progressEl.hidden = true;
    }
  };

  sendBtn?.addEventListener("click", () => runRound("send"));
  replyBtn?.addEventListener("click", () => runRound("reply"));
  autoBtn?.addEventListener("click", () => runRound("auto"));

  stopBtn?.addEventListener("click", async () => {
    try {
      await fetch(`/api/group-chat/sessions/${sessionId}/stop`, { method: "POST" });
    } catch (_e) {
      /* ignore */
    }
    setBusy(false);
  });

  // ---------- @ mention picker ----------
  const mentionPicker = document.getElementById("group_mention_picker");
  const loadMentionMembers = () => {
    const scriptEl = document.getElementById("group_mention_data");
    if (scriptEl?.textContent?.trim()) {
      try {
        const parsed = JSON.parse(scriptEl.textContent);
        if (Array.isArray(parsed)) return parsed;
      } catch (e) {
        console.warn("[group_chat] group_mention_data parse failed", e);
      }
    }
    try {
      const raw = composer.dataset.mentionMembers || "[]";
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) return parsed;
    } catch (e) {
      console.warn("[group_chat] data-mention-members parse failed", e);
    }
    return [];
  };
  let mentionMembers = loadMentionMembers();

  let mentionActiveIndex = 0;
  let mentionQuery = null;

  const hideMentionPicker = () => {
    mentionQuery = null;
    mentionActiveIndex = 0;
    if (mentionPicker) {
      mentionPicker.hidden = true;
      mentionPicker.innerHTML = "";
      mentionPicker.classList.remove("is-floating");
      mentionPicker.style.left = "";
      mentionPicker.style.width = "";
      mentionPicker.style.bottom = "";
    }
  };

  const positionMentionPicker = () => {
    if (!mentionPicker || !inputEl) return;
    const rect = inputEl.getBoundingClientRect();
    mentionPicker.classList.add("is-floating");
    mentionPicker.style.left = `${rect.left}px`;
    mentionPicker.style.width = `${Math.max(rect.width, 200)}px`;
    mentionPicker.style.bottom = `${window.innerHeight - rect.top + 6}px`;
  };

  const getMentionContext = () => {
    if (!inputEl) return null;
    const value = inputEl.value;
    const pos = inputEl.selectionStart ?? value.length;
    const before = value.slice(0, pos);
    const at = before.lastIndexOf("@");
    if (at < 0) return null;
    const segment = before.slice(at + 1);
    if (/[\s\n]/.test(segment)) return null;
    return { at, pos, query: segment };
  };

  const filteredMentionMembers = (query) => {
    const q = (query || "").trim().toLowerCase();
    return mentionMembers.filter((m) => {
      const name = (m.character_name || "").trim();
      if (!name) return false;
      if (!q) return true;
      return name.toLowerCase().includes(q) || (m.character_id || "").toLowerCase().includes(q);
    });
  };

  const insertMention = (name) => {
    if (!inputEl || !mentionQuery) return;
    const value = inputEl.value;
    const before = value.slice(0, mentionQuery.at);
    const after = value.slice(mentionQuery.pos);
    const insert = `@${name} `;
    inputEl.value = before + insert + after;
    const caret = before.length + insert.length;
    inputEl.setSelectionRange(caret, caret);
    hideMentionPicker();
    inputEl.focus();
  };

  const renderMentionPicker = (items) => {
    if (!mentionPicker) return;
    mentionPicker.innerHTML = "";
    if (!items.length) {
      const empty = document.createElement("li");
      empty.className = "mention-picker-empty";
      empty.textContent = t("group_chat.mention_empty", "没有匹配的成员");
      mentionPicker.appendChild(empty);
      mentionPicker.hidden = false;
      positionMentionPicker();
      return;
    }
    items.forEach((m, idx) => {
      const li = document.createElement("li");
      li.className = "mention-picker-item";
      li.setAttribute("role", "option");
      if (idx === mentionActiveIndex) li.classList.add("is-active");
      const name = (m.character_name || "").trim();
      li.dataset.name = name;
      li.innerHTML = `${escapeHtml(name)}<span class="mention-world">${escapeHtml(m.world_name || "")}</span>`;
      li.addEventListener("mousedown", (e) => {
        e.preventDefault();
        insertMention(name);
      });
      mentionPicker.appendChild(li);
    });
    mentionPicker.hidden = false;
    positionMentionPicker();
  };

  const refreshMentionPicker = () => {
    const ctx = getMentionContext();
    if (!ctx || !mentionMembers.length) {
      hideMentionPicker();
      return;
    }
    mentionQuery = ctx;
    const items = filteredMentionMembers(ctx.query);
    if (mentionActiveIndex >= items.length) mentionActiveIndex = 0;
    renderMentionPicker(items);
  };

  inputEl?.addEventListener("input", refreshMentionPicker);
  inputEl?.addEventListener("click", refreshMentionPicker);
  inputEl?.addEventListener("compositionend", refreshMentionPicker);
  window.addEventListener(
    "scroll",
    () => {
      if (mentionPicker && !mentionPicker.hidden) positionMentionPicker();
    },
    true
  );
  window.addEventListener("resize", () => {
    if (mentionPicker && !mentionPicker.hidden) positionMentionPicker();
  });
  inputEl?.addEventListener("blur", () => {
    setTimeout(hideMentionPicker, 150);
  });

  inputEl?.addEventListener("keydown", (e) => {
    if (mentionPicker && !mentionPicker.hidden && mentionQuery) {
      const items = filteredMentionMembers(mentionQuery.query);
      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (items.length) {
          mentionActiveIndex = (mentionActiveIndex + 1) % items.length;
          renderMentionPicker(items);
        }
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        if (items.length) {
          mentionActiveIndex = (mentionActiveIndex - 1 + items.length) % items.length;
          renderMentionPicker(items);
        }
        return;
      }
      if (e.key === "Enter" && items.length) {
        e.preventDefault();
        const pick = items[mentionActiveIndex] || items[0];
        insertMention((pick.character_name || "").trim());
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        hideMentionPicker();
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendBtn?.click();
    }
  });

  if (messagesEl) {
    messagesEl.querySelectorAll(".message.assistant .content, .message.user .content").forEach((el) => {
      if (el.closest(".message.assistant")) {
        el.innerHTML = renderMarkdown(el.textContent || "");
      }
    });
    window.__NWMedia?.injectSpeakButtons?.(messagesEl);
  }
  scrollToBottom();
});
