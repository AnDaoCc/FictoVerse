(function () {
  const $ = (id) => document.getElementById(id);

  let busy = false;
  let apiReady = false;
  let busyTimer = null;
  let taskPollTimer = null;
  const BUSY_TIMEOUT_MS = 120000;
  const TASK_POLL_MS = 500;

  const statusBadge = $("status_badge");
  const urlLine = $("url_line");
  const logBox = $("log_box");
  const btnLaunch = $("btn_launch");
  const chkOpenBrowser = $("chk_open_browser");
  const chkRecreateVenv = $("chk_recreate_venv");
  const btnInstallEnv = $("btn_install_env");
  const btnInstallPython = $("btn_install_python");
  const btnRefreshPrereq = $("btn_refresh_prereq");
  const setupReadyHint = $("setup_ready_hint");
  const setupProgressWrap = $("setup_progress_wrap");
  const setupProgressBar = $("setup_progress_bar");
  const setupProgressLabel = $("setup_progress_label");

  const infoLauncher = $("info_launcher");
  const infoApp = $("info_app");
  const infoPython = $("info_python");
  const infoVenv = $("info_venv");
  const infoDeps = $("info_deps");
  const infoService = $("info_service");
  const btnUpgradePython = $("btn_upgrade_python");
  const btnUpgradeDeps = $("btn_upgrade_deps");
  const selPython = $("sel_python");

  function api() {
    return window.pywebview && window.pywebview.api;
  }

  function setApiEnabled(on) {
    document.querySelectorAll(".await-api").forEach((el) => {
      if (el.tagName === "BUTTON" || el.tagName === "INPUT") {
        el.disabled = !on;
      }
      el.classList.toggle("api-disabled", !on);
    });
    if (btnLaunch) btnLaunch.disabled = !on || busy;
  }

  function setBusy(on) {
    if (busyTimer) {
      clearTimeout(busyTimer);
      busyTimer = null;
    }
    busy = on;
    if (btnLaunch) btnLaunch.disabled = on || !apiReady;
    if (btnInstallEnv) btnInstallEnv.disabled = on || !apiReady;
    if (btnInstallPython) btnInstallPython.disabled = on || !apiReady;
    if (btnRefreshPrereq) btnRefreshPrereq.disabled = on || !apiReady;
    if ($("btn_upgrade_all")) $("btn_upgrade_all").disabled = on || !apiReady;
    if (btnUpgradePython) btnUpgradePython.disabled = on || !apiReady;
    if (btnUpgradeDeps) btnUpgradeDeps.disabled = on || !apiReady;
    if (selPython) selPython.disabled = on || !apiReady;
    if (on && statusBadge) {
      statusBadge.className = "status-badge busy";
      statusBadge.textContent = "处理中…";
      busyTimer = setTimeout(() => {
        if (busy) {
          stopTaskPoll();
          busy = false;
          setApiEnabled(apiReady);
          hideSetupProgress();
          refreshStatus();
        }
      }, BUSY_TIMEOUT_MS);
    }
  }

  function truncateMsg(text, max) {
    const s = String(text || "");
    if (s.length <= max) return s;
    return s.slice(0, max - 1) + "…";
  }

  function showSetupProgress(label, percent, indeterminate) {
    if (!setupProgressWrap) return;
    setupProgressWrap.hidden = false;
    if (setupProgressLabel) setupProgressLabel.textContent = label || "处理中…";
    if (setupProgressBar) {
      setupProgressBar.classList.toggle("indeterminate", !!indeterminate);
      if (!indeterminate) {
        setupProgressBar.style.width = Math.min(100, Math.max(0, percent || 0)) + "%";
      } else {
        setupProgressBar.style.width = "";
      }
    }
  }

  function hideSetupProgress() {
    if (setupProgressWrap) setupProgressWrap.hidden = true;
    if (setupProgressBar) {
      setupProgressBar.classList.remove("indeterminate");
      setupProgressBar.style.width = "0%";
    }
  }

  function setLaunchIconSvg(iconEl, symbolId) {
    if (!iconEl) return;
    iconEl.innerHTML = `<svg><use href="#${symbolId}"/></svg>`;
  }

  function updateLaunchButton(running) {
    if (!btnLaunch) return;
    const icon = btnLaunch.querySelector(".launch-icon");
    const title = btnLaunch.querySelector(".launch-text strong");
    const sub = btnLaunch.querySelector(".launch-text small");
    if (running) {
      btnLaunch.dataset.mode = "reopen";
      setLaunchIconSvg(icon, "icon-globe");
      if (title) title.textContent = "重新打开浏览器";
      if (sub) sub.textContent = "服务运行中，点击重新打开";
      btnLaunch.classList.add("launch-reopen");
    } else {
      btnLaunch.dataset.mode = "launch";
      setLaunchIconSvg(icon, "icon-play");
      if (title) title.textContent = "一键启动";
      if (sub) sub.textContent = "自动安装依赖并启动服务";
      btnLaunch.classList.remove("launch-reopen");
    }
  }

  function applyActionResult(result, options) {
    if (!result) return;
    if (result.logs) appendLog(result.logs, true);
    if (result.status) {
      if (result.ok && result.status.running) {
        if (statusBadge) {
          statusBadge.className = "status-badge running";
          statusBadge.textContent = "运行中 :" + (result.status.port || "");
        }
        if (urlLine) urlLine.textContent = result.status.url || result.url || "";
        updateLaunchButton(true);
      } else if (!result.ok) {
        if (statusBadge) {
          statusBadge.className = "status-badge error";
          statusBadge.textContent = truncateMsg(result.message || "操作失败", 48);
        }
        if (urlLine) urlLine.textContent = "";
      }
    } else if (!result.ok && result.message) {
      if (statusBadge) {
        statusBadge.className = "status-badge error";
        statusBadge.textContent = truncateMsg(result.message, 48);
      }
    }
    if (result.prerequisites) applyPrerequisites(result.prerequisites);
    if (options && options.switchConsole && (!result.ok || result.kind === "launch")) {
      showView("console");
    }
  }

  function stopTaskPoll() {
    if (taskPollTimer) {
      clearInterval(taskPollTimer);
      taskPollTimer = null;
    }
  }

  async function pollTaskOnce() {
    const a = api();
    if (!a || !a.get_task_status) return null;
    try {
      return await a.get_task_status();
    } catch (_e) {
      return null;
    }
  }

  async function runTask(startFn, options) {
    const a = api();
    if (!a || busy || !apiReady) return;
    setBusy(true);
    if (options && options.showProgress) {
      showSetupProgress("准备中…", 0, options.indeterminate);
    }
    try {
      const started = await startFn(a);
      if (!started || !started.ok || !started.started) {
        const msg = (started && started.message) || "无法启动任务";
        appendLog([msg], true);
        if (statusBadge) {
          statusBadge.className = "status-badge error";
          statusBadge.textContent = truncateMsg(msg, 48);
        }
        setBusy(false);
        hideSetupProgress();
        return started;
      }

      return await new Promise((resolve) => {
        stopTaskPoll();
        taskPollTimer = setInterval(async () => {
          const task = await pollTaskOnce();
          if (!task) return;
          window.__applyTaskProgress(task);
          if (!task.running) {
            stopTaskPoll();
            setBusy(false);
            hideSetupProgress();
            applyActionResult(task, options);
            if (task.ok) {
              await refreshStatus();
            }
            await loadSystemInfo();
            await loadPrerequisites();
            resolve(task);
          }
        }, TASK_POLL_MS);
      });
    } catch (err) {
      appendLog([String(err)], true);
      if (statusBadge) {
        statusBadge.className = "status-badge error";
        statusBadge.textContent = truncateMsg(String(err), 48);
      }
      setBusy(false);
      hideSetupProgress();
      stopTaskPoll();
    }
  }

  function showView(name) {
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    const panel = $("view_" + name);
    if (panel) panel.classList.add("active");
    document.querySelectorAll(".nav-item[data-view]").forEach((n) => {
      n.classList.toggle("active", n.dataset.view === name);
    });
    if (name === "setup") loadPrerequisites();
    if (name === "worlds" && window.NWWorlds && window.NWWorlds.onShow) {
      window.NWWorlds.onShow();
    }
    if (name === "settings" && window.NWSettings && window.NWSettings.onShow) {
      window.NWSettings.onShow();
    }
  }

  function setDot(id, state) {
    const el = $(id);
    if (!el) return;
    el.className = "setup-dot " + (state || "");
  }

  function applyPrerequisites(pre) {
    if (!pre) return;
    if (pre.python_ok) {
      setDot("setup_python_dot", "ok");
      $("setup_python_detail").textContent =
        (pre.python_version || "已安装") + (pre.python_path ? " · " + pre.python_path : "");
      if (btnInstallPython) btnInstallPython.hidden = true;
    } else {
      setDot("setup_python_dot", "err");
      $("setup_python_detail").textContent = "未检测到 Python 3.10+";
      if (btnInstallPython) btnInstallPython.hidden = false;
    }
    if (pre.webview2_ok) {
      setDot("setup_webview2_dot", "ok");
      $("setup_webview2_detail").textContent = "已安装（启动器界面需要）";
    } else {
      setDot("setup_webview2_dot", "warn");
      $("setup_webview2_detail").textContent = "未检测到，可安装 Edge WebView2 运行时";
    }
    if (pre.root_ok) {
      setDot("setup_root_dot", "ok");
      $("setup_root_detail").textContent = "已找到 pyproject.toml";
    } else {
      setDot("setup_root_dot", "err");
      $("setup_root_detail").textContent = pre.root_error || "未找到项目根";
    }
    if (pre.venv_exists) {
      setDot("setup_venv_dot", "ok");
      $("setup_venv_detail").textContent = ".venv 已创建";
    } else {
      setDot("setup_venv_dot", "warn");
      $("setup_venv_detail").textContent = "尚未创建";
    }
    if (!pre.deps_need_install && pre.venv_exists) {
      setDot("setup_deps_dot", "ok");
      $("setup_deps_detail").textContent = "依赖已就绪";
    } else if (pre.venv_exists) {
      setDot("setup_deps_dot", "warn");
      $("setup_deps_detail").textContent = "需要安装或更新";
    } else {
      setDot("setup_deps_dot", "warn");
      $("setup_deps_detail").textContent = "待安装";
    }
    if (setupReadyHint) setupReadyHint.hidden = !pre.ready;
    if ($("btn_upgrade_all")) $("btn_upgrade_all").hidden = !pre.ready;
  }

  function applyUpgrades(updates) {
    if (!updates) return;
    if (btnUpgradePython) {
      const pyUp = updates.python && updates.python.upgrade_available;
      btnUpgradePython.hidden = !pyUp;
      if (pyUp) btnUpgradePython.title = updates.python.message || "升级 Python 到最新兼容版";
    }
    if (btnUpgradeDeps) {
      const depUp = updates.deps && updates.deps.upgrade_available;
      btnUpgradeDeps.hidden = !depUp;
      if (depUp) btnUpgradeDeps.title = updates.deps.message || "升级依赖到最新版";
    }
  }

  function applyAvailablePythons(pythons) {
    if (!selPython) return;
    if (!pythons || pythons.length <= 1) {
      selPython.hidden = true;
      if (infoPython) infoPython.hidden = false;
      return;
    }
    selPython.innerHTML = "";
    pythons.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.path;
      opt.textContent = "Python " + p.version;
      if (p.active === "true") opt.selected = true;
      selPython.appendChild(opt);
    });
    selPython.hidden = false;
    selPython.disabled = !apiReady || busy;
    if (infoPython) infoPython.hidden = true;
  }

  async function loadAvailablePythons() {
    const a = api();
    if (!a) return;
    try {
      const pythons = await a.get_available_pythons();
      applyAvailablePythons(pythons);
    } catch (_e) { /* ignore */ }
  }

  async function loadPrerequisites() {
    const a = api();
    if (!a || !a.get_prerequisites) return;
    try {
      const pre = await a.get_prerequisites();
      applyPrerequisites(pre);
      try {
        const updates = await a.check_updates();
        applyUpgrades(updates);
      } catch (_u) { /* ignore */ }
    } catch (_e) {
      /* ignore */
    }
  }

  function appendLog(lines, force) {
    if (!logBox || !lines || !lines.length) return;
    if (false && !force) return;
    const text = lines.join("\n");
    if (logBox.textContent) {
      logBox.textContent += "\n" + text;
    } else {
      logBox.textContent = text;
    }
    logBox.scrollTop = logBox.scrollHeight;
  }

  window.__applyLogs = function (lines) {
    if (!logBox) return;
    if (Array.isArray(lines) && lines.length) {
      logBox.textContent = lines.join("\n");
      logBox.scrollTop = logBox.scrollHeight;
    }
  };

  window.__applyStatus = function (status) {
    if (busy) return;
    if (!status || !status.running) {
      if (statusBadge) {
        statusBadge.className = "status-badge idle";
        statusBadge.textContent = status && status.message ? status.message : "未运行";
        if (status && status.message && status.message.indexOf("请将") >= 0) {
          statusBadge.className = "status-badge error";
        }
      }
      if (urlLine) urlLine.textContent = "";
      updateLaunchButton(false);
      return;
    }
    if (statusBadge) {
      statusBadge.className = "status-badge running";
      statusBadge.textContent = "运行中 :" + (status.port || "");
    }
    if (urlLine) urlLine.textContent = status.url || "";
    updateLaunchButton(true);
  };

  window.__applyTaskProgress = function (task) {
    if (!task) return;
    const label = task.label || "处理中…";
    if (task.kind === "launch" && statusBadge) {
      statusBadge.className = "status-badge busy";
      statusBadge.textContent = truncateMsg(label, 40);
    }
    if (task.kind === "install" || task.kind === "check") {
      showSetupProgress(label, task.percent, task.indeterminate);
    } else if (task.running) {
      showSetupProgress(label, task.percent, task.indeterminate);
    }
    if (task.logs && task.logs.length) {
      window.__applyLogs(task.logs);
    }
  };

  function applySystemInfo(info) {
    if (!info) return;
    if (infoLauncher) infoLauncher.textContent = info.launcher_version || "—";
    if (infoApp) infoApp.textContent = info.app_version || "—";
    if (infoPython) infoPython.textContent = info.python_version || "—";
    if (infoVenv) {
      if (!info.root_ok) {
        infoVenv.textContent = "未找到项目";
        infoVenv.className = "err";
      } else {
        infoVenv.textContent = info.venv_exists ? "已创建" : "未创建";
        infoVenv.className = info.venv_exists ? "ok" : "warn";
      }
    }
    if (infoDeps) {
      if (!info.root_ok) {
        infoDeps.textContent = "—";
        infoDeps.className = "";
      } else if (info.deps_need_install) {
        infoDeps.textContent = "待安装/更新";
        infoDeps.className = "warn";
      } else {
        infoDeps.textContent = "已就绪";
        infoDeps.className = "ok";
      }
    }
    if (infoService && info.status) {
      if (info.status.running) {
        infoService.textContent = "运行中";
        infoService.className = "ok";
      } else {
        infoService.textContent = info.status.message || "未运行";
        infoService.className = "";
      }
    }
    if (
      info.status &&
      !busy &&
      statusBadge &&
      !statusBadge.classList.contains("error")
    ) {
      window.__applyStatus(info.status);
    }
  }

  async function refreshStatus() {
    const a = api();
    if (!a) return;
    try {
      const status = await a.get_status();
      window.__applyStatus(status);
    } catch (_e) {
      /* ignore */
    }
  }

  async function loadSystemInfo() {
    const a = api();
    if (!a) return;
    try {
      const info = await a.get_system_info();
      applySystemInfo(info);
    } catch (_e) {
      /* ignore */
    }
  }

  async function runAction(fn, options) {
    const a = api();
    if (!a || busy || !apiReady) return;
    setBusy(true);
    try {
      const result = await fn(a);
      applyActionResult(result, options);
      await refreshStatus();
      await loadSystemInfo();
      await loadPrerequisites();
      return result;
    } catch (err) {
      appendLog([String(err)], true);
      if (statusBadge) {
        statusBadge.className = "status-badge error";
        statusBadge.textContent = truncateMsg(String(err), 48);
      }
    } finally {
      setBusy(false);
      await refreshStatus();
      await loadSystemInfo();
      await loadPrerequisites();
    }
  }

  function bindNav() {
    document.querySelectorAll(".nav-item[data-view]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (!apiReady) return;
        showView(btn.dataset.view);
      });
    });

    document.querySelectorAll(".nav-item[data-action]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (!apiReady) return;
        const action = btn.dataset.action;
        if (action === "stop_server") {
          runAction((a) => a.stop_server(), { switchConsole: true });
        }
      });
    });

    document.querySelectorAll(".quick-tile[data-dir]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (!apiReady) return;
        runAction((a) => a.open_directory(btn.dataset.dir));
      });
    });
  }

  function bindControls() {
    if (btnLaunch) {
      btnLaunch.addEventListener("click", () => {
        if (!apiReady || busy) return;
        const mode = btnLaunch.dataset.mode || "launch";
        if (mode === "reopen") {
          runAction((a) => a.open_browser());
          return;
        }
        if (api()) api().clear_logs();
        if (logBox) logBox.textContent = "";
        const openBrowser = chkOpenBrowser ? chkOpenBrowser.checked : true;
        runTask((a) => a.launch_async(openBrowser), {
          switchConsole: true,
          showProgress: true,
        });
      });
    }

    if (btnRefreshPrereq) {
      btnRefreshPrereq.addEventListener("click", () => {
        runTask((a) => a.check_prerequisites_async(), {
          showProgress: true,
          indeterminate: true,
        });
      });
    }

    const btnUpgradeAll = $("btn_upgrade_all");
    if (btnUpgradeAll) {
      btnUpgradeAll.addEventListener("click", () => {
        if (!apiReady) return;
        if (!confirm("将尝试升级 Python 和所有依赖到最新兼容版本。\n\n是否继续？")) return;
        if (api()) api().clear_logs();
        if (logBox) logBox.textContent = "";
        runTask((a) => a.upgrade_all_async(), {
          switchConsole: true,
          showProgress: true,
        });
      });
    }

    if (btnUpgradePython) {
      btnUpgradePython.addEventListener("click", () => {
        if (!apiReady) return;
        if (!confirm("将尝试升级 Python 到最新兼容版本。\n\n是否继续？")) return;
        if (api()) api().clear_logs();
        if (logBox) logBox.textContent = "";
        runTask((a) => a.upgrade_python_async(), {
          switchConsole: true,
          showProgress: true,
        });
      });
    }

    if (btnUpgradeDeps) {
      btnUpgradeDeps.addEventListener("click", () => {
        if (!apiReady) return;
        if (!confirm("将尝试升级所有依赖到最新兼容版本。\n\n是否继续？")) return;
        if (api()) api().clear_logs();
        if (logBox) logBox.textContent = "";
        runTask((a) => a.upgrade_deps_async(), {
          switchConsole: true,
          showProgress: true,
        });
      });
    }

    if (selPython) {
      selPython.addEventListener("change", () => {
        if (!apiReady || busy) return;
        const newPath = selPython.value;
        if (!newPath) return;
        const label = selPython.selectedOptions[0].textContent;
        if (!confirm("将切换到 " + label + "，这会重建虚拟环境并重新安装所有依赖。\n\n是否继续？")) {
          loadAvailablePythons();
          return;
        }
        if (api()) api().clear_logs();
        if (logBox) logBox.textContent = "";
        runTask((a) => a.switch_python_async(newPath), {
          switchConsole: true,
          showProgress: true,
        });
      });
    }

    if (btnInstallEnv) {
      btnInstallEnv.addEventListener("click", () => {
        if (!apiReady) return;
        if (api()) api().clear_logs();
        if (logBox) logBox.textContent = "";
        const recreate = chkRecreateVenv ? chkRecreateVenv.checked : false;
        runTask((a) => a.install_environment_async(recreate, false), {
          switchConsole: true,
          showProgress: true,
        });
      });
    }

    if (btnInstallPython) {
      btnInstallPython.addEventListener("click", () => {
        if (!apiReady) return;
        const msg =
          "将尝试通过 winget 安装 Python 3.12，可能需要几分钟并需要网络。\n\n是否继续？";
        if (!confirm(msg)) return;
        if (api()) api().clear_logs();
        if (logBox) logBox.textContent = "";
        const recreate = chkRecreateVenv ? chkRecreateVenv.checked : false;
        runTask((a) => a.install_environment_async(recreate, true), {
          switchConsole: true,
          showProgress: true,
        });
      });
    }

    const btnClear = $("btn_clear_logs");
    if (btnClear) {
      btnClear.addEventListener("click", () => {
        if (api()) api().clear_logs();
        if (logBox) logBox.textContent = "";
      });
    }
  }

  async function waitForApi(maxMs) {
    const deadline = Date.now() + (maxMs || 8000);
    while (Date.now() < deadline) {
      const a = api();
      if (a && a.ping) {
        try {
          const res = await a.ping();
          if (res && res.ok) return true;
        } catch (_e) {
          /* retry */
        }
      }
      await new Promise((r) => setTimeout(r, 80));
    }
    return false;
  }

  async function onReady() {
    setApiEnabled(false);
    const ok = await waitForApi(10000);
    if (!ok) {
      if (statusBadge) {
        statusBadge.className = "status-badge error";
        statusBadge.textContent = "API 未就绪";
      }
      return;
    }
    apiReady = true;
    setApiEnabled(true);
    bindNav();
    bindControls();
    refreshStatus();
    loadSystemInfo();
    loadPrerequisites();
    loadAvailablePythons();
    if (window.NWWorlds && window.NWWorlds.init) window.NWWorlds.init();
  }

  window.addEventListener("pywebviewready", () => onReady());

  if (document.readyState === "complete" || document.readyState === "interactive") {
    setTimeout(() => {
      if (api() && !apiReady) onReady();
    }, 100);
  }

  setApiEnabled(false);
})();
