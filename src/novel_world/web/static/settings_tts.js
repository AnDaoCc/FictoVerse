document.addEventListener("DOMContentLoaded", () => {
  const backendSel = document.getElementById("tts_backend_select");
  const openaiFields = document.getElementById("tts_openai_fields");
  const customFields = document.getElementById("tts_custom_fields");
  const sel = document.getElementById("tts_voice_select");

  const selected = window.__SETTINGS_TTS__?.voice ?? "";
  const backend = window.__SETTINGS_TTS__?.backend ?? "edge";
  const locale = window.__SETTINGS_TTS__?.locale ?? "zh";
  const uninstallConfirm = window.__SETTINGS_TTS__?.modsUninstallConfirm ?? "确定卸载？";

  const syncBackendPanels = () => {
    const b = backendSel?.value || backend || "edge";
    const isOpenai = b === "openai" || b === "openai_compatible";
    if (openaiFields) openaiFields.hidden = !isOpenai;
    if (customFields) customFields.hidden = b !== "custom_http";
  };
  syncBackendPanels();

  backendSel?.addEventListener("change", syncBackendPanels);

  const fillBrowserVoices = () => {
    if (!sel || !window.speechSynthesis) return;
    while (sel.options.length > 1) sel.remove(1);
    window.speechSynthesis.getVoices().forEach((v) => {
      const opt = document.createElement("option");
      opt.value = v.name;
      opt.textContent = v.name;
      if (v.name === selected) opt.selected = true;
      sel.appendChild(opt);
    });
  };

  const fillApiVoices = async () => {
    if (!sel) return;
    const b = backendSel?.value || backend || "edge";
    if (b === "browser") {
      fillBrowserVoices();
      return;
    }
    const resp = await fetch(`/api/tts/voices?backend=${encodeURIComponent(b)}&locale=${encodeURIComponent(locale)}`);
    const data = await resp.json().catch(() => ({}));
    while (sel.options.length > 1) sel.remove(1);
    (data.voices || []).forEach((v) => {
      const opt = document.createElement("option");
      opt.value = v.id;
      opt.textContent = v.name || v.id;
      if (v.id === selected) opt.selected = true;
      sel.appendChild(opt);
    });
  };

  fillApiVoices();
  if (window.speechSynthesis) {
    window.speechSynthesis.onvoiceschanged = () => {
      if ((backendSel?.value || backend) === "browser") fillBrowserVoices();
    };
  }

  document.getElementById("tts_preview_btn")?.addEventListener("click", async () => {
    const voice = sel?.value || "";
    const resp = await fetch("/api/tts/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "你好，这是音色试听。", voice }),
    });
    if (!resp.ok) {
      alert("试听失败");
      return;
    }
    const blob = await resp.blob();
    const audio = new Audio(URL.createObjectURL(blob));
    audio.play();
  });

  document.querySelectorAll(".btn-uninstall-mod").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (!confirm(uninstallConfirm)) return;
      const id = btn.dataset.modId || "";
      const form = document.getElementById("mod_uninstall_form");
      const input = document.getElementById("mod_uninstall_id");
      if (form && input) {
        input.value = id;
        form.submit();
      }
    });
  });

  if (window.NovelWorldMods) {
    window.NovelWorldMods.runHooks("settings.panel", null, {
      container: document.getElementById("mods_settings_hook_panel"),
    });
  }
});
