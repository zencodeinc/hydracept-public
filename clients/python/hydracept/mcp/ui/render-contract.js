function liveTitle(contract, fallback) {
  return (contract && contract.title) || fallback;
}

function approvalRequestBody(approval) {
  const quote = (approval && approval.quote) || {};
  const prompt = (approval && approval.prompt) || {};
  const body = {};
  const domain = quote.domain || prompt.domain;
  if (domain) body.domain = domain;
  if (quote.registrant || prompt.registrant) body.registrant = quote.registrant || prompt.registrant;
  const first = quote.firstYearPriceUsd ?? prompt.firstYearPriceUsd;
  if (first != null) body.firstYearPriceUsd = first;
  const renewal = quote.renewalPriceUsd ?? prompt.renewalPriceUsd;
  if (renewal != null) body.renewalPriceUsd = renewal;
  const version =
    quote.porkbunAgreementVersion ||
    prompt.porkbunAgreementVersion ||
    quote.agreementVersion ||
    prompt.agreementVersion;
  if (version) body.porkbunAgreementVersion = version;
  if (body.domain || body.firstYearPriceUsd != null) {
    body.agreeToPorkbunRegistrationAgreement = true;
  }
  const max = quote.authorizedMaxAmount ?? prompt.authorizedMaxAmount;
  if (max != null) body.authorizedMaxAmount = max;
  const recipient = quote.recipientPorkbunUsername || prompt.recipientPorkbunUsername;
  if (recipient) body.recipientPorkbunUsername = recipient;
  return body;
}

function el(tag, attrs, children) {
  const node = document.createElement(tag);
  Object.entries(attrs || {}).forEach(([key, value]) => {
    if (value == null || value === false) return;
    if (key === "className") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "html") node.innerHTML = value;
    else if (key.slice(0, 2) === "on" && typeof value === "function") node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === "disabled") node.disabled = Boolean(value);
    else node.setAttribute(key, value === true ? "" : String(value));
  });
  (children || []).forEach((child) => {
    if (child == null) return;
    node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  });
  return node;
}

function isComplexSchema(schema) {
  if (!schema || typeof schema !== "object") return false;
  if (schema.widget === "json") return true;
  const type = schema.type;
  if (type === "object") return true;
  if (type === "array" && schema.items && (schema.items.type === "object" || schema.items.type === "array")) return true;
  return false;
}

function uiForField(name, schema, uiSchema) {
  const ui = (uiSchema && (uiSchema[name] || uiSchema.properties && uiSchema.properties[name])) || {};
  return { ...schema, ...ui };
}

function schemaOf(contract) {
  const data = (contract && contract.data) || {};
  return {
    input: data.inputSchema || {},
    ui: data.uiSchema || {},
  };
}

function fieldValue(field) {
  if (field && Object.prototype.hasOwnProperty.call(state.formValues, field.name)) {
    return state.formValues[field.name];
  }
  return field && field.value;
}

function collectFormBody(contract) {
  const data = (contract && contract.data) || {};
  const schema = data.inputSchema || {};
  const properties = (schema.properties || {});
  const body = {};
  Object.keys(properties).forEach((name) => {
    if (isSecretField(name)) return;
    if (Object.prototype.hasOwnProperty.call(state.formValues, name)) {
      body[name] = state.formValues[name];
    } else if (properties[name] && properties[name].default !== undefined) {
      body[name] = properties[name].default;
    }
  });
  (contract.fields || []).forEach((field) => {
    if (!field || field.readOnly || !field.name || isSecretField(field.name)) return;
    if (Object.prototype.hasOwnProperty.call(state.formValues, field.name)) {
      body[field.name] = state.formValues[field.name];
    } else if (field.value !== undefined) {
      body[field.name] = field.value;
    }
  });
  return body;
}

function validateAgainstSchema(body, schema) {
  const errors = [];
  const properties = (schema && schema.properties) || {};
  const required = schema && schema.required ? schema.required : [];
  required.forEach((name) => {
    if (isSecretField(name)) return;
    const value = body[name];
    if (value == null || value === "") errors.push(`${name} is required`);
  });
  Object.entries(properties).forEach(([name, spec]) => {
    const value = body[name];
    if (value == null || value === "") return;
    const type = spec && spec.type;
    if (type === "integer" && !Number.isInteger(Number(value))) errors.push(`${name} must be an integer`);
    if (type === "number" && !Number.isFinite(Number(value))) errors.push(`${name} must be a number`);
    if (typeof value === "string") {
      if (spec.minLength != null && value.length < spec.minLength) errors.push(`${name} is too short`);
      if (spec.maxLength != null && value.length > spec.maxLength) errors.push(`${name} is too long`);
    }
    const numeric = Number(value);
    if (Number.isFinite(numeric)) {
      if (spec.minimum != null && numeric < spec.minimum) errors.push(`${name} is below the minimum`);
      if (spec.maximum != null && numeric > spec.maximum) errors.push(`${name} is above the maximum`);
      if (spec.multipleOf != null && numeric % spec.multipleOf !== 0) errors.push(`${name} must be a multiple of ${spec.multipleOf}`);
    }
    if (Array.isArray(spec.enum) && spec.enum.length && !spec.enum.includes(value)) {
      errors.push(`${name} must be one of the allowed values`);
    }
  });
  return errors;
}

function renderFieldControl(field, schema, uiSchema, onChange) {
  const spec = uiForField(field.name, schema || {}, uiSchema || {});
  const label = el("label", { for: `field-${field.name}`, text: field.label || field.name });
  const wrap = el("div", {});
  wrap.appendChild(label);
  let control;
  const value = fieldValue(field);
  if (field.readOnly) {
    control = el("p", { className: field.name.toLowerCase().includes("id") ? "id-secondary" : "meta", text: value == null ? "" : String(value) });
  } else if (field.kind === "boolean" || spec.type === "boolean") {
    control = el("label", { className: "toggles" }, [
      el("input", {
        id: `field-${field.name}`,
        type: "checkbox",
        onchange: (event) => onChange(field.name, event.target.checked),
      }),
      " ",
      field.label || field.name,
    ]);
    control.querySelector("input").checked = Boolean(value);
  } else if ((field.options && field.options.length) || spec.enum) {
    const options = field.options || spec.enum;
    control = el("select", {
      id: `field-${field.name}`,
      onchange: (event) => onChange(field.name, event.target.value),
    }, options.map((option) => el("option", { value: option, text: String(option) })));
    control.value = value == null ? "" : String(value);
  } else if (spec.widget === "json" || isComplexSchema(spec) || field.kind === "object") {
    const serialized = typeof value === "string" ? value : JSON.stringify(value == null ? (spec.type === "array" ? [] : {}) : value, null, 2);
    control = el("textarea", {
      id: `field-${field.name}`,
      className: "json-editor",
      "aria-label": `${field.label || field.name} JSON`,
    });
    control.value = serialized || "";
    const err = el("p", { className: "field-error", hidden: true, id: `json-error-${field.name}` });
    const parseJson = (raw) => (raw.trim() ? JSON.parse(raw) : (spec.type === "array" ? [] : {}));
    control.addEventListener("input", () => {
      try {
        const parsed = parseJson(control.value);
        err.hidden = true;
        onChange(field.name, parsed);
      } catch (exc) {
        err.hidden = false;
        err.textContent = `JSON error: ${exc.message}`;
      }
    });
    if (value != null) {
      try {
        onChange(field.name, parseJson(control.value));
      } catch {
        /* wait for a valid edit */
      }
    }
    wrap.appendChild(control);
    wrap.appendChild(err);
    if (spec.description || field.description) {
      wrap.appendChild(el("p", { className: "meta", text: spec.description || field.description }));
    }
    return wrap;
  } else if (field.kind === "integer" || spec.type === "integer" || spec.type === "number") {
    control = el("input", {
      id: `field-${field.name}`,
      type: "number",
      value: value == null ? "" : String(value),
      oninput: (event) => onChange(field.name, event.target.value === "" ? "" : Number(event.target.value)),
    });
    if (spec.minimum != null) control.min = spec.minimum;
    if (spec.maximum != null) control.max = spec.maximum;
    if (spec.multipleOf != null) control.step = spec.multipleOf;
  } else if (field.kind === "array") {
    control = el("textarea", {
      id: `field-${field.name}`,
      oninput: (event) => onChange(field.name, event.target.value.split(/\r?\n|,/).map((part) => part.trim()).filter(Boolean)),
    });
    control.value = Array.isArray(value) ? value.join("\n") : (value || "");
  } else if (spec.widget === "textarea" || field.kind === "textarea") {
    control = el("textarea", {
      id: `field-${field.name}`,
      oninput: (event) => onChange(field.name, event.target.value),
    });
    control.value = value == null ? "" : String(value);
  } else {
    control = el("input", {
      id: `field-${field.name}`,
      type: "text",
      value: value == null ? "" : String(value),
      oninput: (event) => onChange(field.name, event.target.value),
    });
  }
  wrap.appendChild(control);
  if (spec.description) wrap.appendChild(el("p", { className: "meta", text: spec.description }));
  return wrap;
}

function renderRisk(contract) {
  const risk = (contract && contract.risk) || {};
  const items = [];
  if (risk.estimatedCostDisplay || risk.estimatedCostCents != null) {
    items.push(el("p", { text: `Expected cost: ${risk.estimatedCostDisplay || `${risk.estimatedCostCents} cents`}` }));
  }
  if (risk.requiredSecretScopes && risk.requiredSecretScopes.length) {
    items.push(el("p", { text: `Required connections: ${risk.requiredSecretScopes.join(", ")}` }));
  }
  if (risk.irreversibleEffects && risk.irreversibleEffects.length) {
    items.push(el("p", { text: `Irreversible: ${risk.irreversibleEffects.join(", ")}` }));
  }
  if (risk.requiresHumanApproval) items.push(el("p", { text: "Human approval is required before this can proceed." }));
  if (risk.dataSensitivity) items.push(el("p", { text: `Sensitivity: ${risk.dataSensitivity}` }));
  if (risk.requiredAssetApprovals && risk.requiredAssetApprovals.length) {
    items.push(el("p", { text: `Asset approvals: ${risk.requiredAssetApprovals.join(", ")}` }));
  }
  if (!items.length) return null;
  return el("div", { className: "risk-block" }, [el("strong", { text: "Review" }), ...items]);
}

function primaryDisabled(contract) {
  const schema = ((contract || {}).data || {}).inputSchema || {};
  const body = collectFormBody(contract || {});
  return validateAgainstSchema(body, schema).length > 0;
}

async function handleContractAction(action, contract, data) {
  const intent = action.intent || action.id;
  const body = collectFormBody(contract);
  const key = capabilityKeyOf(contract, data);
  const liveError = $("contract-error");
  if (liveError) {
    liveError.hidden = true;
    liveError.textContent = "";
  }
  try {
    if (intent === "cancel" || action.id === "cancel") {
      stopPoll();
      setChip("Hydracept");
      setStage("Cancelled", "No changes were made.");
      showNotice("Cancelled. No changes were made.");
      return;
    }
    if (action.id === "close" || intent === "stop") {
      stopPoll();
      setStage("Stopped watching", "The job keeps running. This panel is no longer polling.");
      showNotice("Stopped watching. The job keeps running. This does not cancel it.");
      return;
    }
    if (contract.surface === "project.connect" && (action.id === "connect" || intent === "apply")) {
      state.connectContext = {
        displayName: body.displayName || "",
        environment: body.environment || "",
      };
      if (typeof renderConnectWaiting === "function") {
        renderConnectWaiting({
          url: "",
          switchUrl: "",
          contract,
          status: "Opening your browser…",
          autoOpen: false,
        });
      }
      const result = structured(await callTool("hydracept_ui_connect_project", {
        displayName: state.connectContext.displayName,
        environment: state.connectContext.environment,
      }));
      paintIncoming(result);
      return;
    }
    if (contract.surface === "connection.resolve" && (action.id === "connect" || intent === "authorize")) {
      const url = (contract.data && (contract.data.connectUrl || contract.data.actionUrl)) || "";
      if (!url) throw new Error("No connection URL is available. Recheck, then try again.");
      openExternal(url);
      return;
    }
    if (contract.surface === "connection.resolve" && action.id === "recheck") {
      paintIncoming(await callTool("hydracept_ui_connection_recheck", { capability_key: key }));
      return;
    }
    if (contract.surface === "change.promote" && (action.id === "promote" || intent === "apply")) {
      const paths = (contract.data && contract.data.surfacePaths) || [];
      const path = body.surfacePath || paths[0];
      if (!path || contract.data.promoteEnabled === false) {
        throw new Error("No local project surface definition is available. Hydracept cloud does not write this repository.");
      }
      paintIncoming(await callTool("hydracept_ui_promote", { path }));
      return;
    }
    if (contract.surface === "authorization.preflight") {
      if (action.id === "authorize" || action.id === "continue" || intent === "authorize") {
        const jobId = (contract.data && contract.data.jobId) || state.jobId;
        const approval = contract.data && contract.data.approval;
        if (jobId && approval) {
          paintIncoming(await callTool("hydracept_ui_approve_job", {
            job_id: jobId,
            body: approvalRequestBody(approval),
          }));
          return;
        }
        const request = (contract.data && contract.data.request) || state.retainedRequest || { input: body };
        paintIncoming(await callTool("hydracept_ui_run", {
          capability_key: key,
          body: request,
        }));
        return;
      }
      if (action.id === "reject") {
        const jobId = (contract.data && contract.data.jobId) || state.jobId;
        if (!jobId) throw new Error("No job id is available to reject.");
        paintIncoming(await callTool("hydracept_ui_reject_job", { job_id: jobId }));
        return;
      }
    }
    if (contract.surface === "capability.launch" && (action.id === "run" || intent === "submit")) {
      const descriptor = (contract.data || {});
      const runnable = descriptor.workspaceRunnable || {};
      if (runnable.runnable === false) {
        paintIncoming(await callTool("hydracept_ui_connection_recheck", { capability_key: key }));
        return;
      }
      const approval = {
        ...(contract.risk || {}),
        ...(descriptor.approvalRequirements || {}),
      };
      const input = { input: body };
      state.retainedRequest = input;
      if (approval.requiresHumanApproval || (approval.irreversibleEffects || []).length) {
        const risk = { ...approval };
        if (state.quotedCost && !risk.estimatedCostDisplay) risk.estimatedCostDisplay = state.quotedCost;
        const fields = [
          { name: "capabilityKey", label: "Capability", kind: "string", value: key, readOnly: true, required: false },
        ];
        if (risk.estimatedCostDisplay) {
          fields.push({
            name: "estimatedCostDisplay",
            label: "Estimated maximum cost",
            kind: "string",
            value: String(risk.estimatedCostDisplay),
            readOnly: true,
            required: false,
          });
        }
        if ((risk.irreversibleEffects || []).length) {
          fields.push({
            name: "irreversibleEffects",
            label: "Irreversible effects",
            kind: "array",
            value: risk.irreversibleEffects,
            readOnly: true,
            required: false,
          });
        }
        if (risk.dataSensitivity) {
          fields.push({
            name: "dataSensitivity",
            label: "Sensitivity",
            kind: "string",
            value: risk.dataSensitivity,
            readOnly: true,
            required: false,
          });
        }
        paintIncoming({
          schemaVersion: INTERACTION_SCHEMA,
          surface: "authorization.preflight",
          title: liveTitle(contract, "Review before execution"),
          description: "Price is always visible. Execution is blocked only when approval policy or irreversible effects require it.",
          risk,
          fields,
          actions: [
            { id: "authorize", label: "Authorize", intent: "authorize", primary: true, style: "primary" },
            { id: "cancel", label: "Cancel", intent: "cancel" },
          ],
          data: { capabilityKey: key, request: input, approvalRequirements: approval },
        });
        return;
      }
      paintIncoming(await callTool("hydracept_ui_run", { capability_key: key, body: input }));
      return;
    }
    if (contract.surface === "artifact.review") {
      const jobId = state.jobId || jobIdOf(contract, data);
      if (action.id === "approve" || intent === "approve") {
        paintIncoming(await callTool("hydracept_ui_approve_job", {
          job_id: jobId,
          body: approvalRequestBody((contract.data && contract.data.approval) || {}),
        }));
        return;
      }
      if (action.id === "reject" || intent === "reject") {
        paintIncoming(await callTool("hydracept_ui_reject_job", { job_id: jobId }));
        return;
      }
      if (action.id === "select" || intent === "select") {
        paintIncoming(await callTool("hydracept_ui_select_variant", {
          job_id: jobId,
          artifact_id: body.selectedArtifactId || state.artifactId,
        }));
        return;
      }
      if (action.id === "use" || intent === "use") {
        await useReviewedArtifact(jobId, body.selectedArtifactId || state.artifactId || "", contract);
        return;
      }
      if (action.id === "download" || intent === "download") {
        paintIncoming(await callTool("hydracept_ui_download_artifact", {
          jobId: jobId,
          artifactId: body.selectedArtifactId || state.artifactId || "",
        }));
        return;
      }
    }
    if (contract.surface === "job.progress" && (action.id === "refresh" || intent === "recheck")) {
      const jobId = state.jobId || jobIdOf(contract, data);
      if (!jobId) throw new Error("No job id is available to refresh.");
      paintIncoming(await callTool("hydracept_ui_poll_job", { job_id: jobId }));
      return;
    }
    if (contract.surface === "job.progress" && (action.id === "receipt" || intent === "inspect")) {
      const jobId = state.jobId || jobIdOf(contract, data);
      if (!jobId) throw new Error("No job id is available for the receipt.");
      const receipt = structured(await callTool("hydracept_get_receipt", { job_id: jobId }));
      hideProductViews();
      showSurfaceRoot();
      const root = $("surface-root");
      root.replaceChildren();
      setChip("Receipt");
      setStage("Receipt", jobId);
      root.appendChild(el("pre", { className: "result-pane", id: "receipt-json", text: JSON.stringify(receipt, null, 2) }));
      root.appendChild(el("div", { className: "actions" }, [
        el("button", {
          type: "button",
          className: "secondary",
          text: "Back",
          onclick: () => paintIncoming(contract),
        }),
      ]));
      publishSize();
      return;
    }
    if (contract.surface === "job.progress" && action.id === "cancel-job") {
      const jobId = state.jobId || jobIdOf(contract, data);
      if (!jobId) throw new Error("No job id is available to cancel.");
      paintIncoming(await callTool("hydracept_ui_cancel_job", { job_id: jobId }));
      return;
    }
    throw new Error(`This panel cannot run “${action.label || action.id}” on ${contract.surface || "this surface"}.`);
  } catch (err) {
    if (liveError) {
      liveError.hidden = false;
      liveError.textContent = humanError(err);
    } else {
      showError(humanError(err));
    }
  }
}

function humanError(err) {
  return (err && err.message) || String(err || "Something went wrong");
}

async function useReviewedArtifact(jobId, artifactId, contract) {
  const typed = contract && contract.data && (contract.data.typedOutput || contract.data.output);
  let text =
    `Use this Hydracept output. Job ${jobId || ""}.` +
    (artifactId ? ` Artifact ${artifactId}.` : "") +
    " This was handed to chat via Use, not saved to disk. Download if you need a workspace file.";
  if (typed != null) {
    text += `\n\n${typeof typed === "string" ? typed : JSON.stringify(typed, null, 2)}`;
  }
  if (state.app && typeof state.app.sendMessage === "function") {
    const content = [{ type: "text", text }];
    const artifacts = (contract && contract.data && contract.data.artifacts) || [];
    const chosen =
      artifacts.find((item) => item && (item.id === artifactId || item.artifactId === artifactId)) ||
      artifacts[0];
    const media = chosen && (chosen.mediaType || "");
    if (jobId && media && String(media).startsWith("image/")) {
      try {
        const preview = structured(
          await callTool("hydracept_ui_artifact_preview", { jobId, artifactId: artifactId || "" }),
        );
        if (preview.bytesBase64 && Number(preview.byteLength || 0) < 750000) {
          content.push({
            type: "image",
            mimeType: preview.mediaType || "image/png",
            data: preview.bytesBase64,
          });
        }
      } catch {
        /* preview is optional for Use */
      }
    }
    await state.app.sendMessage({ role: "user", content });
    showNotice("Sent to chat. The agent can use this output now. Nothing was saved to disk.");
    return;
  }
  paintIncoming(
    await callTool("hydracept_ui_download_artifact", {
      jobId: jobId || "",
      artifactId: artifactId || "",
    }),
  );
}

function connectActionUrl(result, contract) {
  const action = (result && result.action) || (contract && contract.data && contract.data.action) || {};
  return action.url || (result && (result.actionUrl || result.connectUrl)) || (contract && contract.data && (contract.data.actionUrl || contract.data.connectUrl)) || "";
}

function switchAccountUrlFromConnect(connectUrl, sessionId) {
  try {
    const parsed = new URL(connectUrl);
    let sid = sessionId || "";
    if (!sid) {
      const parts = parsed.pathname.split("/").filter(Boolean);
      if (parts[0] === "connect" && parts[1]) sid = parts[1];
      if (!sid) sid = parsed.searchParams.get("bootstrapSessionId") || "";
    }
    if (!sid) return "";
    return `${parsed.origin}/v1/auth/browser-logout?next=${encodeURIComponent(`/connect/${sid}`)}`;
  } catch {
    return "";
  }
}

function connectFormValues(contract) {
  const stored = state.connectContext || {};
  const named = (name) => {
    const hit = (contract && (contract.fields || [])).find((field) => field && field.name === name);
    return (hit && hit.value) || stored[name] || "";
  };
  return {
    displayName: named("displayName"),
    environment: named("environment"),
  };
}

async function resumeConnect(contract) {
  const values = connectFormValues(contract);
  return structured(await callTool("hydracept_ui_connect_project", {
    displayName: values.displayName,
    environment: values.environment,
  }));
}

function scheduleConnectWaitPoll(contract) {
  stopPoll();
  state.pollTimer = window.setTimeout(async () => {
    try {
      paintIncoming(await resumeConnect(contract));
    } catch (err) {
      const status = $("connect-wait-status");
      if (status) status.textContent = humanError(err);
      else showError(humanError(err));
      scheduleConnectWaitPoll(contract);
    }
  }, 4000);
}

function revealConnectFallback(url) {
  const fallback = $("connect-open-fallback");
  const urlLine = $("connect-url-wrap");
  if (fallback) fallback.hidden = false;
  if (urlLine) urlLine.hidden = !url;
}

function cancelConnectWait() {
  stopPoll();
  state.waitingConnectUrl = "";
  setChip("Hydracept");
  setStage("Cancelled", "No changes were made.");
  showNotice("Cancelled. No changes were made.");
}

function renderConnectWaiting(opts) {
  const url = opts.url || "";
  const switchUrl = opts.switchUrl || "";
  const contract = opts.contract;
  const statusText = opts.status || (url ? "Opening your browser…" : "Starting…");
  hideProductViews();
  showSurfaceRoot();
  const root = $("surface-root");
  root.replaceChildren();
  setChip("Connect");
  setStage("Approve in your browser", "Finish in the window that opened. You don't need to name the project again.");
  state.waitingConnectUrl = url || state.waitingConnectUrl || "";
  const card = el("div", { className: "connect-wait", id: "connect-waiting" });
  card.appendChild(el("div", { className: "progress" }, [el("i", { id: "connect-progress-fill" })]));
  const waitStatus = el("p", { className: "meta", id: "connect-wait-status", text: statusText });
  card.appendChild(waitStatus);
  const urlWrap = el("p", { className: "connect-url", id: "connect-url-wrap", hidden: true });
  if (url) {
    urlWrap.appendChild(el("a", {
      href: url,
      id: "connect-url",
      text: url,
      target: "_blank",
      rel: "noopener noreferrer",
    }));
  }
  card.appendChild(urlWrap);
  const openAgain = async (event) => {
    if (!url) return false;
    waitStatus.textContent = "Opening your browser…";
    try {
      const opened = await openExternal(url);
      if (opened) {
        if (event) event.preventDefault();
        waitStatus.textContent = "Waiting for you to approve…";
        return true;
      }
    } catch (err) {
      waitStatus.textContent = humanError(err);
    }
    waitStatus.textContent = "Couldn't open the window. Use Open browser.";
    revealConnectFallback(url);
    return false;
  };
  const fallback = el("a", {
    href: url || "#",
    className: "button-link",
    id: "connect-open-fallback",
    text: "Open browser",
    target: "_blank",
    rel: "noopener noreferrer",
    hidden: true,
    onclick: openAgain,
  });
  card.appendChild(fallback);
  root.appendChild(card);
  const quiet = el("div", { className: "quiet-row" });
  if (url) {
    quiet.appendChild(el("button", {
      type: "button",
      className: "quiet-link",
      text: "Didn't open?",
      onclick: () => {
        revealConnectFallback(url);
        openAgain();
      },
    }));
  }
  if (switchUrl) {
    quiet.appendChild(el("button", {
      type: "button",
      className: "quiet-link",
      text: "Use a different account",
      onclick: async () => {
        waitStatus.textContent = "Opening account switch…";
        try {
          const opened = await openExternal(switchUrl);
          waitStatus.textContent = opened
            ? "Pick the GitHub or Google account, then approve."
            : "Couldn't open account switch. Use Didn't open? then switch on the page.";
          if (!opened) revealConnectFallback(url);
        } catch (err) {
          waitStatus.textContent = humanError(err);
        }
      },
    }));
  }
  quiet.appendChild(el("button", {
    type: "button",
    className: "quiet-link",
    text: "Cancel",
    onclick: cancelConnectWait,
  }));
  root.appendChild(quiet);
  publishSize();
  if (url && opts.autoOpen !== false) openAgain();
  if (contract) scheduleConnectWaitPoll(contract);
}

function renderConnectInteraction(result, contract) {
  const url = connectActionUrl(result, contract);
  if (state.waitingConnectUrl === url && url && $("connect-waiting")) {
    scheduleConnectWaitPoll(contract);
    return;
  }
  stopPoll();
  const sessionId = (result && (result.bootstrapSessionId || (result.action && result.action.sessionId)))
    || (contract && contract.data && (contract.data.bootstrapSessionId || (contract.data.action && contract.data.action.sessionId)))
    || "";
  const switchUrl = (contract && contract.data && contract.data.switchAccountUrl)
    || switchAccountUrlFromConnect(url, sessionId);
  renderConnectWaiting({
    url,
    switchUrl,
    contract,
    status: url ? "Opening your browser…" : "Waiting…",
  });
}

function renderTypedResult(value) {
  if (value == null) return el("p", { className: "meta", text: "No output." });
  if (typeof value === "string") return el("pre", { className: "result-pane", text: value });
  return el("pre", { className: "result-pane", text: JSON.stringify(value, null, 2) });
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    /* host may block clipboard */
  }
}

function renderInteractionContract(surface, contract, data) {
  hideProductViews();
  showSurfaceRoot();
  const root = $("surface-root");
  root.replaceChildren();
  const live = contract || { surface, title: surface, fields: [], actions: [], data: data || {} };
  const progressStatus = String(
    (live.data && live.data.status) ||
      (data && (data.status || data.state)) ||
      "",
  ).toLowerCase();
  const chips = {
    "project.connect": "Connect",
    "capability.launch": "Launch",
    "connection.resolve": "Connection",
    "authorization.preflight": "Authorize",
    "job.progress": (
      state.capabilityKey === "image.generate.v1" && !TERMINAL_JOB_STATES.includes(progressStatus)
        ? "Generating"
        : "Working"
    ),
    "artifact.review": "Ready",
    "change.promote": "Promote",
  };
  setChip(chips[surface] || "Hydracept");
  setStage(live.title || surface, live.description || "");
  (live.fields || []).forEach((field) => {
    if (field && field.value !== undefined && state.formValues[field.name] === undefined) {
      state.formValues[field.name] = field.value;
    }
  });
  const schemas = schemaOf(live);
  const onChange = (name, value) => {
    state.formValues[name] = value;
    const primary = root.querySelector("[data-primary='true']");
    if (primary) primary.disabled = primaryDisabled(live);
  };
  if (surface === "capability.launch" && schemas.input.properties) {
    Object.entries(schemas.input.properties).forEach(([name, spec]) => {
      if (isSecretField(name)) {
        return;
      }
      const field = { name, label: spec.title || name, kind: spec.type, value: spec.default };
      if (field.value !== undefined && state.formValues[name] === undefined) {
        state.formValues[name] = field.value;
      }
      root.appendChild(renderFieldControl(field, spec, schemas.ui, onChange));
    });
  } else {
    (live.fields || []).forEach((field) => {
      const spec = (schemas.input.properties || {})[field.name] || {};
      root.appendChild(renderFieldControl(field, spec, schemas.ui, onChange));
    });
  }
  const risk = renderRisk(live);
  if (risk) root.appendChild(risk);
  if (surface === "capability.launch") {
    const cost = el("p", { className: "meta", id: "generic-cost", text: "Quote appears next to Run when available." });
    root.appendChild(cost);
    const key = capabilityKeyOf(live, data);
    if (state.app && key) {
      callTool("hydracept_ui_quote", { capability_key: key, body: { input: collectFormBody(live) } })
        .then((quoted) => {
          const label = extractCost(structured(quoted));
          state.quotedCost = label || state.quotedCost;
          if (label) cost.textContent = `This run ${label}. Quote is not admission.`;
          else cost.textContent = "Quote is unavailable for this input. You can still run.";
        })
        .catch((err) => {
          cost.textContent = `Quote failed: ${humanError(err)}. You can still run.`;
        });
    }
  }
  if (surface === "connection.resolve") {
    root.appendChild(el("p", { className: "meta", text: "Provider credentials are never pasted into this panel." }));
    const url = live.data && (live.data.connectUrl || live.data.actionUrl);
    if (url) root.appendChild(el("p", { className: "id-secondary", id: "connect-url", text: url }));
  }
  if (surface === "change.promote") {
    const paths = (live.data && live.data.surfacePaths) || [];
    root.appendChild(el("p", { className: "meta", text: paths.length ? `Surface definition: ${paths.join(", ")}` : "No local surface definition found." }));
    const changes = (live.data && live.data.changes) || [];
    if (changes.length) {
      root.appendChild(el("p", { className: "meta", text: `Display-only changes: ${changes.join(", ")}` }));
    }
    root.appendChild(el("p", { className: "promote-note", text: "Hydracept cloud does not write this repository. Promotion runs through the project-local Hydracept authority." }));
  }
  if (surface === "authorization.preflight" && live.data && live.data.approval) {
    root.appendChild(el("pre", { className: "result-pane", text: JSON.stringify(live.data.approval, null, 2) }));
  }
  if (surface === "job.progress") {
    const status = String(
      (live.data && live.data.status) ||
        (data && (data.status || data.state)) ||
        fieldNamed(live, "status") ||
        "running",
    ).toLowerCase();
    const poll = (data && data.pollAfterSeconds) || (live.data && live.data.pollAfterSeconds);
    const err = (data && data.error) || (live.data && live.data.error);
    const errText = err && typeof err === "object" ? (err.message || err.code || "") : "";
    root.appendChild(el("p", { className: "meta", id: "generic-progress-status", text: `Status: ${status}` }));
    stopPoll();
    if (status === "succeeded" || status === "completed") {
      paintIncoming({
        ...(data || {}),
        ...(live.data || {}),
        schemaVersion: INTERACTION_SCHEMA,
        surface: "artifact.review",
        interaction: { ...(live || {}), surface: "artifact.review" },
      });
      return;
    }
    if (TERMINAL_JOB_STATES.includes(status) || (data && data.nextAction === "stop") || (live.data && live.data.nextAction === "stop")) {
      if (errText) root.appendChild(el("p", { className: "error", text: String(errText) }));
      else if (status === "succeeded" || status === "completed") {
        root.appendChild(el("p", { className: "meta", text: "This job succeeded. View the receipt, or review artifacts next." }));
      } else {
        root.appendChild(el("p", { className: "meta", text: "This job is no longer running." }));
      }
    } else {
      root.appendChild(el("p", { className: "meta", text: poll ? `Checking again in ${poll}s. This is not an ETA.` : "Waiting for the next status update. This is not an ETA." }));
      const wait = Number(poll || 4) * 1000;
      const jobId = state.jobId || jobIdOf(live, data);
      if (jobId) {
        state.jobId = jobId;
        state.pollTimer = window.setTimeout(async () => {
          try {
            paintIncoming(await callTool("hydracept_ui_poll_job", { job_id: jobId }));
          } catch (pollErr) {
            showError(humanError(pollErr));
          }
        }, wait);
      }
    }
  }
  if (surface === "artifact.review") {
    const artifacts = (live.data && live.data.artifacts) || (data && data.artifacts) || [];
    const typed = (live.data && live.data.typedOutput) || (data && (data.typedOutput || data.output));
    if (artifacts.length) {
      artifacts.forEach((artifact) => {
        root.appendChild(el("p", { className: "meta", text: artifact.label || artifact.filename || artifact.kind || "Artifact" }));
      });
    } else if (typed != null) {
      root.appendChild(renderTypedResult(typed));
      root.appendChild(el("button", {
        type: "button",
        className: "secondary",
        text: "Copy",
        onclick: () => copyText(typeof typed === "string" ? typed : JSON.stringify(typed, null, 2)),
      }));
    }
  }
  const actions = el("div", { className: "actions" });
  (live.actions || []).forEach((action) => {
    const primary = isPrimaryAction(action);
    const disabled = primary && surface === "capability.launch" && primaryDisabled(live);
    if (surface === "change.promote" && primary && live.data && live.data.promoteEnabled === false) {
      actions.appendChild(el("button", { type: "button", disabled: true, text: action.label || action.id }));
      return;
    }
    actions.appendChild(el("button", {
      type: "button",
      className: primary ? "" : "secondary",
      text: action.label || action.id,
      "data-primary": primary ? "true" : "false",
      disabled,
      onclick: () => handleContractAction(action, live, data),
    }));
  });
  root.appendChild(actions);
  root.appendChild(el("p", { className: "error", id: "contract-error", hidden: true, "aria-live": "polite" }));
  publishSize();
}
