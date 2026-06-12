(function () {
  const $ = (id) => document.getElementById(id);

  const ROLE_OPTIONS = [
    ["hero_male", "男主角"],
    ["hero_female", "女主角"],
    ["party_male", "主角团内的男"],
    ["party_female", "主角团中的女"],
    ["npc_important", "重要NPC"],
    ["npc_story", "剧情NPC"],
    ["npc_passerby", "路人NPC"],
  ];
  const ROLE_LABELS = Object.fromEntries(ROLE_OPTIONS);
  const LEGACY_ROLE_MAP = {
    主角: "hero_male",
    女主角: "hero_female",
    男主角: "hero_male",
    配角: "npc_important",
    player: "hero_male",
    npc: "npc_passerby",
  };

  function normalizeRole(raw) {
    const text = String(raw || "").trim();
    if (!text) return "npc_passerby";
    if (ROLE_LABELS[text]) return text;
    if (LEGACY_ROLE_MAP[text]) return LEGACY_ROLE_MAP[text];
    const lower = text.toLowerCase();
    if (LEGACY_ROLE_MAP[lower]) return LEGACY_ROLE_MAP[lower];
    return ROLE_LABELS[text] ? text : "npc_passerby";
  }

  function roleLabel(raw) {
    return ROLE_LABELS[normalizeRole(raw)] || String(raw || "路人NPC");
  }

  function refreshWorldSelects(root) {
    if (!window.NWUi) return;
    const scope = root || document.getElementById("view_worlds") || document;
    window.NWUi.refreshSelects(scope);
    const roleSel = $("cf_role");
    if (roleSel) window.NWUi.syncSelect(roleSel);
  }

  let selectedWorldId = null;
  let worldData = null;
  let selectedCharId = null;
  let loreEditId = null;

  function api() {
    return window.pywebview && window.pywebview.api;
  }

  function toast(msg) {
    const el = $("worlds_toast");
    if (!el) return;
    el.textContent = msg;
    el.classList.add("show");
    setTimeout(() => el.classList.remove("show"), 2800);
  }

  async function call(method, ...args) {
    const a = api();
    if (!a || !a[method]) throw new Error("API 不可用");
    const res = await a[method](...args);
    if (!res || !res.ok) {
      throw new Error((res && res.message) || "操作失败");
    }
    return res;
  }

  function readFileB64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
  }

  function downloadB64(filename, dataB64) {
    const a = document.createElement("a");
    a.href = "data:application/octet-stream;base64," + dataB64;
    a.download = filename;
    a.click();
  }

  function bindTabs() {
    document.querySelectorAll(".worlds-tabs [data-wtab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tab = btn.dataset.wtab;
        document.querySelectorAll(".worlds-tabs [data-wtab]").forEach((b) => {
          b.classList.toggle("active", b.dataset.wtab === tab);
        });
        document.querySelectorAll(".worlds-panel").forEach((p) => {
          p.classList.toggle("active", p.dataset.wpanel === tab);
        });
        const activePanel = document.querySelector(
          `.worlds-panel[data-wpanel="${tab}"]`
        );
        if (activePanel) activePanel.scrollTop = 0;
        if (tab === "characters") refreshWorldSelects();
      });
    });
  }

  async function loadWorldList(selectId) {
    const listEl = $("worlds_list");
    if (!listEl) return;
    listEl.innerHTML = "<li>加载中…</li>";
    try {
      const res = await call("list_worlds");
      const worlds = res.data || [];
      if (!worlds.length) {
        listEl.innerHTML = "<li class='muted'>暂无世界</li>";
        return;
      }
      listEl.innerHTML = "";
      worlds.forEach((w) => {
        const li = document.createElement("li");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className =
          "await-api" + (w.id === selectedWorldId ? " active" : "");
        btn.innerHTML =
          "<span>" +
          escapeHtml(w.name) +
          "</span><span class='world-meta'>" +
          escapeHtml(w.genre || w.description_preview || w.id) +
          "</span>";
        btn.addEventListener("click", () => selectWorld(w.id));
        li.appendChild(btn);
        listEl.appendChild(li);
      });
      const pick = selectId || selectedWorldId || (worlds[0] && worlds[0].id);
      if (pick) await selectWorld(pick);
    } catch (e) {
      listEl.innerHTML = "<li class='muted'>" + escapeHtml(String(e)) + "</li>";
    }
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function selectWorld(worldId) {
    selectedWorldId = worldId;
    selectedCharId = null;
    loreEditId = null;
    $("worlds_empty_hint").hidden = true;
    $("worlds_detail").hidden = false;
    try {
      const res = await call("get_world", worldId);
      worldData = res.data;
      renderWorldHeader();
      renderWorldTab();
      renderCharactersTab();
      renderStateTab();
      renderDocsTab();
      renderLoreTab();
      renderSavesTab();
      document.querySelectorAll("#worlds_list button").forEach((b) => {
        b.classList.toggle(
          "active",
          b.textContent.indexOf(worldData.name) >= 0
        );
      });
    } catch (e) {
      toast(String(e));
    }
  }

  function renderWorldHeader() {
    if (!worldData) return;
    $("worlds_title").textContent = worldData.name;
    $("worlds_id").textContent = worldData.id;
  }

  function renderWorldTab() {
    const d = worldData;
    if (!d) return;
    $("wf_name").value = d.name || "";
    $("wf_genre").value = d.genre || "";
    $("wf_description").value = d.description || "";
    $("wf_rules").value = d.rules_json || "{}";
    $("wf_settings").value = d.settings_json || "{}";
    $("wf_persona_name").value = (d.user_persona && d.user_persona.name) || "";
    $("wf_persona_desc").value =
      (d.user_persona && d.user_persona.description) || "";
    $("wf_bg_status").textContent = d.has_background
      ? "已设置背景图"
      : "未设置背景图";
  }

  function renderCharactersTab() {
    const list = $("char_list");
    const form = $("char_form");
    if (!list || !worldData) return;
    list.innerHTML = "";
    (worldData.characters || []).forEach((c) => {
      const li = document.createElement("li");
      li.className = c.id === selectedCharId ? "selected" : "";
      li.innerHTML =
        "<div class='char-head'><span class='char-name'>" +
        escapeHtml(c.name) +
        "</span><span class='muted'>" +
        escapeHtml(roleLabel(c.role)) +
        "</span></div>";
      li.addEventListener("click", () => {
        selectedCharId = c.id;
        renderCharForm(c);
        renderCharactersTab();
      });
      list.appendChild(li);
    });
    if (!selectedCharId && worldData.characters && worldData.characters[0]) {
      selectedCharId = worldData.characters[0].id;
      renderCharForm(worldData.characters[0]);
    } else if (selectedCharId) {
      const c = (worldData.characters || []).find((x) => x.id === selectedCharId);
      if (c) renderCharForm(c);
      else if (form) form.hidden = true;
    } else if (form) {
      form.hidden = true;
    }
  }

  function renderCharForm(c) {
    const form = $("char_form");
    if (!form || !c) return;
    form.hidden = false;
    const p = c.profile || {};
    $("cf_id").value = c.id;
    $("cf_name").value = c.name || "";
    $("cf_role").value = normalizeRole(c.role);
    refreshWorldSelects(form);
    $("cf_summary").value = p.summary || p.description || "";
    $("cf_personality").value = p.personality || "";
    $("cf_appearance").value = p.appearance || "";
    $("cf_background").value = p.background || "";
    $("cf_scenario").value = p.scenario || "";
    $("cf_first_mes").value = p.first_mes || "";
    $("cf_mes_example").value = p.mes_example || "";
    $("cf_post_history").value = p.post_history_instructions || "";
    $("cf_attributes").value = JSON.stringify(c.attributes || {}, null, 2);
    $("cf_relationships").value = JSON.stringify(c.relationships || [], null, 2);
  }

  function renderStateTab() {
    const tbody = $("state_tbody");
    if (!tbody || !worldData) return;
    tbody.innerHTML = "";
    (worldData.state_entries || []).forEach((e) => {
      const tr = document.createElement("tr");
      tr.innerHTML =
        "<td>" +
        escapeHtml(e.scope) +
        "</td><td>" +
        escapeHtml(e.scope_id) +
        "</td><td>" +
        escapeHtml(e.key) +
        "</td><td><pre>" +
        escapeHtml(JSON.stringify(e.value)) +
        "</pre></td>";
      tbody.appendChild(tr);
    });
  }

  function renderDocsTab() {
    const ul = $("docs_list");
    if (!ul || !worldData) return;
    ul.innerHTML = "";
    (worldData.documents || []).forEach((d) => {
      const li = document.createElement("li");
      li.innerHTML =
        escapeHtml(d.filename) +
        " <button type='button' class='danger await-api' data-doc='" +
        d.id +
        "'>删除</button>";
      li.querySelector("button").addEventListener("click", async () => {
        if (!confirm("删除文档？")) return;
        try {
          await call("delete_world_document", selectedWorldId, d.id);
          toast("已删除");
          await selectWorld(selectedWorldId);
        } catch (e) {
          toast(String(e));
        }
      });
      ul.appendChild(li);
    });
  }

  function renderLoreTab() {
    const ul = $("lore_list");
    if (!ul || !worldData) return;
    ul.innerHTML = "";
    (worldData.lore_entries || []).forEach((e) => {
      const li = document.createElement("li");
      li.innerHTML =
        "<strong>" +
        escapeHtml((e.keys || []).join(", ")) +
        "</strong> <span class='muted'>" +
        escapeHtml(e.scope) +
        "</span><br/><span>" +
        escapeHtml((e.content || "").slice(0, 80)) +
        "</span> " +
        (e.source === "character_book"
          ? "<em class='muted'>（角色书）</em>"
          : "<button type='button' class='await-api' data-lore='" +
            e.id +
            "'>编辑</button> <button type='button' class='danger await-api' data-lore-del='" +
            e.id +
            "'>删除</button>");
      const editBtn = li.querySelector("[data-lore]");
      if (editBtn) {
        editBtn.addEventListener("click", () => fillLoreForm(e));
      }
      const delBtn = li.querySelector("[data-lore-del]");
      if (delBtn) {
        delBtn.addEventListener("click", async () => {
          if (!confirm("删除 Lore？")) return;
          try {
            await call("delete_lore_entry", selectedWorldId, e.id);
            toast("已删除");
            await selectWorld(selectedWorldId);
          } catch (err) {
            toast(String(err));
          }
        });
      }
      ul.appendChild(li);
    });
  }

  function fillLoreForm(e) {
    loreEditId = e.id;
    $("lf_scope").value = e.scope || "world";
    $("lf_character_id").value = e.character_id || "";
    $("lf_keys").value = (e.keys || []).join(", ");
    $("lf_content").value = e.content || "";
    $("lf_priority").value = e.priority || 0;
    $("lf_enabled").checked = e.enabled !== false;
    $("lf_save").textContent = "保存 Lore";
  }

  function renderSavesTab() {
    const ul = $("saves_list");
    if (!ul || !worldData) return;
    ul.innerHTML = "";
    (worldData.saves || []).forEach((s) => {
      const li = document.createElement("li");
      li.innerHTML =
        "槽位 " +
        s.slot_index +
        " · " +
        escapeHtml(s.label || "(无标签)") +
        " <button type='button' class='await-api' data-save='" +
        s.id +
        "'>加载</button>";
      li.querySelector("button").addEventListener("click", async () => {
        try {
          await call("load_save", selectedWorldId, s.id);
          toast("存档已加载");
        } catch (e) {
          toast(String(e));
        }
      });
      ul.appendChild(li);
    });
  }

  function bindWorldActions() {
    $("btn_new_world").addEventListener("click", async () => {
      const name = prompt("新世界名称：");
      if (!name || !name.trim()) return;
      try {
        const res = await call("create_world", name.trim());
        toast(res.message || "已创建");
        await loadWorldList(res.data && res.data.id);
      } catch (e) {
        toast(String(e));
      }
    });

    $("btn_import_pack").addEventListener("click", () => {
      $("import_pack_input").click();
    });

    $("import_pack_input").addEventListener("change", async (ev) => {
      const file = ev.target.files && ev.target.files[0];
      ev.target.value = "";
      if (!file) return;
      try {
        const b64 = await readFileB64(file);
        const res = await call("import_world_pack", file.name, b64);
        toast(res.message || "已导入");
        await loadWorldList(res.data && res.data.world_id);
      } catch (e) {
        toast(String(e));
      }
    });

    $("btn_save_world").addEventListener("click", async () => {
      if (!selectedWorldId) return;
      try {
        await call(
          "update_world",
          selectedWorldId,
          $("wf_name").value,
          $("wf_description").value,
          $("wf_genre").value,
          $("wf_rules").value,
          $("wf_settings").value
        );
        toast("世界已保存");
        await selectWorld(selectedWorldId);
      } catch (e) {
        toast(String(e));
      }
    });

    $("btn_save_persona").addEventListener("click", async () => {
      if (!selectedWorldId) return;
      try {
        await call(
          "update_world_user_persona",
          selectedWorldId,
          $("wf_persona_name").value,
          $("wf_persona_desc").value
        );
        toast("人设已保存");
      } catch (e) {
        toast(String(e));
      }
    });

    $("btn_delete_world").addEventListener("click", async () => {
      if (!selectedWorldId || !worldData) return;
      if (!confirm('删除世界「' + worldData.name + "」？不可恢复。")) return;
      try {
        await call("delete_world", selectedWorldId);
        toast("已删除");
        selectedWorldId = null;
        worldData = null;
        $("worlds_detail").hidden = true;
        $("worlds_empty_hint").hidden = false;
        await loadWorldList();
      } catch (e) {
        toast(String(e));
      }
    });

    $("btn_export_pack").addEventListener("click", async () => {
      if (!selectedWorldId) return;
      try {
        const res = await call("export_world_pack", selectedWorldId, true);
        const saved = await call("save_file", res.data.filename, res.data.data_b64);
        toast(saved.path ? "已保存: " + saved.path : saved.message || "已取消");
      } catch (e) {
        toast(String(e));
      }
    });

    $("btn_upload_bg").addEventListener("click", () => $("bg_file_input").click());
    $("bg_file_input").addEventListener("change", async (ev) => {
      const file = ev.target.files && ev.target.files[0];
      ev.target.value = "";
      if (!file || !selectedWorldId) return;
      try {
        const b64 = await readFileB64(file);
        await call("upload_world_background", selectedWorldId, file.name, b64);
        toast("背景已更新");
        await selectWorld(selectedWorldId);
      } catch (e) {
        toast(String(e));
      }
    });

    $("btn_clear_bg").addEventListener("click", async () => {
      if (!selectedWorldId) return;
      try {
        await call("clear_world_background", selectedWorldId);
        toast("背景已清除");
        await selectWorld(selectedWorldId);
      } catch (e) {
        toast(String(e));
      }
    });

    $("btn_new_char").addEventListener("click", async () => {
      if (!selectedWorldId) return;
      const name = prompt("角色名称：");
      if (!name || !name.trim()) return;
      try {
        const res = await call("create_character", selectedWorldId, {
          name: name.trim(),
          role: "npc_passerby",
        });
        toast(res.message || "已创建");
        selectedCharId = res.data && res.data.id;
        await selectWorld(selectedWorldId);
      } catch (e) {
        toast(String(e));
      }
    });

    $("btn_save_char").addEventListener("click", async () => {
      if (!selectedWorldId || !selectedCharId) return;
      try {
        await call("update_character", selectedWorldId, selectedCharId, {
          name: $("cf_name").value,
          role: normalizeRole($("cf_role").value),
          summary: $("cf_summary").value,
          personality: $("cf_personality").value,
          appearance: $("cf_appearance").value,
          background: $("cf_background").value,
          scenario: $("cf_scenario").value,
          first_mes: $("cf_first_mes").value,
          mes_example: $("cf_mes_example").value,
          post_history_instructions: $("cf_post_history").value,
          attributes: $("cf_attributes").value,
          relationships_json: $("cf_relationships").value,
        });
        toast("角色已保存");
        await selectWorld(selectedWorldId);
      } catch (e) {
        toast(String(e));
      }
    });

    $("btn_delete_char").addEventListener("click", async () => {
      if (!selectedWorldId || !selectedCharId) return;
      if (!confirm("删除该角色？")) return;
      try {
        await call("delete_character", selectedWorldId, selectedCharId);
        toast("已删除");
        selectedCharId = null;
        await selectWorld(selectedWorldId);
      } catch (e) {
        toast(String(e));
      }
    });

    $("btn_avatar_pick").addEventListener("click", () => $("avatar_file_input").click());
    $("avatar_file_input").addEventListener("change", (ev) => {
      const file = ev.target.files && ev.target.files[0];
      ev.target.value = "";
      if (file) openAvatarCrop(file);
    });

    $("btn_import_card").addEventListener("click", () => $("card_import_input").click());
    $("card_import_input").addEventListener("change", async (ev) => {
      const file = ev.target.files && ev.target.files[0];
      ev.target.value = "";
      if (!file || !selectedWorldId || !selectedCharId) return;
      try {
        const b64 = await readFileB64(file);
        await call(
          "import_character_card",
          selectedWorldId,
          selectedCharId,
          file.name,
          b64
        );
        toast("角色卡已导入");
        await selectWorld(selectedWorldId);
      } catch (e) {
        toast(String(e));
      }
    });

    $("btn_export_card_json").addEventListener("click", async () => {
      if (!selectedWorldId || !selectedCharId) return;
      try {
        const res = await call(
          "export_character_card",
          selectedWorldId,
          selectedCharId,
          "json"
        );
        const saved = await call("save_file", res.data.filename, res.data.data_b64); toast(saved.path ? "已保存: " + saved.path : saved.message || "已取消");
      } catch (e) {
        toast(String(e));
      }
    });

    $("btn_export_card_png").addEventListener("click", async () => {
      if (!selectedWorldId || !selectedCharId) return;
      try {
        const res = await call(
          "export_character_card",
          selectedWorldId,
          selectedCharId,
          "png"
        );
        const saved = await call("save_file", res.data.filename, res.data.data_b64); toast(saved.path ? "已保存: " + saved.path : saved.message || "已取消");
      } catch (e) {
        toast(String(e));
      }
    });

    $("btn_set_state").addEventListener("click", async () => {
      if (!selectedWorldId) return;
      try {
        await call(
          "set_state",
          selectedWorldId,
          $("sf_key").value,
          $("sf_value").value,
          $("sf_scope").value,
          $("sf_scope_id").value
        );
        toast("状态已更新");
        await selectWorld(selectedWorldId);
      } catch (e) {
        toast(String(e));
      }
    });

    $("btn_upload_doc").addEventListener("click", () => $("doc_file_input").click());
    $("doc_file_input").addEventListener("change", async (ev) => {
      const file = ev.target.files && ev.target.files[0];
      ev.target.value = "";
      if (!file || !selectedWorldId) return;
      try {
        const b64 = await readFileB64(file);
        await call("upload_world_document", selectedWorldId, file.name, b64);
        toast("文档已上传");
        await selectWorld(selectedWorldId);
      } catch (e) {
        toast(String(e));
      }
    });

    $("lf_save").addEventListener("click", async () => {
      if (!selectedWorldId) return;
      const payload = {
        scope: $("lf_scope").value,
        character_id: $("lf_character_id").value,
        keys: $("lf_keys").value,
        content: $("lf_content").value,
        priority: parseInt($("lf_priority").value, 10) || 0,
        enabled: $("lf_enabled").checked,
      };
      try {
        if (loreEditId) {
          await call("update_lore_entry", selectedWorldId, loreEditId, payload);
          toast("Lore 已保存");
        } else {
          await call("create_lore_entry", selectedWorldId, payload);
          toast("Lore 已创建");
        }
        loreEditId = null;
        $("lf_keys").value = "";
        $("lf_content").value = "";
        await selectWorld(selectedWorldId);
      } catch (e) {
        toast(String(e));
      }
    });

    $("btn_import_st_wi")?.addEventListener("click", () => {
      $("st_wi_import_input")?.click();
    });

    $("st_wi_import_input")?.addEventListener("change", async (ev) => {
      const file = ev.target.files && ev.target.files[0];
      ev.target.value = "";
      if (!file || !selectedWorldId) return;
      try {
        const b64 = await readFileB64(file);
        const scope = $("lf_scope")?.value || "world";
        const characterId = $("lf_character_id")?.value?.trim() || "";
        const mode = $("st_wi_mode")?.value || "merge";
        const res = await call(
          "import_st_world_info",
          selectedWorldId,
          file.name,
          b64,
          scope,
          characterId,
          mode
        );
        toast(res.message || "已导入 World Info");
        await selectWorld(selectedWorldId);
      } catch (e) {
        toast(String(e));
      }
    });

    $("btn_export_st_wi")?.addEventListener("click", async () => {
      if (!selectedWorldId) return;
      try {
        const scope = $("lf_scope")?.value || "world";
        const characterId = $("lf_character_id")?.value?.trim() || "";
        const res = await call("export_st_world_info", selectedWorldId, scope, characterId);
        if (!res.ok || !res.data) {
          toast(res.message || "导出失败");
          return;
        }
        const saved = await call("save_file", res.data.filename || "world_info.json", res.data.data_b64);
        toast(saved.path ? "已保存: " + saved.path : saved.message || "已取消");
      } catch (e) {
        toast(String(e));
      }
    });

    $("btn_new_lore").addEventListener("click", () => {
      loreEditId = null;
      $("lf_keys").value = "";
      $("lf_content").value = "";
      $("lf_save").textContent = "创建 Lore";
    });

    $("btn_create_save").addEventListener("click", async () => {
      if (!selectedWorldId) return;
      const slot = parseInt($("save_slot").value, 10);
      const label = $("save_label").value;
      try {
        await call("create_save", selectedWorldId, slot, label);
        toast("存档已创建");
        await selectWorld(selectedWorldId);
      } catch (e) {
        toast(String(e));
      }
    });
  }

  /* 头像裁剪（QQ/微信式） */
  const VIEWPORT = 300;
  const OUTPUT = 512;
  let cropScale = 1;
  let cropOx = 0;
  let cropOy = 0;
  let cropDragging = false;
  let cropFile = null;

  function openAvatarCrop(file) {
    cropFile = file;
    const modal = $("avatar_crop_modal");
    const img = $("avatar_crop_img");
    const reader = new FileReader();
    reader.onload = () => {
      img.onload = () => {
        const cover = Math.max(
          VIEWPORT / img.naturalWidth,
          VIEWPORT / img.naturalHeight
        );
        cropScale = cover;
        cropOx = 0;
        cropOy = 0;
        applyCropTransform();
        modal.classList.remove("hidden");
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  }

  function applyCropTransform() {
    const img = $("avatar_crop_img");
    if (!img) return;
    img.style.transform =
      "translate(calc(-50% + " +
      cropOx +
      "px), calc(-50% + " +
      cropOy +
      "px)) scale(" +
      cropScale +
      ")";
    const zoom = $("avatar_crop_zoom");
    if (zoom) zoom.value = String(Math.round(cropScale * 100));
  }

  function bindAvatarCrop() {
    const viewport = $("avatar_crop_viewport");
    const img = $("avatar_crop_img");
    const zoom = $("avatar_crop_zoom");
    const modal = $("avatar_crop_modal");

    if (zoom) {
      zoom.addEventListener("input", () => {
        cropScale = parseInt(zoom.value, 10) / 100;
        applyCropTransform();
      });
    }

    let sx, sy, bx, by;
    const onDown = (e) => {
      cropDragging = true;
      const p = e.touches ? e.touches[0] : e;
      sx = p.clientX;
      sy = p.clientY;
      bx = cropOx;
      by = cropOy;
      viewport.classList.add("is-dragging");
    };
    const onMove = (e) => {
      if (!cropDragging) return;
      const p = e.touches ? e.touches[0] : e;
      cropOx = bx + (p.clientX - sx);
      cropOy = by + (p.clientY - sy);
      applyCropTransform();
    };
    const onUp = () => {
      cropDragging = false;
      viewport.classList.remove("is-dragging");
    };
    viewport.addEventListener("mousedown", onDown);
    viewport.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    viewport.addEventListener("touchstart", onDown, { passive: true });
    viewport.addEventListener("touchmove", onMove, { passive: true });
    viewport.addEventListener("touchend", onUp);

    $("avatar_crop_cancel").addEventListener("click", () => {
      modal.classList.add("hidden");
      img.removeAttribute("src");
    });

    $("avatar_crop_confirm").addEventListener("click", async () => {
      if (!cropFile || !selectedWorldId || !selectedCharId) return;
      const nw = img.naturalWidth;
      const nh = img.naturalHeight;
      const dw = nw * cropScale;
      const dh = nh * cropScale;
      const left = VIEWPORT / 2 + cropOx - dw / 2;
      const top = VIEWPORT / 2 + cropOy - dh / 2;
      const sx0 = Math.max(0, (0 - left) / cropScale);
      const sy0 = Math.max(0, (0 - top) / cropScale);
      const sSize = VIEWPORT / cropScale;
      const canvas = document.createElement("canvas");
      canvas.width = OUTPUT;
      canvas.height = OUTPUT;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(img, sx0, sy0, sSize, sSize, 0, 0, OUTPUT, OUTPUT);
      const dataUrl = canvas.toDataURL("image/png");
      try {
        await call(
          "upload_character_avatar",
          selectedWorldId,
          selectedCharId,
          "avatar.png",
          dataUrl
        );
        toast("头像已更新");
        modal.classList.add("hidden");
      } catch (e) {
        toast(String(e));
      }
    });
  }

  let inited = false;

  function init() {
    if (inited) return;
    inited = true;
    bindTabs();
    bindWorldActions();
    bindAvatarCrop();
  }

  function onShow() {
    init();
    loadWorldList();
    refreshWorldSelects();
  }

  window.NWWorlds = { init, onShow };
})();
