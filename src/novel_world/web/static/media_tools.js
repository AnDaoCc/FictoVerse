document.addEventListener("DOMContentLoaded", () => {
  const I18N = window.__I18N__ || {};
  const t = (key, fallback = "") => I18N[key] || fallback || key;
  const prefs = window.__USER_PREFS__ || {};
  const media = () => window.__NWMedia || {};

  const injectSpeakButtons = (root) => {
    if (!prefs.tts_enabled || !root) return;
    root.querySelectorAll(".message.assistant .bubble, .rp-message.assistant .bubble").forEach((bubble) => {
      if (bubble.querySelector("[data-speak-content]")) return;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "ghost speak-btn";
      btn.dataset.speakContent = "1";
      btn.title = t("appearance.speak", "朗读");
      btn.textContent = "🔊";
      bubble.appendChild(btn);
    });
  };
  if (media().injectSpeakButtons === undefined) {
    media().injectSpeakButtons = injectSpeakButtons;
  }

  if (prefs.tts_enabled) {
    document.body.classList.add("tts-enabled");
  }

  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-speak-content]");
    if (!btn) return;
    const wrap = btn.closest(".message, .rp-message");
    if (wrap && media().speakMessage) media().speakMessage(wrap);
  });

  const immersiveBtn = document.getElementById("immersive_toggle");
  const layout = document.querySelector(".roleplay-layout");
  if (immersiveBtn && layout) {
    const key = "nw-immersive";
    const apply = (on) => {
      layout.classList.toggle("immersive", on);
      immersiveBtn.textContent = on
        ? t("appearance.exit_immersive", "退出沉浸")
        : t("appearance.immersive", "沉浸模式");
    };
    try {
      apply(localStorage.getItem(key) === "1");
    } catch (_e) {
      apply(false);
    }
    immersiveBtn.addEventListener("click", () => {
      const next = !layout.classList.contains("immersive");
      apply(next);
      try {
        localStorage.setItem(key, next ? "1" : "0");
      } catch (_e) {
        /* ignore */
      }
    });
  }

  const clearBgBtn = document.getElementById("clear_bg_btn");
  const appearancePanel = document.getElementById("appearance-panel");
  const sessionId = appearancePanel?.dataset.sessionId;
  if (clearBgBtn && sessionId) {
    clearBgBtn.addEventListener("click", async () => {
      const body = new URLSearchParams();
      body.set("clear", "1");
      await fetch(`/api/sessions/${sessionId}/background`, { method: "POST", body });
      window.location.reload();
    });
  }

  const applyDisplayScripts = (root) => {
    const scripts = window.__DISPLAY_SCRIPTS__ || [];
    if (!scripts.length) return;
    root.querySelectorAll(".content").forEach((el) => {
      if (el.dataset.displayProcessed === "1") return;
      let text = el.textContent || "";
      for (const rule of scripts) {
        try {
          const re = new RegExp(rule.pattern, rule.flags || "g");
          text = text.replace(re, rule.replace || "");
        } catch (_e) {
          /* skip bad regex */
        }
      }
      if (text !== el.textContent) {
        el.textContent = text;
      }
      el.dataset.displayProcessed = "1";
    });
  };

  applyDisplayScripts(document);
  injectSpeakButtons(document);
  const messagesEl = document.getElementById("messages");
  if (messagesEl) {
    new MutationObserver(() => {
      applyDisplayScripts(messagesEl);
      injectSpeakButtons(messagesEl);
    }).observe(messagesEl, {
      childList: true,
      subtree: true,
    });
  }
});
