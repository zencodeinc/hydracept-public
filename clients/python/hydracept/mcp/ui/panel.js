function bindShell() {
  $("expand-btn").addEventListener("click", () => expandHost(state.app).then(publishSize));
}

async function connectPanel() {
  const Ext = globalThis.MCPExtApps;
  if (!Ext || !Ext.App) return;
  bindShell();
  bindImageGenerateControls();
  const app = new Ext.App(
    { name: "Hydracept panel", version: "0.3.11" },
    { availableDisplayModes: ["inline", "fullscreen"] },
    { autoResize: false },
  );
  app.ontoolresult = (params) => applyToolResult(params);
  app.onhostcontextchanged = (ctx) => {
    const next = ctx && typeof ctx === "object" ? ctx : {};
    const current = typeof app.getHostContext === "function" ? app.getHostContext() || {} : {};
    applyHostTheme({ ...current, ...next });
    expandHost(app).then(publishSize);
  };
  app.ontoolinput = (params) => {
    const args = (params && params.arguments) || {};
    if (args.prompt && $("prompt")) {
      $("prompt").value = args.prompt;
      setGenerateEnabled();
      scheduleQuote();
    }
    if (args.capability_key) state.capabilityKey = args.capability_key;
  };
  await app.connect();
  state.app = app;
  if (typeof app.getHostContext === "function") applyHostTheme(app.getHostContext() || {});
  await expandHost(app);
  publishSize();
  window.setTimeout(publishSize, 50);
  window.setTimeout(publishSize, 250);
}

connectPanel();
