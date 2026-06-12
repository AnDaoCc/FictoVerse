(function () {
  const $ = (id) => document.getElementById(id);

  const bgEl = $("launcher_bg");
  const scrimEl = $("launcher_scrim");
  const btnUpload = $("btn_upload_launcher_bg");
  const btnClear = $("btn_clear_launcher_bg");
  const fileInput = $("launcher_bg_input");
  const rngOverlay = $("rng_launcher_overlay");
  const rngBlur = $("rng_launcher_blur");
  const lblOverlay = $("lbl_launcher_overlay");
  const lblBlur = $("lbl_launcher_blur");

  let saveTimer = null;
  let current = { overlay: 0.55, blur: 8, fit: "cover", has_background: false };

  function api() {
    return window.pywebview && window.pywebview.api;
  }

  async function call(method, ...args) {
    const a = api();
    if (!a || typeof a[method] !== "function") return null;
    return a[method](...args);
  }

  function applyAppearance(data) {
    if (!data) return;
    current = {
      overlay: Number(data.overlay ?? 0.55),
      blur: Number(data.blur ?? 8),
      fit: data.fit || "cover",
      has_background: !!data.has_background,
    };

    if (bgEl) {
      if (data.background_data_url) {
        bgEl.style.backgroundImage = `url("${data.background_data_url}")`;
        bgEl.classList.add("has-image");
      } else {
        bgEl.style.backgroundImage = "";
        bgEl.classList.remove("has-image");
      }
      bgEl.style.backgroundSize = current.fit;
    }

    if (scrimEl) {
      scrimEl.style.setProperty("--scrim-opacity", String(current.overlay));
      scrimEl.style.setProperty("--scrim-blur", `${current.blur}px`);
    }

    if (rngOverlay) {
      rngOverlay.value = String(Math.round(current.overlay * 100));
      if (lblOverlay) lblOverlay.textContent = `${Math.round(current.overlay * 100)}%`;
    }
    if (rngBlur) {
      rngBlur.value = String(current.blur);
      if (lblBlur) lblBlur.textContent = `${current.blur}px`;
    }
  }

  function scheduleSave() {
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(async () => {
      saveTimer = null;
      const overlay = Number(rngOverlay?.value || 55) / 100;
      const blur = Number(rngBlur?.value || 8);
      await call("save_launcher_appearance", overlay, blur, current.fit);
    }, 350);
  }

  async function loadAppearance() {
    const res = await call("get_launcher_appearance");
    if (res && res.ok !== false) applyAppearance(res);
  }

  function readFileAsB64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
  }

  if (btnUpload && fileInput) {
    btnUpload.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", async () => {
      const file = fileInput.files && fileInput.files[0];
      fileInput.value = "";
      if (!file) return;
      try {
        const b64 = await readFileAsB64(file);
        const res = await call("upload_launcher_background", file.name, b64);
        if (res && res.ok !== false) await loadAppearance();
      } catch (_) {
        /* ignore */
      }
    });
  }

  if (btnClear) {
    btnClear.addEventListener("click", async () => {
      const res = await call("clear_launcher_background");
      if (res && res.ok !== false) await loadAppearance();
    });
  }

  if (rngOverlay) {
    rngOverlay.addEventListener("input", () => {
      const pct = Number(rngOverlay.value);
      current.overlay = pct / 100;
      if (scrimEl) scrimEl.style.setProperty("--scrim-opacity", String(current.overlay));
      if (lblOverlay) lblOverlay.textContent = `${pct}%`;
      scheduleSave();
    });
  }

  if (rngBlur) {
    rngBlur.addEventListener("input", () => {
      current.blur = Number(rngBlur.value);
      if (scrimEl) scrimEl.style.setProperty("--scrim-blur", `${current.blur}px`);
      if (lblBlur) lblBlur.textContent = `${current.blur}px`;
      scheduleSave();
    });
  }

  window.NWAppearance = { load: loadAppearance, apply: applyAppearance };

  function tryLoad() {
    if (api()) {
      loadAppearance();
      return;
    }
    setTimeout(tryLoad, 120);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", tryLoad);
  } else {
    tryLoad();
  }
})();
