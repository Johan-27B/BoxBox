(() => {
  "use strict";

  const app = document.getElementById("app");
  const accessToken = new URLSearchParams(window.location.search).get("token") || "";
  const COMPLETED_PAGE_SIZE = 10;

  const COPY = {
    zh: {
      appLabel: "PERFRACE · PAIR VERIFICATION",
      title: "Dashboard",
      runId: "Run ID",
      language: "English",
      slots: "并发会话上限",
      addSlot: "+ Slot",
      importTitle: "导入候选 JSONL",
      importHelp: "选择一个 JSONL 文件，将候选项目批量加入队列。",
      chooseFile: "选择 JSONL 文件",
      importAction: "导入",
      repoTitle: "手动添加 GitHub 仓库",
      repoHelp: "输入公开 GitHub 仓库 URL，立即加入调度队列。",
      repoPlaceholder: "https://github.com/owner/repository",
      addCandidate: "加入队列",
      notificationsDenied: "浏览器未授予通知权限",
      sessionsTitle: "会话",
      sessionCount: "个会话",
      summaryNeedsHuman: "Needs Human",
      summaryRunning: "Running",
      summaryQueued: "Queued",
      summaryCompleted: "Completed",
      completedTasks: "已完成",
      previousPage: "上一页",
      nextPage: "下一页",
      page: "页",
      switchSession: "切换会话",
      emptyTitle: "暂无会话或候选项目",
      emptyBody: "导入 JSONL 或手动添加 GitHub 仓库以开始。",
      loading: "正在加载仪表板…",
      loadError: "无法加载仪表板",
      connectionError: "实时连接已断开，正在重连…",
      repo: "仓库 / 最终实例 ID",
      stage: "构建阶段",
      state: "状态",
      reason: "人工接管原因",
      elapsed: "已用时间",
      cost: "实时 Agent 成本",
      comments: "人工交互",
      noReason: "—",
      noInstance: "尚未生成最终实例",
      queuedStage: "等待 Slot",
      queued: "排队中",
      accepted: "已完成 · 接受",
      rejected: "已完成 · 拒绝",
      unknown: "未知",
      importSuccess: "候选文件已导入",
      addSuccess: "仓库已加入队列",
      noFile: "请先选择 JSONL 文件",
      invalidRepo: "请输入有效的 GitHub 仓库 URL",
      requestFailed: "请求失败",
      back: "返回会话",
      terminal: "终端",
      files: "文件",
      connecting: "连接中",
      connected: "已连接",
      disconnected: "已断开，正在重连",
      unavailable: "终端不可用",
      workspace: "工作区",
      treeLoading: "正在读取目录…",
      treeEmpty: "此目录为空",
      treeError: "无法读取目录",
      selectFile: "选择文件以只读预览",
      fileLoading: "正在读取文件…",
      fileError: "无法读取文件",
      binaryFile: "二进制文件无法预览",
      preview: "预览",
      source: "源码",
      loadMore: "加载更多",
      notifyTitle: "Needs Human",
      notifyBody: "会话需要人工处理",
      bytes: "字节",
    },
    en: {
      appLabel: "PERFRACE · PAIR VERIFICATION",
      title: "Dashboard",
      runId: "Run ID",
      language: "中文",
      slots: "Concurrent session limit",
      addSlot: "+ Slot",
      importTitle: "Import candidate JSONL",
      importHelp: "Choose a JSONL file to add candidate repositories in bulk.",
      chooseFile: "Choose JSONL file",
      importAction: "Import",
      repoTitle: "Add a GitHub repository",
      repoHelp: "Enter a public GitHub repository URL to add it to the scheduler.",
      repoPlaceholder: "https://github.com/owner/repository",
      addCandidate: "Add to queue",
      notificationsDenied: "Notification permission was not granted",
      sessionsTitle: "Sessions",
      sessionCount: "sessions",
      summaryNeedsHuman: "Needs Human",
      summaryRunning: "Running",
      summaryQueued: "Queued",
      summaryCompleted: "Completed",
      completedTasks: "Completed",
      previousPage: "Previous",
      nextPage: "Next",
      page: "Page",
      switchSession: "Switch session",
      emptyTitle: "No sessions or candidates yet",
      emptyBody: "Import a JSONL file or add a GitHub repository to begin.",
      loading: "Loading dashboard…",
      loadError: "Could not load the dashboard",
      connectionError: "Live connection lost. Reconnecting…",
      repo: "Repository / final instance ID",
      stage: "Construction stage",
      state: "State",
      reason: "Needs-human reason",
      elapsed: "Elapsed",
      cost: "Live Agent cost",
      comments: "Human interactions",
      noReason: "—",
      noInstance: "Final instance not created",
      queuedStage: "Waiting for Slot",
      queued: "Queued",
      accepted: "Completed · Accepted",
      rejected: "Completed · Rejected",
      unknown: "Unknown",
      importSuccess: "Candidate file imported",
      addSuccess: "Repository added to queue",
      noFile: "Choose a JSONL file first",
      invalidRepo: "Enter a valid GitHub repository URL",
      requestFailed: "Request failed",
      back: "Back to sessions",
      terminal: "Terminal",
      files: "Files",
      connecting: "Connecting",
      connected: "Connected",
      disconnected: "Disconnected; reconnecting",
      unavailable: "Terminal unavailable",
      workspace: "Workspace",
      treeLoading: "Loading directory…",
      treeEmpty: "This directory is empty",
      treeError: "Could not load directory",
      selectFile: "Select a file for a read-only preview",
      fileLoading: "Loading file…",
      fileError: "Could not load file",
      binaryFile: "Binary files cannot be previewed",
      preview: "Preview",
      source: "Source",
      loadMore: "Load more",
      notifyTitle: "Needs Human",
      notifyBody: "A session needs human attention",
      bytes: "bytes",
    },
  };

  const state = {
    language: localStorage.getItem("perfrace-dashboard-language") === "en" ? "en" : "zh",
    runId: "",
    slotLimit: 0,
    sessions: [],
    queue: [],
    loaded: false,
    error: "",
    flash: "",
    socketError: false,
    dashboardSocket: null,
    dashboardRetry: null,
    selectedSessionId: null,
    terminal: null,
    fitAddon: null,
    terminalSocket: null,
    terminalRetry: null,
    resizeObserver: null,
    detailResizeHandler: null,
    sessionSwitcherActive: false,
    renderedDetailId: null,
    viewMode: "",
    detailTab: "terminal",
    notificationsInitialized: false,
    audioContext: null,
    previousStates: new Map(),
    completedPage: 1,
    preview: null,
    fileAbort: null,
  };

  function t(key) {
    return COPY[state.language][key] || key;
  }

  function node(tag, options = {}, children = []) {
    const element = document.createElement(tag);
    if (options.className) element.className = options.className;
    if (options.text !== undefined) element.textContent = String(options.text);
    if (options.type) element.type = options.type;
    if (options.id) element.id = options.id;
    if (options.title) element.title = options.title;
    for (const [name, value] of Object.entries(options.attrs || {})) {
      element.setAttribute(name, String(value));
    }
    for (const child of children) {
      if (child) element.append(child);
    }
    return element;
  }

  function setBusy(button, busy) {
    button.disabled = busy;
    button.setAttribute("aria-busy", String(busy));
  }

  function apiError(error) {
    if (error instanceof Error && error.message) return error.message;
    return t("requestFailed");
  }

  async function request(url, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set("X-PerfRace-Token", accessToken);
    const response = await fetch(url, { ...options, headers });
    if (response.ok) return response.json();
    let detail = "";
    try {
      const payload = await response.json();
      detail = payload.detail || payload.message || "";
    } catch {
      detail = await response.text();
    }
    throw new Error(detail || `${t("requestFailed")} (${response.status})`);
  }

  function repositoryLabel(url) {
    try {
      const parsed = new URL(url);
      return parsed.pathname.replace(/^\/|\/$/g, "").replace(/\.git$/, "") || url;
    } catch {
      return url || t("unknown");
    }
  }

  function stateLabel(value) {
    const labels = {
      needs_human: "Needs Human",
      running: "Running",
      queued: t("queued"),
      accepted: t("accepted"),
      rejected: t("rejected"),
    };
    return labels[value] || value || t("unknown");
  }

  function stageLabel(value) {
    if (!value) return t("unknown");
    const protectedTerms = ["Realism", "Integrity", "Reliability"];
    const protectedTerm = protectedTerms.find(
      (term) => value.toLowerCase() === term.toLowerCase(),
    );
    return protectedTerm || value;
  }

  function elapsedSince(value, untilValue = "") {
    const started = Date.parse(value);
    if (!Number.isFinite(started)) return "—";
    const until = untilValue ? Date.parse(untilValue) : Date.now();
    if (!Number.isFinite(until)) return "—";
    let seconds = Math.max(0, Math.floor((until - started) / 1000));
    const days = Math.floor(seconds / 86400);
    seconds %= 86400;
    const hours = Math.floor(seconds / 3600);
    seconds %= 3600;
    const minutes = Math.floor(seconds / 60);
    seconds %= 60;
    const parts = [];
    if (days) parts.push(`${days}d`);
    if (hours || days) parts.push(`${hours}h`);
    if (minutes || hours || days) parts.push(`${minutes}m`);
    parts.push(`${seconds}s`);
    return parts.join(" ");
  }

  function costLabel(value) {
    if (value === null || value === undefined || value === "") return "—";
    const amount = Number(value);
    return Number.isFinite(amount) ? `$${amount.toFixed(4)}` : "—";
  }

  function byteLabel(value) {
    const bytes = Number(value);
    if (!Number.isFinite(bytes)) return "";
    if (bytes < 1024) return `${bytes} ${t("bytes")}`;
    const units = ["KB", "MB", "GB"];
    let size = bytes / 1024;
    let unit = units[0];
    for (let index = 1; index < units.length && size >= 1024; index += 1) {
      size /= 1024;
      unit = units[index];
    }
    return `${size.toFixed(size >= 10 ? 1 : 2)} ${unit}`;
  }

  function beep() {
    if (!state.audioContext) return;
    const oscillator = state.audioContext.createOscillator();
    const gain = state.audioContext.createGain();
    const now = state.audioContext.currentTime;
    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(740, now);
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.12, now + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.16);
    oscillator.connect(gain);
    gain.connect(state.audioContext.destination);
    oscillator.start(now);
    oscillator.stop(now + 0.17);
  }

  function notifyNeedsHuman(session) {
    beep();
    if ("Notification" in window && Notification.permission === "granted") {
      try {
        const notification = new Notification(t("notifyTitle"), {
          body: `${repositoryLabel(session.repo_url)} — ${
            session.engagement_reason || t("notifyBody")
          }`,
          tag: `perfrace-${session.session_id}`,
        });
        notification.onclick = () => {
          window.focus();
          window.location.hash = `session=${encodeURIComponent(session.session_id)}`;
        };
      } catch {
        // Audio remains available when the browser blocks desktop notifications.
      }
    }
  }

  function detectNeedsHumanTransitions(sessions, shouldNotify) {
    const nextStates = new Map();
    for (const session of sessions) {
      const id = String(session.session_id);
      const previous = state.previousStates.get(id);
      nextStates.set(id, session.state);
      if (
        state.notificationsInitialized &&
        session.state === "needs_human" &&
        previous !== "needs_human" &&
        (shouldNotify || previous === undefined)
      ) {
        notifyNeedsHuman(session);
      }
    }
    state.previousStates = nextStates;
  }

  function mergeUpdate(payload) {
    if (!payload || typeof payload !== "object") return;
    const hadData = state.loaded;
    if (typeof payload.runId === "string") state.runId = payload.runId;
    if (Number.isFinite(Number(payload.slotLimit))) {
      state.slotLimit = Number(payload.slotLimit);
    }
    if (Array.isArray(payload.sessions)) {
      detectNeedsHumanTransitions(payload.sessions, hadData);
      state.sessions = payload.sessions;
    } else {
      const changed = payload.session || (payload.session_id ? payload : null);
      if (changed && changed.session_id) {
        const sessions = [...state.sessions];
        const index = sessions.findIndex(
          (session) => String(session.session_id) === String(changed.session_id),
        );
        if (index >= 0) sessions[index] = { ...sessions[index], ...changed };
        else sessions.push(changed);
        detectNeedsHumanTransitions(sessions, hadData);
        state.sessions = sessions;
      }
    }
    if (Array.isArray(payload.queue)) state.queue = payload.queue;
    if (payload.removed_session_id) {
      state.sessions = state.sessions.filter(
        (session) => String(session.session_id) !== String(payload.removed_session_id),
      );
    }
    state.loaded = true;
    state.error = "";
    renderCurrentView();
  }

  function fieldRow(label, value, extraClass = "") {
    return node("div", { className: "field-row" }, [
      node("span", { className: "field-label", text: label }),
      node("span", {
        className: `field-value ${extraClass}`.trim(),
        text: value,
        title: value,
      }),
    ]);
  }

  function sessionCard(item, queued = false) {
    const sessionState = queued ? "queued" : item.state;
    const card = node(queued ? "article" : "button", {
      className: `session-card state-${sessionState || "unknown"}`,
      type: queued ? undefined : "button",
      attrs: {
        "aria-label": `${repositoryLabel(item.repo_url)}, ${stateLabel(sessionState)}`,
      },
    });
    const identity = node("div", { className: "card-identity" }, [
      node("div", { className: "card-top" }, [
        node("h3", {
          className: "repo-name",
          text: repositoryLabel(item.repo_url),
          title: item.repo_url || "",
        }),
        node("span", {
          className: `state-badge state-${sessionState || "unknown"}`,
          text: stateLabel(sessionState),
        }),
      ]),
      node("p", {
        className: "instance-id",
        text: item.instance_id || t("noInstance"),
        title: item.instance_id || t("noInstance"),
      }),
    ]);
    const details = node("div", { className: "card-fields" }, [
      fieldRow(t("stage"), queued ? t("queuedStage") : stageLabel(item.stage)),
      fieldRow(t("state"), stateLabel(sessionState)),
      fieldRow(
        t("reason"),
        queued ? t("noReason") : item.engagement_reason || t("noReason"),
      ),
    ]);
    const elapsed = fieldRow(
      t("elapsed"),
      queued ? "—" : elapsedSince(item.started_at, item.elapsed_until),
    );
    if (!queued) {
      elapsed.classList.add("elapsed-field");
      elapsed.dataset.startedAt = item.started_at || "";
      elapsed.dataset.elapsedUntil = item.elapsed_until || "";
    }
    const metrics = node("div", { className: "card-fields" }, [
      elapsed,
      fieldRow(t("cost"), queued ? "—" : costLabel(item.live_cost_usd)),
      fieldRow(t("comments"), queued ? "—" : String(item.human_comments ?? 0)),
    ]);
    card.append(identity, details, metrics);
    if (!queued) {
      card.addEventListener("click", () => {
        window.location.hash = `session=${encodeURIComponent(item.session_id)}`;
      });
    }
    return card;
  }

  function orderedCards() {
    const needsHuman = state.sessions.filter((session) => session.state === "needs_human");
    const running = state.sessions.filter((session) => session.state === "running");
    const otherActive = state.sessions.filter(
      (session) =>
        !["needs_human", "running", "accepted", "rejected"].includes(session.state),
    );
    return [
      ...needsHuman.map((item) => ({ item, queued: false })),
      ...running.map((item) => ({ item, queued: false })),
      ...otherActive.map((item) => ({ item, queued: false })),
      ...state.queue.map((item) => ({ item, queued: true })),
    ];
  }

  function completedPageData() {
    const completed = state.sessions
      .filter((session) => ["accepted", "rejected"].includes(session.state))
      .sort((left, right) => {
        const rightTime = Date.parse(right.updated_at || right.started_at) || 0;
        const leftTime = Date.parse(left.updated_at || left.started_at) || 0;
        return rightTime - leftTime || String(right.session_id).localeCompare(left.session_id);
      });
    const pageCount = Math.max(1, Math.ceil(completed.length / COMPLETED_PAGE_SIZE));
    state.completedPage = Math.min(Math.max(state.completedPage, 1), pageCount);
    const start = (state.completedPage - 1) * COMPLETED_PAGE_SIZE;
    return {
      items: completed.slice(start, start + COMPLETED_PAGE_SIZE),
      page: state.completedPage,
      pageCount,
      total: completed.length,
    };
  }

  function completedSection(pageData) {
    if (!pageData.total) return null;
    const previous = node("button", {
      className: "pagination-button",
      type: "button",
      text: t("previousPage"),
    });
    previous.disabled = pageData.page <= 1;
    previous.addEventListener("click", () => {
      state.completedPage -= 1;
      renderCurrentView(true);
    });
    const next = node("button", {
      className: "pagination-button",
      type: "button",
      text: t("nextPage"),
    });
    next.disabled = pageData.page >= pageData.pageCount;
    next.addEventListener("click", () => {
      state.completedPage += 1;
      renderCurrentView(true);
    });
    const list = node(
      "div",
      { id: "completed-list", className: "session-list" },
      pageData.items.map((item) => sessionCard(item)),
    );
    return node("section", { id: "completed-section", className: "completed-section" }, [
      node("div", { className: "section-heading" }, [
        node("h2", { text: t("completedTasks") }),
        node("div", { className: "pagination" }, [
          node("span", {
            className: "section-meta",
            text: `${t("page")} ${pageData.page} / ${pageData.pageCount} · ${pageData.total}`,
          }),
          previous,
          next,
        ]),
      ]),
      list,
    ]);
  }

  function showFlash(message) {
    state.flash = message;
    renderCurrentView();
    window.setTimeout(() => {
      if (state.flash === message) {
        state.flash = "";
        renderCurrentView();
      }
    }, 3200);
  }

  async function addSlot(button) {
    setBusy(button, true);
    try {
      if (state.dashboardSocket?.readyState === WebSocket.OPEN) {
        state.dashboardSocket.send(JSON.stringify({ type: "add_slot" }));
      } else {
        const payload = await request("/api/slots", { method: "POST" });
        if (Number.isFinite(Number(payload.slotLimit))) {
          state.slotLimit = Number(payload.slotLimit);
          renderCurrentView();
        }
      }
    } catch (error) {
      state.error = apiError(error);
      renderCurrentView();
    } finally {
      window.setTimeout(() => setBusy(button, false), 500);
    }
  }

  async function importCandidates(form, input, button) {
    if (!input.files?.length) {
      state.error = t("noFile");
      renderCurrentView();
      return;
    }
    setBusy(button, true);
    state.error = "";
    try {
      const content = await input.files[0].text();
      await request("/api/candidates/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      form.reset();
      showFlash(t("importSuccess"));
    } catch (error) {
      state.error = apiError(error);
      renderCurrentView();
    } finally {
      setBusy(button, false);
    }
  }

  async function addCandidate(form, input, button) {
    let url;
    try {
      url = new URL(input.value.trim());
      const parts = url.pathname.split("/").filter(Boolean);
      if (url.protocol !== "https:" || url.hostname !== "github.com" || parts.length < 2) {
        throw new Error();
      }
    } catch {
      state.error = t("invalidRepo");
      renderCurrentView();
      return;
    }
    setBusy(button, true);
    state.error = "";
    try {
      await request("/api/candidates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_url: url.toString() }),
      });
      form.reset();
      showFlash(t("addSuccess"));
    } catch (error) {
      state.error = apiError(error);
      renderCurrentView();
    } finally {
      setBusy(button, false);
    }
  }

  async function initializeNotifications() {
    if (state.notificationsInitialized) return;
    state.notificationsInitialized = true;
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (AudioContext) {
        state.audioContext ||= new AudioContext();
        if (state.audioContext.state === "suspended") await state.audioContext.resume();
      }
      let permission = "unsupported";
      if ("Notification" in window) {
        permission =
          Notification.permission === "default"
            ? await Notification.requestPermission()
            : Notification.permission;
      }
      if (permission === "denied") state.error = t("notificationsDenied");
      for (const session of state.sessions.filter(
        (item) => item.state === "needs_human",
      )) {
        notifyNeedsHuman(session);
      }
      renderCurrentView();
    } catch (error) {
      state.error = apiError(error);
      renderCurrentView();
    }
  }

  function toggleLanguage() {
    state.language = state.language === "zh" ? "en" : "zh";
    localStorage.setItem("perfrace-dashboard-language", state.language);
    document.documentElement.lang = state.language === "zh" ? "zh-CN" : "en";
    document.title =
      state.language === "zh"
        ? "PerfRace Pair Verification · 实例构建"
        : "PerfRace Pair Verification · Instance Construction";
    renderCurrentView(true);
  }

  function fillStatusArea(container) {
    container.replaceChildren();
    if (!state.loaded) container.append(node("div", { className: "loading-line" }));
    if (state.error) {
      container.append(
        node("div", {
          className: "error-banner",
          text: state.error,
          attrs: { role: "alert" },
        }),
      );
    } else if (state.socketError) {
      container.append(
        node("div", {
          className: "error-banner",
          text: t("connectionError"),
          attrs: { role: "status" },
        }),
      );
    }
    if (state.flash) {
      container.append(
        node("div", {
          className: "flash-banner",
          text: state.flash,
          attrs: { role: "status" },
        }),
      );
    }
  }

  function renderMain() {
    teardownDetail();
    state.viewMode = "main";
    const shell = node("main", { className: "shell" });
    const languageButton = node("button", {
      className: "language-toggle",
      type: "button",
      text: t("language"),
      attrs: { "aria-label": t("language") },
    });
    languageButton.addEventListener("click", toggleLanguage);
    shell.append(
      node("div", { className: "topbar" }, [
        node("span", {
          id: "run-id",
          className: "run-id-badge",
          text: `${t("runId")} · ${state.runId || "—"}`,
          title: state.runId || "",
        }),
        languageButton,
      ]),
    );

    const addSlotButton = node("button", {
      className: "primary-button",
      type: "button",
      text: t("addSlot"),
    });
    addSlotButton.addEventListener("click", () => addSlot(addSlotButton));
    shell.append(
      node("header", { className: "page-heading" }, [
        node("div", {}, [
          node("p", { className: "eyebrow", text: t("appLabel") }),
          node("h1", { text: t("title") }),
        ]),
        node("div", { className: "slot-block" }, [
          node("span", { className: "slot-count" }, [
            node("span", { text: `${t("slots")} ` }),
            node("strong", {
              id: "slot-limit",
              text: state.loaded ? state.slotLimit : "—",
            }),
          ]),
          addSlotButton,
        ]),
      ]),
    );

    const fileInput = node("input", {
      type: "file",
      attrs: {
        accept: ".jsonl,application/json,text/plain",
        "aria-label": t("chooseFile"),
      },
    });
    const importButton = node("button", {
      type: "submit",
      text: t("importAction"),
    });
    const importForm = node("form", { className: "file-form" }, [fileInput, importButton]);
    importForm.addEventListener("submit", (event) => {
      event.preventDefault();
      importCandidates(importForm, fileInput, importButton);
    });

    const repoInput = node("input", {
      type: "url",
      attrs: {
        placeholder: t("repoPlaceholder"),
        autocomplete: "url",
        spellcheck: "false",
        "aria-label": t("repoTitle"),
      },
    });
    const repoButton = node("button", {
      className: "primary-button",
      type: "submit",
      text: t("addCandidate"),
    });
    const repoForm = node("form", { className: "inline-form" }, [repoInput, repoButton]);
    repoForm.addEventListener("submit", (event) => {
      event.preventDefault();
      addCandidate(repoForm, repoInput, repoButton);
    });

    shell.append(
      node("section", { className: "controls-grid" }, [
        node("div", { className: "control-panel" }, [
          node("h2", { text: t("importTitle") }),
          node("p", { text: t("importHelp") }),
          importForm,
        ]),
        node("div", { className: "control-panel" }, [
          node("h2", { text: t("repoTitle") }),
          node("p", { text: t("repoHelp") }),
          repoForm,
        ]),
      ]),
    );

    const statusArea = node("div", { id: "status-area" });
    shell.append(statusArea);
    fillStatusArea(statusArea);

    const cards = orderedCards();
    const completed = completedPageData();
    const totalCards = cards.length + completed.total;
    const list = node("div", { id: "session-list", className: "session-list" });
    if (state.loaded && totalCards === 0) {
      list.append(
        node("div", { className: "empty-state" }, [
          node("strong", { text: t("emptyTitle") }),
          node("span", { text: t("emptyBody") }),
        ]),
      );
    } else {
      for (const card of cards) list.append(sessionCard(card.item, card.queued));
    }
    shell.append(
      node("section", {}, [
        node("div", { className: "section-heading" }, [
          node("h2", { text: t("sessionsTitle") }),
          node("span", {
            id: "session-count",
            className: "section-meta",
            text: `${totalCards} ${t("sessionCount")}`,
          }),
        ]),
        list,
      ]),
    );
    shell.append(
      node("div", { id: "completed-container" }, [completedSection(completed)]),
    );
    app.replaceChildren(shell);
  }

  function updateMainData() {
    const runId = document.getElementById("run-id");
    const slot = document.getElementById("slot-limit");
    const count = document.getElementById("session-count");
    const list = document.getElementById("session-list");
    const completedContainer = document.getElementById("completed-container");
    const statusArea = document.getElementById("status-area");
    const cards = orderedCards();
    const completed = completedPageData();
    const totalCards = cards.length + completed.total;
    if (runId) {
      runId.textContent = `${t("runId")} · ${state.runId || "—"}`;
      runId.title = state.runId || "";
    }
    if (slot) slot.textContent = state.loaded ? String(state.slotLimit) : "—";
    if (count) count.textContent = `${totalCards} ${t("sessionCount")}`;
    if (statusArea) fillStatusArea(statusArea);
    if (completedContainer) {
      const section = completedSection(completed);
      completedContainer.replaceChildren();
      if (section) completedContainer.append(section);
    }
    if (!list) return;
    list.replaceChildren();
    if (state.loaded && totalCards === 0) {
      list.append(
        node("div", { className: "empty-state" }, [
          node("strong", { text: t("emptyTitle") }),
          node("span", { text: t("emptyBody") }),
        ]),
      );
      return;
    }
    for (const card of cards) list.append(sessionCard(card.item, card.queued));
  }

  function teardownDetail() {
    if (state.terminalRetry) window.clearTimeout(state.terminalRetry);
    state.terminalRetry = null;
    if (state.terminalSocket) {
      state.terminalSocket.onclose = null;
      state.terminalSocket.onopen = null;
      state.terminalSocket.onmessage = null;
      state.terminalSocket.onerror = null;
      state.terminalSocket.close();
    }
    state.terminalSocket = null;
    state.resizeObserver?.disconnect();
    state.resizeObserver = null;
    if (state.detailResizeHandler) {
      window.removeEventListener("resize", state.detailResizeHandler);
    }
    state.detailResizeHandler = null;
    state.fileAbort?.abort();
    state.fileAbort = null;
    state.sessionSwitcherActive = false;
    state.terminal?.dispose();
    state.terminal = null;
    state.fitAddon = null;
    state.preview = null;
    state.renderedDetailId = null;
  }

  function terminalStatus(kind, label) {
    const dot = document.getElementById("terminal-status-dot");
    const text = document.getElementById("terminal-status-text");
    if (dot) dot.className = `connection-dot ${kind}`.trim();
    if (text) text.textContent = label;
  }

  function sendTerminalResize() {
    if (!state.fitAddon || !state.terminal) return;
    try {
      state.fitAddon.fit();
      if (state.terminalSocket?.readyState === WebSocket.OPEN) {
        state.terminalSocket.send(
          JSON.stringify({
            type: "resize",
            cols: state.terminal.cols,
            rows: state.terminal.rows,
          }),
        );
      }
    } catch {
      // The terminal may be hidden while the mobile detail tab changes.
    }
  }

  function connectTerminal(sessionId) {
    if (state.selectedSessionId !== sessionId || !state.terminal) return;
    terminalStatus("", t("connecting"));
    try {
      state.fitAddon?.fit();
    } catch {
      // Keep xterm's default geometry if the panel is temporarily hidden.
    }
    const terminal = state.terminal;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const parameters = new URLSearchParams({
      token: accessToken,
      cols: String(terminal.cols),
      rows: String(terminal.rows),
    });
    const socket = new WebSocket(
      `${protocol}//${window.location.host}/ws/sessions/${encodeURIComponent(
        sessionId,
      )}/terminal?${parameters}`,
    );
    const isCurrent = () =>
      state.selectedSessionId === sessionId &&
      state.terminal === terminal &&
      state.terminalSocket === socket;
    socket.binaryType = "arraybuffer";
    state.terminalSocket = socket;
    socket.onopen = () => {
      if (!isCurrent()) return;
      terminalStatus("connected", t("connected"));
      sendTerminalResize();
    };
    socket.onmessage = async (event) => {
      if (!isCurrent()) return;
      if (typeof event.data === "string") {
        terminal.write(event.data);
      } else if (event.data instanceof ArrayBuffer) {
        terminal.write(new Uint8Array(event.data));
      } else if (event.data instanceof Blob) {
        const data = new Uint8Array(await event.data.arrayBuffer());
        if (isCurrent()) terminal.write(data);
      }
    };
    socket.onerror = () => {
      if (isCurrent()) terminalStatus("error", t("unavailable"));
    };
    socket.onclose = () => {
      if (!isCurrent()) return;
      state.terminalSocket = null;
      terminalStatus("error", t("disconnected"));
      state.terminalRetry = window.setTimeout(() => connectTerminal(sessionId), 1800);
    };
  }

  function setupTerminal(sessionId) {
    const container = document.getElementById("terminal");
    if (!container || typeof window.Terminal !== "function") {
      terminalStatus("error", t("unavailable"));
      return;
    }
    state.terminal = new window.Terminal({
      cursorBlink: true,
      convertEol: false,
      fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
      fontSize: 13,
      lineHeight: 1.25,
      scrollback: 8000,
      theme: {
        background: "#171b17",
        foreground: "#e6eadf",
        cursor: "#d4a36f",
        selectionBackground: "#526049",
      },
    });
    const FitAddonClass = window.FitAddon?.FitAddon;
    if (FitAddonClass) {
      state.fitAddon = new FitAddonClass();
      state.terminal.loadAddon(state.fitAddon);
    }
    state.terminal.open(container);
    state.terminal.onData((data) => {
      if (state.terminalSocket?.readyState === WebSocket.OPEN) {
        state.terminalSocket.send(data);
      }
    });
    if ("ResizeObserver" in window) {
      state.resizeObserver = new ResizeObserver(sendTerminalResize);
      state.resizeObserver.observe(container);
    }
    window.setTimeout(sendTerminalResize, 0);
    connectTerminal(sessionId);
  }

  function setPreviewMessage(message) {
    const body = document.getElementById("preview-body");
    const path = document.getElementById("preview-path");
    const size = document.getElementById("preview-size");
    const actions = document.getElementById("preview-actions");
    const footer = document.getElementById("preview-footer");
    if (!body) return;
    body.className = "preview-placeholder";
    body.textContent = message;
    if (path) path.textContent = "";
    if (size) size.textContent = "";
    if (actions) actions.replaceChildren();
    if (footer) footer.replaceChildren();
  }

  function setPreviewMode(mode) {
    if (!state.preview?.renderedHtml) return;
    state.preview.mode = mode;
    renderPreview();
  }

  function renderPreview() {
    const preview = state.preview;
    const body = document.getElementById("preview-body");
    const path = document.getElementById("preview-path");
    const size = document.getElementById("preview-size");
    const actions = document.getElementById("preview-actions");
    const footer = document.getElementById("preview-footer");
    if (!preview || !body || !path || !size || !actions || !footer) return;
    path.textContent = preview.path;
    path.title = preview.path;
    size.textContent = byteLabel(preview.size);
    actions.replaceChildren();
    footer.replaceChildren();
    if (preview.binary) {
      body.className = "preview-placeholder";
      body.textContent = t("binaryFile");
      return;
    }
    if (preview.renderedHtml) {
      const previewButton = node("button", {
        className: "preview-mode-button",
        type: "button",
        text: t("preview"),
        attrs: { "aria-pressed": String(preview.mode !== "source") },
      });
      const sourceButton = node("button", {
        className: "preview-mode-button",
        type: "button",
        text: t("source"),
        attrs: { "aria-pressed": String(preview.mode === "source") },
      });
      previewButton.addEventListener("click", () => setPreviewMode("preview"));
      sourceButton.addEventListener("click", () => setPreviewMode("source"));
      actions.append(previewButton, sourceButton);
    }
    if (preview.renderedHtml && preview.mode !== "source") {
      body.className = "markdown-preview";
      body.innerHTML = preview.renderedHtml;
    } else {
      body.className = "file-preview";
      body.textContent = preview.content;
    }
    if (!preview.eof) {
      const more = node("button", {
        className: "load-more",
        type: "button",
        text: t("loadMore"),
      });
      more.addEventListener("click", () => loadFile(preview.path, preview.nextOffset, true));
      footer.append(more);
    }
  }

  async function loadFile(path, offset = 0, append = false) {
    state.fileAbort?.abort();
    const controller = new AbortController();
    const markdown = /\.(?:md|markdown)$/i.test(path);
    state.fileAbort = controller;
    if (!append) setPreviewMessage(t("fileLoading"));
    for (const row of document.querySelectorAll(".tree-row[data-file-path]")) {
      row.classList.toggle("selected", row.dataset.filePath === path);
    }
    try {
      const query = new URLSearchParams({
        path,
        offset: String(offset),
        limit: markdown ? "1048576" : "262144",
      });
      const payload = await request(
        `/api/sessions/${encodeURIComponent(state.selectedSessionId)}/file?${query}`,
        { signal: controller.signal },
      );
      if (controller.signal.aborted) return;
      const previous =
        append && state.preview?.path === path && !state.preview.binary
          ? state.preview.content
          : "";
      state.preview = {
        ...payload,
        path,
        content: `${previous}${payload.content || ""}`,
        mode: append
          ? state.preview?.mode || "source"
          : payload.renderedHtml
            ? "preview"
            : "source",
      };
      renderPreview();
    } catch (error) {
      if (error.name !== "AbortError") setPreviewMessage(`${t("fileError")}: ${apiError(error)}`);
    } finally {
      if (state.fileAbort === controller) state.fileAbort = null;
    }
  }

  function treeEntry(entry) {
    const item = node("li");
    const icon = node("span", {
      className: "tree-icon",
      text: entry.type === "directory" ? "▸" : "·",
      attrs: { "aria-hidden": "true" },
    });
    const button = node(
      "button",
      {
        className: "tree-row",
        type: "button",
        title: entry.path,
        attrs:
          entry.type === "directory"
            ? { "aria-expanded": "false" }
            : { "data-file-path": entry.path },
      },
      [icon, node("span", { className: "tree-name", text: entry.name })],
    );
    item.append(button);
    if (entry.type === "directory") {
      const children = node("ul", { className: "tree-children" });
      children.hidden = true;
      item.append(children);
      let loaded = false;
      button.addEventListener("click", async () => {
        const opening = children.hidden;
        children.hidden = !opening;
        button.setAttribute("aria-expanded", String(opening));
        icon.textContent = opening ? "▾" : "▸";
        if (opening && !loaded) {
          loaded = true;
          await loadDirectory(entry.path, children);
        }
      });
    } else {
      button.addEventListener("click", () => loadFile(entry.path));
    }
    return item;
  }

  async function loadDirectory(path, container) {
    container.replaceChildren(node("li", { className: "tree-message", text: t("treeLoading") }));
    try {
      const query = new URLSearchParams({ path });
      const payload = await request(
        `/api/sessions/${encodeURIComponent(state.selectedSessionId)}/tree?${query}`,
      );
      container.replaceChildren();
      if (!payload.entries?.length) {
        container.append(node("li", { className: "tree-message", text: t("treeEmpty") }));
        return;
      }
      for (const entry of payload.entries) container.append(treeEntry(entry));
    } catch (error) {
      container.replaceChildren(
        node("li", {
          className: "tree-message",
          text: `${t("treeError")}: ${apiError(error)}`,
        }),
      );
    }
  }

  function setDetailTab(tab) {
    state.detailTab = tab;
    const narrow = window.matchMedia("(max-width: 900px)").matches;
    const terminalPanel = document.getElementById("terminal-panel");
    const filesPanel = document.getElementById("files-panel");
    const terminalTab = document.getElementById("terminal-tab");
    const filesTab = document.getElementById("files-tab");
    if (terminalPanel) terminalPanel.hidden = narrow && tab !== "terminal";
    if (filesPanel) filesPanel.hidden = narrow && tab !== "files";
    terminalTab?.setAttribute("aria-selected", String(tab === "terminal"));
    filesTab?.setAttribute("aria-selected", String(tab === "files"));
    if (!narrow || tab === "terminal") window.setTimeout(sendTerminalResize, 0);
  }

  function fillDetailOverview(container) {
    const summaries = [
      {
        label: t("summaryNeedsHuman"),
        count: state.sessions.filter((item) => item.state === "needs_human").length,
        className: "state-needs_human",
      },
      {
        label: t("summaryRunning"),
        count: state.sessions.filter((item) => item.state === "running").length,
        className: "state-running",
      },
      {
        label: t("summaryQueued"),
        count: state.queue.length,
        className: "state-queued",
      },
      {
        label: t("summaryCompleted"),
        count: state.sessions.filter((item) =>
          ["accepted", "rejected"].includes(item.state),
        ).length,
        className: "state-completed",
      },
    ];
    const counts = node(
      "div",
      { className: "detail-summary-counts" },
      summaries.map((summary) =>
        node("span", { className: `summary-chip ${summary.className}` }, [
          node("span", { text: summary.label }),
          node("strong", { text: summary.count }),
        ]),
      ),
    );
    const select = node("select", {
      attrs: { "aria-label": t("switchSession") },
    });
    for (const session of state.sessions) {
      const option = node("option", {
        text: `${repositoryLabel(session.repo_url)} · ${stateLabel(session.state)}`,
        attrs: { value: session.session_id },
      });
      option.selected = String(session.session_id) === String(state.selectedSessionId);
      select.append(option);
    }
    select.disabled = state.sessions.length < 2;
    select.addEventListener("pointerdown", () => {
      state.sessionSwitcherActive = true;
    });
    select.addEventListener("focus", () => {
      state.sessionSwitcherActive = true;
    });
    select.addEventListener("blur", () => {
      state.sessionSwitcherActive = false;
      updateDetailHeader();
    });
    select.addEventListener("change", () => {
      state.sessionSwitcherActive = false;
      window.location.hash = `session=${encodeURIComponent(select.value)}`;
    });
    container.replaceChildren(
      counts,
      node("label", { className: "detail-session-switcher" }, [
        node("span", { text: t("switchSession") }),
        select,
      ]),
    );
  }

  function updateDetailHeader() {
    const session = state.sessions.find(
      (item) => String(item.session_id) === String(state.selectedSessionId),
    );
    if (!session) return;
    const title = document.getElementById("detail-title");
    const subtitle = document.getElementById("detail-subtitle");
    const badge = document.getElementById("detail-state");
    if (title) title.textContent = repositoryLabel(session.repo_url);
    if (subtitle) {
      subtitle.textContent = session.instance_id || session.session_id;
      subtitle.title = session.instance_id || session.session_id;
    }
    if (badge) {
      badge.className = `state-badge state-${session.state || "unknown"}`;
      badge.textContent = stateLabel(session.state);
    }
    const overview = document.getElementById("detail-overview");
    if (overview && !state.sessionSwitcherActive) fillDetailOverview(overview);
  }

  function renderMissingSession() {
    teardownDetail();
    state.viewMode = "missing";
    const back = node("button", {
      className: "back-button",
      type: "button",
      text: `← ${t("back")}`,
    });
    back.addEventListener("click", () => {
      window.location.hash = "";
    });
    app.replaceChildren(
      node("main", { className: "shell" }, [
        back,
        node("div", { className: "empty-state" }, [
          node("strong", { text: t("unknown") }),
          node("span", { text: t("loadError") }),
        ]),
      ]),
    );
  }

  function renderDetail(session) {
    teardownDetail();
    state.viewMode = "detail";
    state.renderedDetailId = String(session.session_id);
    const back = node("button", {
      className: "back-button",
      type: "button",
      text: `← ${t("back")}`,
    });
    back.addEventListener("click", () => {
      window.location.hash = "";
    });
    const languageButton = node("button", {
      className: "language-toggle",
      type: "button",
      text: t("language"),
    });
    languageButton.addEventListener("click", toggleLanguage);
    const header = node("header", { className: "detail-header" }, [
      back,
      node("div", { className: "detail-identity" }, [
        node("h1", {
          id: "detail-title",
          text: repositoryLabel(session.repo_url),
        }),
        node("p", {
          id: "detail-subtitle",
          text: session.instance_id || session.session_id,
          title: session.instance_id || session.session_id,
        }),
      ]),
      node("span", {
        className: "run-id-badge detail-run-id",
        text: `${t("runId")} · ${state.runId || "—"}`,
        title: state.runId || "",
      }),
      node("span", {
        id: "detail-state",
        className: `state-badge state-${session.state || "unknown"}`,
        text: stateLabel(session.state),
      }),
      languageButton,
    ]);
    const overview = node("section", {
      id: "detail-overview",
      className: "detail-overview",
      attrs: { "aria-label": t("sessionsTitle") },
    });
    fillDetailOverview(overview);

    const terminalTab = node("button", {
      id: "terminal-tab",
      className: "mobile-tab",
      type: "button",
      text: t("terminal"),
      attrs: { role: "tab", "aria-selected": "true" },
    });
    const filesTab = node("button", {
      id: "files-tab",
      className: "mobile-tab",
      type: "button",
      text: t("files"),
      attrs: { role: "tab", "aria-selected": "false" },
    });
    terminalTab.addEventListener("click", () => setDetailTab("terminal"));
    filesTab.addEventListener("click", () => setDetailTab("files"));

    const terminalPanel = node(
      "section",
      {
        id: "terminal-panel",
        className: "detail-panel terminal-panel",
        attrs: { "aria-label": t("terminal") },
      },
      [
        node("div", { className: "panel-toolbar" }, [
          node("span", { text: t("terminal") }),
          node("span", { className: "connection-line" }, [
            node("span", {
              id: "terminal-status-dot",
              className: "connection-dot",
              attrs: { "aria-hidden": "true" },
            }),
            node("span", { id: "terminal-status-text", text: t("connecting") }),
          ]),
        ]),
        node("div", { id: "terminal" }),
      ],
    );

    const treeRoot = node("ul", { id: "tree-root", className: "tree-list" }, [
      node("li", { className: "tree-message", text: t("treeLoading") }),
    ]);
    const filesPanel = node(
      "section",
      {
        id: "files-panel",
        className: "detail-panel files-panel",
        attrs: { "aria-label": t("files") },
      },
      [
        node("div", { className: "panel-toolbar" }, [
          node("span", { text: t("files") }),
          node("span", { text: t("workspace") }),
        ]),
        node("div", { className: "files-content" }, [
          node("nav", { className: "tree-pane", attrs: { "aria-label": t("files") } }, [
            treeRoot,
          ]),
          node("section", { className: "preview-pane", attrs: { "aria-live": "polite" } }, [
            node("div", { className: "preview-heading" }, [
              node("span", { id: "preview-path", className: "preview-path" }),
              node("span", { id: "preview-actions", className: "preview-actions" }),
              node("span", { id: "preview-size", className: "preview-size" }),
            ]),
            node("div", {
              id: "preview-body",
              className: "preview-placeholder",
              text: t("selectFile"),
            }),
            node("div", { id: "preview-footer" }),
          ]),
        ]),
      ],
    );
    const shell = node("main", { className: "detail-shell" }, [
      header,
      overview,
      node("div", { className: "mobile-tabs", attrs: { role: "tablist" } }, [
        terminalTab,
        filesTab,
      ]),
      node("div", { className: "detail-grid" }, [terminalPanel, filesPanel]),
    ]);
    app.replaceChildren(shell);
    state.detailResizeHandler = () => setDetailTab(state.detailTab);
    window.addEventListener("resize", state.detailResizeHandler);
    setDetailTab(state.detailTab);
    setupTerminal(String(session.session_id));
    loadDirectory("", treeRoot);
  }

  function renderCurrentView(force = false) {
    if (!state.selectedSessionId) {
      if (!force && state.viewMode === "main") updateMainData();
      else renderMain();
      return;
    }
    const session = state.sessions.find(
      (item) => String(item.session_id) === String(state.selectedSessionId),
    );
    if (!session) {
      if (state.loaded) renderMissingSession();
      else renderMain();
      return;
    }
    if (!force && state.renderedDetailId === String(session.session_id)) {
      updateDetailHeader();
      return;
    }
    renderDetail(session);
  }

  async function loadSnapshot() {
    try {
      const payload = await request("/api/snapshot");
      mergeUpdate(payload);
    } catch (error) {
      state.loaded = true;
      state.error = apiError(error);
      renderCurrentView();
    }
  }

  function connectDashboard() {
    if (state.dashboardRetry) window.clearTimeout(state.dashboardRetry);
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(
      `${protocol}//${window.location.host}/ws/dashboard?token=${encodeURIComponent(
        accessToken,
      )}`,
    );
    state.dashboardSocket = socket;
    socket.onopen = () => {
      state.socketError = false;
      if (state.viewMode === "main") updateMainData();
    };
    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message.type === "snapshot" || message.type === "update") {
          mergeUpdate(message.payload);
        }
      } catch (error) {
        state.error = apiError(error);
        renderCurrentView();
      }
    };
    socket.onerror = () => {
      state.socketError = true;
      if (state.viewMode === "main") updateMainData();
    };
    socket.onclose = () => {
      if (state.dashboardSocket === socket) state.dashboardSocket = null;
      state.socketError = true;
      if (state.viewMode === "main") updateMainData();
      state.dashboardRetry = window.setTimeout(connectDashboard, 1800);
    };
  }

  function readRoute() {
    const parameters = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    state.selectedSessionId = parameters.get("session");
    renderCurrentView(true);
  }

  function refreshElapsedLabels() {
    for (const row of document.querySelectorAll(".elapsed-field[data-started-at]")) {
      const value = row.querySelector(".field-value");
      if (value) {
        value.textContent = elapsedSince(
          row.dataset.startedAt,
          row.dataset.elapsedUntil,
        );
      }
    }
  }

  function initialize() {
    document.documentElement.lang = state.language === "zh" ? "zh-CN" : "en";
    document.title =
      state.language === "zh"
        ? "PerfRace Pair Verification · 实例构建"
        : "PerfRace Pair Verification · Instance Construction";
    const parameters = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    state.selectedSessionId = parameters.get("session");
    renderCurrentView(true);
    loadSnapshot();
    connectDashboard();
    window.addEventListener("hashchange", readRoute);
    window.addEventListener("pointerdown", initializeNotifications, { once: true });
    window.addEventListener("keydown", initializeNotifications, { once: true });
    window.setInterval(refreshElapsedLabels, 1000);
    window.addEventListener("beforeunload", () => {
      if (state.dashboardRetry) window.clearTimeout(state.dashboardRetry);
      state.dashboardSocket?.close();
      teardownDetail();
    });
  }

  initialize();
})();
