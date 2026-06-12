(function () {
  const I18N = window.__I18N__ || {};
  const t = (key, fallback = "") => I18N[key] || fallback || key;

  const VIEWPORT = 300;
  const OUTPUT = 512;

  const modal = document.getElementById("avatar_crop_modal");
  if (!modal) return;

  const img = document.getElementById("avatar_crop_img");
  const viewport = document.getElementById("avatar_crop_viewport");
  const zoomInput = document.getElementById("avatar_crop_zoom");
  const confirmBtn = document.getElementById("avatar_crop_confirm");
  const statusEl = document.getElementById("avatar_crop_status");

  let uploadUrl = "";
  let redirectUrl = "";
  let scale = 1;
  let offsetX = 0;
  let offsetY = 0;
  let dragging = false;
  let dragStartX = 0;
  let dragStartY = 0;
  let dragBaseX = 0;
  let dragBaseY = 0;

  const applyTransform = () => {
    if (!img) return;
    img.style.transform = `translate(calc(-50% + ${offsetX}px), calc(-50% + ${offsetY}px)) scale(${scale})`;
  };

  const fitImage = () => {
    if (!img.naturalWidth || !img.naturalHeight) return;
    const cover = Math.max(VIEWPORT / img.naturalWidth, VIEWPORT / img.naturalHeight);
    scale = cover;
    offsetX = 0;
    offsetY = 0;
    if (zoomInput) zoomInput.value = String(Math.round(scale * 100));
    applyTransform();
  };

  const closeModal = () => {
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
    if (statusEl) {
      statusEl.hidden = true;
      statusEl.textContent = "";
    }
    if (img) img.removeAttribute("src");
  };

  const openModal = (file, url, redirect) => {
    uploadUrl = url || "";
    redirectUrl = redirect || "";
    if (!file || !uploadUrl) return;

    const reader = new FileReader();
    reader.onload = () => {
      img.onload = () => {
        fitImage();
        modal.classList.remove("hidden");
        modal.setAttribute("aria-hidden", "false");
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  };

  const exportCanvas = () => {
    const nw = img.naturalWidth;
    const nh = img.naturalHeight;
    const dw = nw * scale;
    const dh = nh * scale;
    const left = VIEWPORT / 2 + offsetX - dw / 2;
    const top = VIEWPORT / 2 + offsetY - dh / 2;

    const sx = Math.max(0, (0 - left) / scale);
    const sy = Math.max(0, (0 - top) / scale);
    const sSize = VIEWPORT / scale;
    const sw = Math.min(nw - sx, sSize);
    const sh = Math.min(nh - sy, sSize);

    const canvas = document.createElement("canvas");
    canvas.width = OUTPUT;
    canvas.height = OUTPUT;
    const ctx = canvas.getContext("2d");
    if (!ctx || sw <= 0 || sh <= 0) return null;
    ctx.drawImage(img, sx, sy, sw, sh, 0, 0, OUTPUT, OUTPUT);
    return canvas;
  };

  const uploadBlob = async (blob) => {
    const form = new FormData();
    form.append("file", blob, "avatar.png");
    if (redirectUrl) form.append("next", redirectUrl);

    const resp = await fetch(uploadUrl, { method: "POST", body: form });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || !data.ok) {
      throw new Error(data.message || t("common.error", "错误"));
    }
    return data.redirect_url || redirectUrl || window.location.pathname;
  };

  modal.querySelectorAll("[data-avatar-crop-close]").forEach((el) => {
    el.addEventListener("click", closeModal);
  });

  zoomInput?.addEventListener("input", () => {
    const min = Math.max(VIEWPORT / img.naturalWidth, VIEWPORT / img.naturalHeight);
    scale = Math.max(min, Number(zoomInput.value) / 100);
    applyTransform();
  });

  const onPointerDown = (e) => {
    if (!img.src) return;
    dragging = true;
    viewport.classList.add("is-dragging");
    dragStartX = e.clientX;
    dragStartY = e.clientY;
    dragBaseX = offsetX;
    dragBaseY = offsetY;
  };

  const onPointerMove = (e) => {
    if (!dragging) return;
    offsetX = dragBaseX + (e.clientX - dragStartX);
    offsetY = dragBaseY + (e.clientY - dragStartY);
    applyTransform();
  };

  const onPointerUp = () => {
    dragging = false;
    viewport.classList.remove("is-dragging");
  };

  viewport.addEventListener("mousedown", onPointerDown);
  window.addEventListener("mousemove", onPointerMove);
  window.addEventListener("mouseup", onPointerUp);

  confirmBtn?.addEventListener("click", async () => {
    const canvas = exportCanvas();
    if (!canvas) {
      alert(t("avatar_crop.failed", "裁剪失败"));
      return;
    }
    confirmBtn.disabled = true;
    if (statusEl) {
      statusEl.hidden = false;
      statusEl.textContent = t("avatar_crop.uploading", "正在上传…");
    }
    try {
      const blob = await new Promise((resolve, reject) => {
        canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("blob"))), "image/png", 0.92);
      });
      const url = await uploadBlob(blob);
      window.location.href = url;
    } catch (err) {
      if (statusEl) statusEl.textContent = err.message || String(err);
      confirmBtn.disabled = false;
    }
  });

  document.querySelectorAll("input[data-avatar-crop]").forEach((input) => {
    input.addEventListener("change", () => {
      const file = input.files && input.files[0];
      if (!file) return;
      openModal(file, input.dataset.uploadUrl, input.dataset.redirectUrl);
      input.value = "";
    });
  });
})();
