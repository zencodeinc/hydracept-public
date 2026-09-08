const TIMES_KEY = "hydracept.panel.jobTimes.v1";
const OUTPUT_KEY = "hydracept.panel.outputDir";
const DEFAULT_OUTPUT = ".hydracept/artifacts";
const SEED_TIMES = [
  { key: "low:1:16", ms: 20000 },
  { key: "medium:1:16", ms: 28000 },
  { key: "medium:2:16", ms: 50000 },
  { key: "high:1:16", ms: 55000 },
];

function loadTimes() {
  try {
    const parsed = JSON.parse(readStore(TIMES_KEY, "[]"));
    if (Array.isArray(parsed) && parsed.length) return parsed;
  } catch {
    /* use seeds */
  }
  return SEED_TIMES.slice();
}

function saveTimes(samples) {
  writeStore(TIMES_KEY, JSON.stringify(samples.slice(-40)));
}

function timingKey(input) {
  const width = Number((input && input.width) || 1024);
  const height = Number((input && input.height) || 1024);
  const bucket = Math.max(1, Math.round((width * height) / 65536));
  return `${(input && input.quality) || "medium"}:${Number((input && input.variantCount) || 1)}:${bucket}`;
}

function estimateMs(input) {
  const key = timingKey(input);
  const samples = loadTimes()
    .filter((item) => item && item.key === key && Number(item.ms) > 0)
    .map((item) => Number(item.ms))
    .sort((a, b) => a - b);
  if (samples.length) return samples[Math.floor(samples.length / 2)];
  const quality = { low: 22000, medium: 38000, high: 70000, auto: 40000 }[(input && input.quality) || "medium"] || 38000;
  const variants = Math.max(1, Number((input && input.variantCount) || 1));
  const pixels = Math.max(1, Number((input && input.width) || 1024) * Number((input && input.height) || 1024));
  return Math.round(quality * variants * (pixels / (1024 * 1024)));
}

function recordDuration(job, input) {
  const created = Date.parse((job && job.createdAt) || "") || state.startedAt;
  const completed = Date.parse((job && job.completedAt) || "") || Date.now();
  const ms = completed - created;
  if (!(ms > 3000 && ms < 600000)) return;
  const next = loadTimes();
  next.push({ key: timingKey(input || state.lastInput || {}), ms });
  saveTimes(next);
}

function formatSeconds(ms) {
  const secs = Math.max(0, Math.round(ms / 1000));
  if (secs < 5) return "a few seconds";
  if (secs < 90) return `about ${secs}s`;
  return `about ${Math.round(secs / 60)} min`;
}

function syncVariantButtons() {
  const value = String(Math.min(4, Math.max(1, Number($("variantCount").value) || 1)));
  $("variantCount").value = value;
  document.querySelectorAll("#variant-seg button").forEach((btn) => {
    btn.setAttribute("aria-pressed", btn.getAttribute("data-count") === value ? "true" : "false");
  });
}

function setGenerateEnabled() {
  const ready = Boolean($("prompt") && $("prompt").value.trim());
  if ($("run-btn")) $("run-btn").disabled = state.view !== "launch" || !ready;
  const hint = $("shortcut-hint");
  if (hint) {
    hint.textContent = ready ? `${shortcutLabel()}.` : `${shortcutLabel()}. Add a prompt first.`;
  }
}

function updateDownloadHint() {
  const hint = $("download-hint");
  if (hint) hint.textContent = `Writes a PNG to ${outputDir()}.`;
}

function renderCost(label) {
  const cost = $("cost-line");
  const run = $("run-btn");
  state.quotedCost = label || "";
  if (run) run.textContent = label ? `Generate · ${label}` : "Generate";
  if (!cost) return;
  if (label) {
    cost.textContent = `This run ${label}. Charged only if generation starts.`;
    return;
  }
  cost.textContent = $("prompt") && $("prompt").value.trim()
    ? "Starts a billed Hydracept job."
    : "Starts a billed Hydracept job. Quote appears after you add a prompt.";
}

let quoteSeq = 0;
async function refreshQuote() {
  setGenerateEnabled();
  updateDownloadHint();
  if (!$("prompt") || !$("prompt").value.trim() || !state.app) {
    renderCost("");
    return;
  }
  const seq = ++quoteSeq;
  $("cost-line").textContent = "Checking price…";
  try {
    const input = await buildInput();
    const quoted = structured(
      await callTool("hydracept_ui_quote", {
        capability_key: state.capabilityKey || "image.generate.v1",
        body: { input },
      }),
    );
    if (seq !== quoteSeq) return;
    renderCost(extractCost(quoted));
  } catch (err) {
    if (seq !== quoteSeq) return;
    renderCost("");
    if ($("cost-line")) {
      $("cost-line").textContent = `Quote failed: ${err.message || err}. You can still generate.`;
    }
  }
}

function scheduleQuote() {
  if (state.quoteTimer) clearTimeout(state.quoteTimer);
  state.quoteTimer = setTimeout(() => {
    state.quoteTimer = null;
    refreshQuote();
  }, 450);
}

function stopProgressTick() {
  if (state.progressTimer) {
    clearInterval(state.progressTimer);
    state.progressTimer = null;
  }
}

function tickProgress() {
  const fill = $("progress-fill");
  const eta = $("progress-eta");
  if (!fill) return;
  const elapsed = Date.now() - (state.startedAt || Date.now());
  const pct = Math.min(92, Math.max(5, (elapsed / Math.max(state.etaMs || 28000, 1000)) * 88 + 5));
  fill.style.width = `${pct}%`;
  if (eta) {
    eta.textContent = `Still working · ${formatSeconds(elapsed)} elapsed`;
  }
}

function startProgress(input) {
  state.lastInput = input || state.lastInput;
  state.startedAt = Date.now();
  state.etaMs = estimateMs(state.lastInput || {});
  stopProgressTick();
  const fill = $("progress-fill");
  if (fill) fill.style.width = "5%";
  tickProgress();
  state.progressTimer = setInterval(tickProgress, 400);
}

function finishProgress() {
  stopProgressTick();
  const fill = $("progress-fill");
  if (fill) fill.style.width = "100%";
  const eta = $("progress-eta");
  if (eta) eta.textContent = "";
}

function outputDir() {
  const value = ($("output-dir") && $("output-dir").value.trim()) || DEFAULT_OUTPUT;
  return value || DEFAULT_OUTPUT;
}

function persistOutputDir() {
  writeStore(OUTPUT_KEY, outputDir());
}

function applySizePreset() {
  const preset = $("size-preset").value;
  const custom = $("custom-size");
  if (preset === "custom") {
    custom.hidden = false;
    publishSize();
    return;
  }
  custom.hidden = true;
  const [width, height] = preset.split("x").map((part) => Number(part));
  if (width) $("width").value = String(width);
  if (height) $("height").value = String(height);
  constraintHint();
}

function isMac() {
  return /Mac|iPhone|iPad/.test(navigator.platform || "");
}

function shortcutLabel() {
  return isMac() ? "⌘ Enter generates" : "Ctrl+Enter generates";
}

function showImageView(view) {
  state.view = view;
  const root = $("surface-root");
  if (root) {
    root.hidden = true;
    root.replaceChildren();
  }
  $("launch-view").hidden = view !== "launch";
  $("progress-view").hidden = view !== "progress";
  $("complete-view").hidden = view !== "complete";
  const titles = {
    launch: "Generate image",
    progress: "Generating…",
    complete: "Image ready",
  };
  const ledes = {
    launch: "Describe the asset, then generate. You can preview before saving.",
    progress: "Keep this panel open. Status comes from the job, not a fabricated ETA.",
    complete: "Preview first. Use in chat does not write a file; Download does.",
  };
  setChip(view === "launch" ? "Generate" : view === "progress" ? "Generating" : "Ready");
  setStage(titles[view] || "Generate image", ledes[view] || "");
  publishSize();
}

function sheetEnabled() {
  return $("sheet-enabled") && $("sheet-enabled").checked;
}

function constraintHint() {
  const hint = $("constraint-hint");
  if (!hint) return;
  if (!sheetEnabled()) {
    hint.textContent = "";
    return;
  }
  const rows = Number($("sheet-rows").value || 1);
  const cols = Number($("sheet-cols").value || 1);
  const width = Number($("width").value || 0);
  const height = Number($("height").value || 0);
  const cellW = Math.floor(width / cols);
  const cellH = Math.floor(height / rows);
  const pixels = cellW * cellH;
  const minPixels = 655360;
  const aligned = 816;
  const needW = aligned * cols;
  const needH = aligned * rows;
  if (pixels < minPixels) {
    hint.replaceChildren();
    hint.append(
      document.createTextNode(
        `Each frame needs to be at least 816×816. ${width}×${height} is too small for a ${rows}×${cols} sheet.`,
      ),
    );
    const apply = document.createElement("button");
    apply.type = "button";
    apply.className = "secondary";
    apply.textContent = `Use ${needW}×${needH}`;
    apply.addEventListener("click", () => {
      $("size-preset").value = "custom";
      $("custom-size").hidden = false;
      $("width").value = String(needW);
      $("height").value = String(needH);
      constraintHint();
      scheduleQuote();
    });
    hint.appendChild(apply);
  } else {
    hint.textContent = `Each frame is ${cellW}×${cellH} — large enough to slice.`;
  }
}

function snap16(value) {
  const n = Math.max(256, Math.min(3840, Number(value) || 1024));
  return Math.round(n / 16) * 16;
}

function snapCustomSize() {
  $("width").value = String(snap16($("width").value));
  $("height").value = String(snap16($("height").value));
  constraintHint();
}

function updateReferenceList() {
  const files = Array.from(($("references") && $("references").files) || []).slice(0, 4);
  $("reference-list").textContent = files.length
    ? `${files.length} selected · ${files.map((file) => file.name).join(", ")}`
    : "";
  const dropLabel = $("reference-drop-label");
  if (dropLabel) {
    dropLabel.textContent = files.length
      ? `${files.length} reference${files.length === 1 ? "" : "s"} ready · click to replace`
      : "Drop images or click to choose · optional · up to 4 · 2 MB each";
  }
}

function readFileAsReference(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result || "");
      const comma = dataUrl.indexOf(",");
      if (comma < 0) {
        resolve(null);
        return;
      }
      const header = dataUrl.slice(0, comma);
      const mime = (header.match(/data:([^;]+)/) || [])[1] || file.type || "image/png";
      resolve({
        dataBase64: dataUrl.slice(comma + 1),
        mimeType: mime,
        filename: file.name,
      });
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

async function readReferences() {
  const files = Array.from(($("references") && $("references").files) || []).slice(0, 4);
  const out = [];
  for (const file of files) {
    if (file.size > 2_000_000) {
      throw new Error(`${file.name} is larger than 2 MB. Use a smaller reference.`);
    }
    const item = await readFileAsReference(file);
    if (item) out.push(item);
  }
  return out;
}

async function buildInput() {
  const input = {
    prompt: $("prompt").value.trim(),
    width: snap16($("width").value),
    height: snap16($("height").value),
    quality: $("quality").value,
    variantCount: Number($("variantCount").value || 1),
    requestTransparentOutput: $("transparent").checked,
  };
  $("width").value = String(input.width);
  $("height").value = String(input.height);
  const references = await readReferences();
  if (references.length) input.referenceImages = references;
  if (sheetEnabled()) {
    const labels = $("sheet-labels").value
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean);
    input.sheet = {
      rows: Number($("sheet-rows").value || 1),
      columns: Number($("sheet-cols").value || 1),
      slice: true,
    };
    if (labels.length) input.sheet.labels = labels;
  }
  return input;
}

async function pollJob() {
  if (!state.jobId) return;
  const result = structured(await callTool("hydracept_ui_poll_job", { job_id: state.jobId }));
  const job = result.job || result;
  const status = String(result.state || job.status || "").toLowerCase();
  const statusCopy = {
    queued: "Queued",
    running: "Generating",
    canceling: "Stopping",
    succeeded: "Done",
    awaiting_approval: "Needs authorization",
  };
  if ($("progress-meta")) {
    $("progress-meta").textContent = statusCopy[status] || status || "Generating";
    $("progress-meta").title = state.jobId || "";
  }
  if (status === "awaiting_approval") {
    stopPoll();
    finishProgress();
    paintIncoming(result);
    return;
  }
  if (status === "succeeded" || result.nextAction === "download_artifacts") {
    stopPoll();
    recordDuration(job, state.lastInput);
    finishProgress();
    await showComplete(job, result);
    return;
  }
  if (["failed", "canceled", "cancelled", "needs_attention"].includes(status) || result.nextAction === "stop") {
    stopPoll();
    finishProgress();
    $("launch-error").hidden = false;
    $("launch-error").textContent = (job.error && job.error.message) || status || "Job failed";
    showImageView("launch");
    return;
  }
  const wait = Number(result.pollAfterSeconds || 4) * 1000;
  state.pollTimer = setTimeout(pollJob, wait);
}

function inferPrimary(job, result) {
  const explicit = String(
    result.previewArtifactId || result.primaryArtifactId || job.primaryArtifactId || "",
  ).trim();
  if (explicit) return explicit;
  const variant = job.variantSet && typeof job.variantSet === "object" ? job.variantSet : {};
  const selectedId = String(variant.selectedArtifactId || "").trim();
  if (selectedId) return selectedId;
  const artifacts = Array.isArray(job.artifacts) ? job.artifacts : [];
  const chosen = artifacts.filter((item) => item && item.selected === true && item.artifactId);
  if (chosen.length === 1) return String(chosen[0].artifactId);
  const ranked = artifacts
    .filter((item) => item && item.artifactId)
    .sort((a, b) => Number(a.variantIndex || 0) - Number(b.variantIndex || 0));
  if (ranked.length) return String(ranked[0].artifactId);
  return "";
}

function imageArtifacts(job) {
  return (Array.isArray(job.artifacts) ? job.artifacts : []).filter(
    (item) => item && item.artifactId && String(item.mediaType || "image/png").startsWith("image/"),
  );
}

async function loadPreview(artifactId) {
  const preview = structured(
    await callTool("hydracept_ui_artifact_preview", {
      jobId: state.jobId,
      artifactId,
    }),
  );
  const src =
    preview.bytesBase64 && String(preview.mediaType || "").startsWith("image/")
      ? `data:${preview.mediaType};base64,${preview.bytesBase64}`
      : "";
  return { preview, src };
}

function openLightbox(src) {
  if (!src) return;
  $("lightbox-image").src = src;
  $("lightbox").hidden = false;
}

function closeLightbox() {
  $("lightbox").hidden = true;
}

function bindPreviewTools() {
  const tools = $("preview-tools");
  const stage = $("preview-stage");
  if (!tools || !stage || tools.dataset.bound === "1") return;
  tools.dataset.bound = "1";
  tools.querySelectorAll("button[data-bg]").forEach((btn) => {
    btn.addEventListener("click", () => {
      stage.dataset.bg = btn.getAttribute("data-bg") || "checker";
      tools.querySelectorAll("button[data-bg]").forEach((node) => {
        node.setAttribute("aria-pressed", node === btn ? "true" : "false");
      });
    });
  });
  const actual = $("actual-size-btn");
  if (actual) {
    actual.addEventListener("click", () => {
      stage.classList.toggle("actual-size");
      actual.setAttribute("aria-pressed", stage.classList.contains("actual-size") ? "true" : "false");
    });
  }
}

function provenanceText(job, result) {
  const report = result.transparencyReport || job.transparencyReport || {};
  const charge = extractCost(job) || extractCost(result);
  const parts = [
    job.capabilityKey || result.capabilityKey,
    job.jobId || result.jobId,
    job.provider || (job.route && job.route.provider),
    charge && `charge ${charge}`,
    (report.sha256 || job.sha256) && `sha ${(report.sha256 || job.sha256).slice(0, 12)}`,
    report.verdict && `alpha ${report.verdict}`,
  ];
  return parts.filter(Boolean).join(" · ");
}

async function showComplete(job, result) {
  bindPreviewTools();
  showImageView("complete");
  const artifacts = imageArtifacts(job);
  const primary = inferPrimary(job, result);
  state.artifactId = primary;
  const receiptId = result.receiptId || job.receiptId || "";
  const gallery = $("preview-gallery");
  const hero = $("preview-image");
  gallery.innerHTML = "";
  gallery.hidden = artifacts.length < 2;
  hero.hidden = true;
  state.previewSrc = "";
  $("receipt-line").className = "meta";
  const billed = extractCost(job) || extractCost(result) || state.quotedCost;
  $("receipt-line").textContent = [
    artifacts.length > 1
      ? `${artifacts.length} images — click one to choose, click it again to enlarge`
      : "Click the image to enlarge",
    billed && `This job ${billed}`,
  ]
    .filter(Boolean)
    .join(" · ");
  $("receipt-line").dataset.receiptId = receiptId;
  $("receipt-line").dataset.artifactId = primary;
  const provenance = $("provenance-line");
  if (provenance) provenance.textContent = provenanceText(job, result);
  if (!artifacts.length && !primary) {
    $("receipt-line").textContent = [$("receipt-line").textContent, "No image to preview"]
      .filter(Boolean)
      .join(" · ");
    return;
  }
  try {
    if (artifacts.length <= 1) {
      const loaded = await loadPreview(primary || (artifacts[0] && artifacts[0].artifactId) || "");
      if (loaded.src) {
        hero.src = loaded.src;
        hero.hidden = false;
        state.previewSrc = loaded.src;
      } else {
        $("receipt-line").textContent += " · preview returned no image bytes";
      }
      return;
    }
    for (const item of artifacts) {
      const loaded = await loadPreview(item.artifactId);
      if (!loaded.src) continue;
      const btn = document.createElement("button");
      btn.type = "button";
      if (item.artifactId === state.artifactId) {
        btn.classList.add("selected");
        state.previewSrc = loaded.src;
      }
      const img = document.createElement("img");
      const take = Number(item.variantIndex || 0) + 1;
      img.alt = item.filename || `Take ${take}`;
      img.src = loaded.src;
      const caption = document.createElement("span");
      caption.textContent = item.filename || `Take ${take}`;
      btn.appendChild(img);
      btn.appendChild(caption);
      btn.addEventListener("click", async () => {
        if (state.artifactId === String(item.artifactId)) {
          openLightbox(loaded.src);
          return;
        }
        state.artifactId = String(item.artifactId);
        state.previewSrc = loaded.src;
        gallery.querySelectorAll("button").forEach((node) => node.classList.remove("selected"));
        btn.classList.add("selected");
        try {
          await callTool("hydracept_ui_select_variant", {
            job_id: state.jobId,
            artifact_id: String(item.artifactId),
          });
        } catch {
          /* selection is best-effort */
        }
      });
      gallery.appendChild(btn);
    }
    gallery.hidden = gallery.childElementCount === 0;
  } catch (err) {
    $("receipt-line").textContent += ` · preview unavailable (${err.message || err})`;
  }
}

async function runImageGenerate() {
  $("launch-error").hidden = true;
  persistOutputDir();
  constraintHint();
  if (state.quoteTimer) {
    clearTimeout(state.quoteTimer);
    state.quoteTimer = null;
  }
  quoteSeq += 1;
  const input = await buildInput();
  if (!input.prompt) {
    $("launch-error").hidden = false;
    $("launch-error").textContent = "Prompt is required.";
    return;
  }
  $("run-btn").disabled = true;
  stopPoll();
  showImageView("progress");
  startProgress(input);
  try {
    const submitted = structured(
      await callTool("hydracept_ui_submit_job", {
        capability_key: state.capabilityKey || "image.generate.v1",
        body: { input },
      }),
    );
    state.jobId = submitted.jobId || submitted.id || (submitted.job && (submitted.job.jobId || submitted.job.id)) || "";
    $("progress-meta").textContent = "Starting…";
    await pollJob();
  } catch (err) {
    finishProgress();
    showImageView("launch");
    $("launch-error").hidden = false;
    $("launch-error").textContent = err.message || String(err);
  } finally {
    setGenerateEnabled();
  }
}

async function saveToOutput() {
  const result = structured(
    await callTool("hydracept_ui_download_artifact", {
      jobId: state.jobId,
      artifactId: state.artifactId || "",
      output_path: outputDir(),
    }),
  );
  const path = result.path || "";
  const filename = result.filename || "";
  if (!path) throw new Error(result.message || "Save did not return a file path");
  return { path, filename, result };
}

async function downloadArtifact() {
  if (!state.jobId) {
    $("receipt-line").textContent = "No job to save yet.";
    return;
  }
  $("use-btn").disabled = true;
  $("download-btn").disabled = true;
  try {
    persistOutputDir();
    const saved = await saveToOutput();
    $("receipt-line").className = "meta ok";
    $("receipt-line").textContent = `Downloaded ${saved.filename || "image"} to ${saved.path}`;
  } catch (err) {
    $("receipt-line").className = "meta error";
    $("receipt-line").textContent = `Download failed: ${err.message || err}`;
  } finally {
    $("use-btn").disabled = false;
    $("download-btn").disabled = false;
  }
}

async function useArtifact() {
  if (!state.jobId) {
    $("receipt-line").textContent = "No job to use yet.";
    return;
  }
  $("use-btn").disabled = true;
  $("download-btn").disabled = true;
  try {
    const loaded = await loadPreview(state.artifactId || "");
    const filename = (loaded.preview && loaded.preview.filename) || state.artifactId || "image";
    const text =
      `Use this Hydracept image (${filename}). Job ${state.jobId}. Artifact ${state.artifactId}` +
      ($("receipt-line").dataset.receiptId
        ? `. Receipt ${$("receipt-line").dataset.receiptId}`
        : "") +
      `. This was handed to chat via Use, not saved to disk. Download if you need a workspace file.`;
    if (typeof state.app.sendMessage === "function") {
      const content = [{ type: "text", text }];
      if (loaded.preview && loaded.preview.bytesBase64 && Number(loaded.preview.byteLength || 0) < 750000) {
        content.push({
          type: "image",
          mimeType: loaded.preview.mediaType || "image/png",
          data: loaded.preview.bytesBase64,
        });
      }
      await state.app.sendMessage({ role: "user", content });
      $("receipt-line").className = "meta ok";
      $("receipt-line").textContent = `Sent to chat. The agent can use this image now. Nothing was saved to disk.`;
      return;
    }
    persistOutputDir();
    const saved = await saveToOutput();
    $("receipt-line").className = "meta";
    $("receipt-line").textContent =
      `This host cannot send images to chat. Saved ${saved.filename} to ${saved.path} instead.`;
  } catch (err) {
    $("receipt-line").className = "meta error";
    $("receipt-line").textContent = `Use failed: ${err.message || err}`;
  } finally {
    $("use-btn").disabled = false;
    $("download-btn").disabled = false;
  }
}

function bindImageGenerateControls() {
  if (!$("run-btn") || $("run-btn").dataset.bound === "1") return;
  $("run-btn").dataset.bound = "1";
  $("sheet-enabled").addEventListener("change", () => {
    $("sheet-controls").hidden = !sheetEnabled();
    constraintHint();
    publishSize();
    scheduleQuote();
  });
  ["width", "height", "sheet-rows", "sheet-cols"].forEach((id) => {
    $(id).addEventListener("input", () => {
      constraintHint();
      scheduleQuote();
    });
  });
  $("size-preset").addEventListener("change", () => {
    applySizePreset();
    scheduleQuote();
  });
  $("output-dir").addEventListener("change", () => {
    persistOutputDir();
    updateDownloadHint();
  });
  $("references").addEventListener("change", updateReferenceList);
  ["width", "height"].forEach((id) => {
    $(id).addEventListener("blur", snapCustomSize);
  });
  $("quality").addEventListener("change", scheduleQuote);
  $("transparent").addEventListener("change", scheduleQuote);
  $("prompt").addEventListener("input", () => {
    setGenerateEnabled();
    scheduleQuote();
  });
  document.querySelectorAll("#variant-seg button").forEach((btn) => {
    btn.addEventListener("click", () => {
      $("variantCount").value = btn.getAttribute("data-count") || "1";
      syncVariantButtons();
      scheduleQuote();
    });
  });
  const drop = $("reference-drop");
  if (drop) {
    ["dragenter", "dragover"].forEach((name) => {
      drop.addEventListener(name, (event) => {
        event.preventDefault();
        drop.classList.add("drag");
      });
    });
    ["dragleave", "drop"].forEach((name) => {
      drop.addEventListener(name, (event) => {
        event.preventDefault();
        drop.classList.remove("drag");
      });
    });
    drop.addEventListener("drop", (event) => {
      const files = event.dataTransfer && event.dataTransfer.files;
      if (!files || !files.length) return;
      try {
        const transfer = new DataTransfer();
        Array.from(files).slice(0, 4).forEach((file) => transfer.items.add(file));
        $("references").files = transfer.files;
      } catch {
        /* host may not expose DataTransfer */
      }
      updateReferenceList();
    });
  }
  $("run-btn").addEventListener("click", runImageGenerate);
  $("download-btn").addEventListener("click", downloadArtifact);
  $("use-btn").addEventListener("click", useArtifact);
  if ($("stop-watch-btn")) {
    $("stop-watch-btn").addEventListener("click", () => {
      stopPoll();
      finishProgress();
      setStage("Stopped watching", "The job keeps running. Stop watching does not cancel it.");
    });
  }
  if ($("cancel-job-btn")) {
    $("cancel-job-btn").addEventListener("click", async () => {
      if (!state.jobId) {
        $("launch-error").hidden = false;
        $("launch-error").textContent = "No job id is available to cancel.";
        return;
      }
      try {
        paintIncoming(await callTool("hydracept_ui_cancel_job", { job_id: state.jobId }));
      } catch (err) {
        $("launch-error").hidden = false;
        $("launch-error").textContent = err.message || String(err);
        showImageView("launch");
      }
    });
  }
  $("again-btn").addEventListener("click", () => {
    $("launch-error").hidden = true;
    showImageView("launch");
    setGenerateEnabled();
    $("prompt").focus();
  });
  $("prompt").addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      runImageGenerate();
    }
  });
  $("preview-image").addEventListener("click", () => openLightbox(state.previewSrc || $("preview-image").src));
  $("lightbox-close").addEventListener("click", closeLightbox);
  $("lightbox").addEventListener("click", (event) => {
    if (event.target === $("lightbox")) closeLightbox();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeLightbox();
  });
  $("output-dir").value = readStore(OUTPUT_KEY, DEFAULT_OUTPUT) || DEFAULT_OUTPUT;
  applySizePreset();
  syncVariantButtons();
  setGenerateEnabled();
  updateDownloadHint();
}

registerCapabilityPlugin("image.generate.v1", {
  renderLaunch() {
    state.capabilityKey = "image.generate.v1";
    bindImageGenerateControls();
    showImageView("launch");
    setGenerateEnabled();
    scheduleQuote();
  },
  renderProgress(contract, data) {
    state.capabilityKey = "image.generate.v1";
    bindImageGenerateControls();
    showImageView("progress");
    startProgress(state.lastInput || {});
    state.jobId = jobIdOf(contract, data) || state.jobId;
    if (!state.pollTimer) pollJob();
  },
  renderReview(contract, data) {
    state.capabilityKey = "image.generate.v1";
    bindImageGenerateControls();
    const job = jobFromSurface(contract, data);
    stopPoll();
    finishProgress();
    showComplete(job, data || {});
  },
});
