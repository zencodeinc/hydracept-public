const PANEL_HEIGHT = 720;
const INTERACTION_SCHEMA = "hydracept.interaction.v1";
const SURFACE_IDS = [
  "project.connect",
  "capability.launch",
  "connection.resolve",
  "authorization.preflight",
  "job.progress",
  "artifact.review",
  "change.promote",
];

const state = {
  app: null,
  jobId: "",
  artifactId: "",
  capabilityKey: "",
  pollTimer: null,
  progressTimer: null,
  quoteTimer: null,
  hostEcho: 0,
  view: "",
  surface: "",
  contract: null,
  lastResult: null,
  lastInput: null,
  startedAt: 0,
  previewSrc: "",
  quotedCost: "",
  autoContinued: false,
  formValues: {},
  retainedRequest: null,
  waitingConnectUrl: "",
  connectContext: null,
};

const capabilityPlugins = Object.create(null);

function registerCapabilityPlugin(key, plugin) {
  capabilityPlugins[key] = plugin;
}

const $ = (id) => document.getElementById(id);

function applyHostTheme(ctx) {
  const Ext = globalThis.MCPExtApps || {};
  const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  const theme = (ctx && ctx.theme) || (prefersDark ? "dark" : "light");
  if (typeof Ext.applyDocumentTheme === "function") {
    Ext.applyDocumentTheme(theme);
  } else {
    document.documentElement.setAttribute("data-theme", theme);
    document.documentElement.style.colorScheme = theme;
  }
  const variables = ctx && ctx.styles && ctx.styles.variables;
  if (variables && typeof Ext.applyHostStyleVariables === "function") {
    Ext.applyHostStyleVariables(variables);
  }
  const fonts = ctx && ctx.styles && ctx.styles.css && ctx.styles.css.fonts;
  if (fonts && typeof Ext.applyHostFonts === "function") {
    Ext.applyHostFonts(fonts);
  }
}

applyHostTheme({});

function readStore(key, fallback) {
  try {
    const raw = window.localStorage.getItem(key);
    return raw == null ? fallback : raw;
  } catch {
    return fallback;
  }
}

function writeStore(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* sandbox may block persistence */
  }
}

function publishSize() {
  if (!state.app || typeof state.app.sendSizeChanged !== "function") return;
  const measured = Math.max(document.documentElement.scrollHeight || 0, document.body.scrollHeight || 0);
  const height = Math.max(measured, PANEL_HEIGHT);
  const width = Math.max(document.documentElement.scrollWidth || 0, 360);
  state.app.sendSizeChanged({ width, height });
}

async function expandHost(app) {
  if (!app || typeof app.requestDisplayMode !== "function") return;
  const ctx = typeof app.getHostContext === "function" ? app.getHostContext() || {} : {};
  const modes = Array.isArray(ctx.availableDisplayModes) ? ctx.availableDisplayModes : [];
  const want = modes.includes("fullscreen") ? "fullscreen" : "inline";
  if (modes.length && !modes.includes(want)) return;
  try {
    const result = await app.requestDisplayMode({ mode: want });
    const mode = (result && result.mode) || want;
    $("expand-btn").textContent = mode === "fullscreen" ? "Exit full size" : "Full size";
  } catch {
    /* host may decline */
  }
}

function structured(result) {
  if (!result) return {};
  const nested = result.structuredContent || result.structured_content;
  if (nested && typeof nested === "object") return nested;
  const text = (result.content || []).find((item) => item.type === "text");
  if (text && text.text) {
    try {
      return JSON.parse(text.text);
    } catch {
      return { text: text.text };
    }
  }
  return result;
}

function isFullContract(value) {
  return Boolean(
    value &&
      typeof value === "object" &&
      value.schemaVersion === INTERACTION_SCHEMA &&
      value.surface &&
      (Array.isArray(value.actions) || Array.isArray(value.fields) || value.title),
  );
}

function deriveSurfaceFromJob(job) {
  const status = String((job && (job.status || job.state)) || "").toLowerCase();
  if (!status) return "";
  if (status === "succeeded" || status === "completed") return "artifact.review";
  if (status === "awaiting_approval") return "authorization.preflight";
  return "job.progress";
}

function normalizeIncoming(result) {
  const data = structured(result);
  if (isFullContract(data)) {
    return { contract: data, result: data, surface: data.surface };
  }
  if (isFullContract(data.interaction)) {
    return { contract: data.interaction, result: data, surface: data.interaction.surface };
  }
  const hinted =
    data.surface ||
    (data.interaction && data.interaction.surface) ||
    (data.presentation && data.presentation.surface) ||
    "";
  if (hinted) {
    const contract = isFullContract(data.interaction)
      ? data.interaction
      : { ...(data.interaction || {}), surface: hinted, schemaVersion: INTERACTION_SCHEMA };
    return { contract, result: data, surface: hinted };
  }
  const job = data.job || data;
  const derived = deriveSurfaceFromJob(job);
  return { contract: data.interaction || null, result: data, surface: derived };
}

function isToolFailure(result, data) {
  if (!result && !data) return false;
  if (result && (result.isError === true || result.is_error === true)) return true;
  if (data && (data.isError === true || data.error === true)) return true;
  return false;
}

async function callTool(name, args) {
  if (!state.app || typeof state.app.callServerTool !== "function") {
    throw new Error("Hydracept panel is not connected to the host.");
  }
  state.hostEcho += 1;
  try {
    const result = await state.app.callServerTool({ name, arguments: args || {} });
    const data = structured(result);
    if (isToolFailure(result, data)) {
      throw new Error(data.message || data.code || "Tool failed");
    }
    return result;
  } finally {
    window.setTimeout(() => {
      state.hostEcho = Math.max(0, state.hostEcho - 1);
    }, 250);
  }
}

function stopPoll() {
  if (state.pollTimer) {
    clearTimeout(state.pollTimer);
    state.pollTimer = null;
  }
}

function setChip(label) {
  const chip = $("family-label");
  if (chip) chip.textContent = label || "Hydracept";
}

function setStage(title, lede) {
  if ($("stage-title")) $("stage-title").textContent = title || "Hydracept";
  if ($("stage-lede")) $("stage-lede").textContent = lede || "";
}

function hideProductViews() {
  ["launch-view", "progress-view", "complete-view"].forEach((id) => {
    const node = $(id);
    if (node) node.hidden = true;
  });
}

function showSurfaceRoot() {
  const root = $("surface-root");
  if (root) root.hidden = false;
}

function showError(message, details) {
  hideProductViews();
  showSurfaceRoot();
  const root = $("surface-root");
  root.replaceChildren();
  const title = document.createElement("p");
  title.className = "unsupported";
  title.textContent = message || "This Hydracept surface is not supported.";
  root.appendChild(title);
  if (details) {
    const meta = document.createElement("p");
    meta.className = "meta";
    meta.textContent = details;
    root.appendChild(meta);
  }
  publishSize();
}

function extractCost(payload) {
  if (!payload || typeof payload !== "object") return "";
  const pricing = payload.pricing || {};
  const charge = (pricing.charge && pricing.charge.customerCharge) || {};
  const quote = (pricing.quote && pricing.quote.customerTotal) || payload.expectedCharge || {};
  const display = charge.display || quote.display || payload.estimatedCostDisplay;
  if (display && String(display).trim()) return String(display).trim();
  const micros = charge.amountMicros ?? quote.amountMicros;
  if (micros == null || micros === "") return "";
  const n = Number(micros);
  if (!Number.isFinite(n)) return "";
  if (n === 0) return "billed by your provider (BYOK)";
  return `~$${(n / 1_000_000).toFixed(2)}`;
}

function openLinkPayload(url) {
  if (!url) return null;
  if (typeof url === "string") return { url };
  if (typeof url === "object" && typeof url.url === "string") return { url: url.url };
  return null;
}

async function openExternal(url) {
  const payload = openLinkPayload(url);
  if (!payload) return false;
  try {
    if (state.app && typeof state.app.openLink === "function") {
      await state.app.openLink(payload);
      return true;
    }
  } catch {
    /* host may decline; fall through */
  }
  try {
    if (state.app && typeof state.app.openUrl === "function") {
      await state.app.openUrl(payload);
      return true;
    }
  } catch {
    /* fall through */
  }
  const opened = window.open(payload.url, "_blank", "noopener");
  return Boolean(opened);
}

function capabilityKeyOf(contract, data) {
  return (
    (contract && contract.data && contract.data.capabilityKey) ||
    (data && data.capabilityKey) ||
    (data && data.job && data.job.capabilityKey) ||
    fieldNamed(contract, "capabilityKey") ||
    ""
  );
}

function fieldNamed(contract, name) {
  const fields = (contract && contract.fields) || [];
  const hit = fields.find((field) => field && field.name === name);
  return hit && hit.value;
}

function jobIdOf(contract, data) {
  return (
    (contract && contract.data && contract.data.jobId) ||
    (data && (data.jobId || (data.job && data.job.jobId))) ||
    fieldNamed(contract, "jobId") ||
    ""
  );
}

function jobFromSurface(contract, data) {
  const merged = Object.assign({}, (contract && contract.data) || {});
  if (data && data.job && typeof data.job === "object") Object.assign(merged, data.job);
  if (data && data.schemaVersion !== INTERACTION_SCHEMA) Object.assign(merged, data);
  return merged;
}

function isPrimaryAction(action) {
  return Boolean(action && (action.primary === true || action.style === "primary"));
}

const SECRET_MARKERS = ["secret", "apikey", "password", "credential", "privatekey", "accesskey"];
const TOKEN_PREFIXES = ["access", "api", "auth", "bearer", "id", "provider", "refresh", "secret", "session"];
const TERMINAL_JOB_STATES = [
  "succeeded",
  "completed",
  "failed",
  "failed_terminal",
  "canceled",
  "cancelled",
  "blocked_budget",
  "blocked_provider",
  "needs_attention",
];

function isSecretField(name) {
  const normalized = String(name || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  if (SECRET_MARKERS.some((marker) => normalized.includes(marker))) return true;
  if (normalized === "token") return true;
  if (!normalized.endsWith("token")) return false;
  const stem = normalized.slice(0, -5);
  return TOKEN_PREFIXES.some((prefix) => stem.endsWith(prefix));
}

function showNotice(message, details) {
  hideProductViews();
  showSurfaceRoot();
  const root = $("surface-root");
  root.replaceChildren();
  root.appendChild(Object.assign(document.createElement("p"), { className: "meta", textContent: message || "" }));
  if (details) {
    root.appendChild(Object.assign(document.createElement("p"), { className: "meta", textContent: details }));
  }
  publishSize();
}

function routeSurface(surface, contract, data) {
  if (surface !== "authorization.preflight") {
    state.autoContinued = false;
  }
  const explicitKey = capabilityKeyOf(contract, data);
  if (surface !== state.surface || (explicitKey && explicitKey !== state.capabilityKey)) {
    state.formValues = {};
  }
  state.surface = surface;
  state.contract = contract;
  state.lastResult = data;
  state.jobId = jobIdOf(contract, data) || state.jobId;
  if (explicitKey) state.capabilityKey = explicitKey;
  const payload = data || {};
  if (
    surface === "project.connect" &&
    (payload.status === "interaction_required" ||
      (contract && contract.data && (contract.data.status === "interaction_required" || contract.data.autoConnect === true)) ||
      payload.autoConnect === true) &&
    typeof renderConnectInteraction === "function"
  ) {
    setChip("Connect");
    renderConnectInteraction(payload, contract);
    return;
  }
  const key = explicitKey;
  if (surface === "capability.launch" && key && capabilityPlugins[key] && typeof capabilityPlugins[key].renderLaunch === "function") {
    setChip("Generate");
    capabilityPlugins[key].renderLaunch(contract, data);
    return;
  }
  if (surface === "job.progress" && key && capabilityPlugins[key] && typeof capabilityPlugins[key].renderProgress === "function") {
    const status = String(
      (data && (data.status || data.state)) ||
        (contract && contract.data && contract.data.status) ||
        fieldNamed(contract, "status") ||
        "",
    ).toLowerCase();
    if (!TERMINAL_JOB_STATES.includes(status)) {
      setChip(key === "image.generate.v1" ? "Generating" : "Working");
      capabilityPlugins[key].renderProgress(contract, data);
      return;
    }
  }
  if (surface === "artifact.review" && key && capabilityPlugins[key] && typeof capabilityPlugins[key].renderReview === "function") {
    const artifacts = jobFromSurface(contract, data).artifacts || [];
    const typed = (data && (data.typedOutput || data.output)) || (contract && contract.data && contract.data.typedOutput);
    if (artifacts.length || !typed) {
      setChip("Ready");
      capabilityPlugins[key].renderReview(contract, data);
      return;
    }
  }
  if (typeof renderInteractionContract === "function") {
    renderInteractionContract(surface, contract, data);
    maybeAutoContinuePreflight(contract, data);
    return;
  }
  showError("Unable to render this Hydracept surface.", surface);
}

function maybeAutoContinuePreflight(contract, data) {
  if (!contract || contract.surface !== "authorization.preflight") return;
  const auth =
    contract.authorization ||
    (contract.data && contract.data.authorization) ||
    {};
  if (auth.confirmationRequired !== false) return;
  const intentAuthorized =
    auth.status === "already_authorized_by_user_intent" ||
    auth.reason === "user_requested_execution";
  if (!intentAuthorized) return;
  const request = (contract.data && contract.data.request) || state.retainedRequest;
  const jobId = (contract.data && contract.data.jobId) || state.jobId;
  const approval = contract.data && contract.data.approval;
  if (!(jobId && approval) && !request) return;
  if (state.autoContinued) return;
  const primary = ((contract.actions || []).find(isPrimaryAction));
  if (!primary || typeof handleContractAction !== "function") return;
  state.autoContinued = true;
  window.setTimeout(() => {
    handleContractAction(primary, contract, data);
  }, 350);
}

function isBenignNonSurface(data) {
  if (!data || typeof data !== "object") return false;
  if (data.pricing || data.bytesBase64 || data.unsupported === true) return true;
  if (data.receiptId && !data.surface && !data.schemaVersion) return true;
  if (data.nextAction === "omit_execution_quoteId_on_submit") return true;
  return false;
}

function paintIncoming(result) {
  const normalized = normalizeIncoming(result);
  const data = normalized.result || {};
  let surface = normalized.surface || "";
  const job = jobFromSurface(normalized.contract, data);
  const derived = deriveSurfaceFromJob(job);
  if (surface === "job.progress" && derived === "artifact.review") {
    surface = "artifact.review";
    if (normalized.contract && typeof normalized.contract === "object") {
      normalized.contract = { ...normalized.contract, surface: "artifact.review" };
    }
  }
  if (data.status === "interaction_required") {
    routeSurface("project.connect", normalized.contract, data);
    return;
  }
  if (state.waitingConnectUrl) {
    if (data.status === "ready") {
      state.waitingConnectUrl = "";
      stopPoll();
      setChip("Connect");
      setStage("Workspace connected", "This workspace is ready. The agent can continue.");
      showNotice("Workspace connected. This workspace is ready.");
      return;
    }
    if (data.status === "interaction_required") {
      routeSurface("project.connect", normalized.contract, data);
      return;
    }
  }
  if (!surface) {
    if (data.applied || data.path || data.filename || data.note) {
      showNotice(data.note || (data.path ? `Saved ${data.filename || "file"} to ${data.path}` : "Done."));
      return;
    }
    if (isBenignNonSurface(data) || state.surface) return;
    showError("Hydracept did not return a recognized interaction surface.");
    return;
  }
  if (!SURFACE_IDS.includes(surface)) {
    showError("This Hydracept surface is not supported.", surface);
    return;
  }
  routeSurface(surface, normalized.contract, data);
}

function applyToolResult(result) {
  if (state.hostEcho > 0) return;
  paintIncoming(result);
}
