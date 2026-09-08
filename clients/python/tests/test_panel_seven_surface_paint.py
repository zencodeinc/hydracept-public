"""Paint and click all seven Hydracept panel surfaces in a real DOM."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hydracept.mcp.interactions import SURFACE_IDS, build_interaction_surface

UI = Path(__file__).resolve().parents[1] / "hydracept" / "mcp" / "ui"


def _fixtures() -> dict[str, dict]:
    return {
        "project.connect": build_interaction_surface(
            "project.connect",
            {
                "projectId": "cpr_1",
                "displayName": "Arena",
                "environment": "development",
                "detectedRoot": "/repo",
            },
        ),
        "capability.launch": build_interaction_surface(
            "capability.launch",
            {
                "capability": {
                    "key": "text.general.fast.v1",
                    "displayName": "Fast text",
                    "description": "Generate text",
                    "inputSchema": {
                        "type": "object",
                        "required": ["messages", "apiKey"],
                        "properties": {
                            "messages": {"type": "array", "title": "Messages"},
                            "maxOutputTokens": {"type": "integer", "title": "Max output tokens"},
                            "apiKey": {"type": "string", "title": "API key"},
                        },
                    },
                }
            },
        ),
        "connection.resolve": build_interaction_surface(
            "connection.resolve",
            {
                "capabilityKey": "domain.register.v1",
                "provider": "Porkbun",
                "status": "missing",
                "connectUrl": "https://studio.example/connections?exact=1",
            },
        ),
        "authorization.preflight": build_interaction_surface(
            "authorization.preflight",
            {
                "capability": {
                    "key": "domain.register.v1",
                    "approvalRequirements": {
                        "requiresHumanApproval": True,
                        "dataSensitivity": "account",
                        "requiredAssetApprovals": ["registrant_contact"],
                        "irreversibleEffects": ["creates_registered_domain"],
                    },
                },
                "estimatedCostDisplay": "$10.37",
                "jobId": "job_d",
            },
        ),
        "job.progress": build_interaction_surface(
            "job.progress",
            {
                "jobId": "job_p",
                "capabilityKey": "text.translate.v1",
                "status": "running",
                "pollAfterSeconds": 4,
            },
        ),
        "artifact.review": build_interaction_surface(
            "artifact.review",
            {
                "jobId": "job_r",
                "capabilityKey": "text.translate.v1",
                "typedOutput": {"text": "bonjour"},
            },
        ),
        "change.promote": build_interaction_surface(
            "change.promote",
            {
                "projectId": "cpr_1",
                "validationStatus": "passed",
                "surfacePaths": [
                    "tools/hydracept/surfaces/hero.json",
                    "tools/hydracept/surfaces/icon.json",
                ],
                "promoteEnabled": True,
            },
        ),
    }


def test_all_seven_fixtures_are_full_contracts() -> None:
    fixtures = _fixtures()
    assert tuple(fixtures) == SURFACE_IDS
    for surface_id, contract in fixtures.items():
        assert contract["schemaVersion"] == "hydracept.interaction.v1"
        assert contract["surface"] == surface_id
        assert contract["title"]
        assert contract["actions"]
        assert contract["actions"][0]["primary"] is True
        assert contract["actions"][0]["style"] == "primary"


def _harness_html(fixtures: dict[str, dict]) -> str:
    shell = (UI / "shell.html").read_text(encoding="utf-8")
    sources = "\n".join(
        (UI / name).read_text(encoding="utf-8")
        for name in ("panel-core.js", "render-contract.js", "plugin-image-generate.js")
    )
    boot = f"""
window.__FIXTURES = {json.dumps(fixtures)};
window.__calls = [];
window.__messages = [];
window.__openLinks = [];
window.__state = state;
state.app = {{
  callServerTool: async (params) => {{
    const name = params && params.name;
    const args = (params && params.arguments) || {{}};
    window.__calls.push({{ name, arguments: args }});
    if (name === "hydracept_get_receipt") {{
      return {{ structuredContent: {{ receiptId: "rcpt_1", jobId: args.job_id }} }};
    }}
    if (name === "hydracept_ui_poll_job") {{
      return {{
        structuredContent: {{
          schemaVersion: "hydracept.interaction.v1",
          surface: "job.progress",
          title: "Hydracept job",
          fields: [],
          actions: [],
          data: {{ jobId: args.job_id, status: "running", pollAfterSeconds: 4 }},
        }},
      }};
    }}
    if (name === "hydracept_ui_cancel_job") {{
      return {{
        structuredContent: {{
          schemaVersion: "hydracept.interaction.v1",
          surface: "job.progress",
          title: "Hydracept job",
          fields: [],
          actions: [{{ id: "receipt", label: "View receipt", intent: "inspect", primary: true, style: "primary" }}],
          data: {{ jobId: args.job_id, status: "canceled" }},
        }},
      }};
    }}
    if (name === "hydracept_ui_download_artifact") {{
      return {{ structuredContent: {{ path: "/tmp/out.txt", filename: "out.txt", note: "saved" }} }};
    }}
    if (name === "hydracept_ui_promote") {{
      return {{ structuredContent: {{ applied: true, path: args.path, note: "promoted" }} }};
    }}
    if (name === "hydracept_ui_connect_project") {{
      return {{ structuredContent: {{ ok: true, displayName: args.displayName, environment: args.environment }} }};
    }}
    if (name === "hydracept_ui_quote") {{
      return {{ structuredContent: {{ pricing: {{ quote: {{ customerTotal: {{ display: "$0.01" }} }} }} }} }};
    }}
    if (name === "hydracept_ui_run") {{
      return {{
        structuredContent: {{
          schemaVersion: "hydracept.interaction.v1",
          surface: "job.progress",
          title: "Hydracept job",
          fields: [],
          actions: [],
          data: {{ jobId: "job_run", status: "running", pollAfterSeconds: 4 }},
        }},
      }};
    }}
    if (name === "hydracept_ui_connection_recheck") {{
      return {{
        structuredContent: {{
          schemaVersion: "hydracept.interaction.v1",
          surface: "connection.resolve",
          title: "Connect a provider",
          fields: [],
          actions: [],
          data: {{ capabilityKey: args.capability_key, connectUrl: "https://studio.example/hydrated" }},
        }},
      }};
    }}
    return {{ structuredContent: {{ ok: true }} }};
  }},
  sendMessage: async (msg) => {{ window.__messages.push(msg); }},
  sendSizeChanged: () => {{}},
  openLink: (url) => {{ window.__openLinks.push(url); }},
}};
window.__snapshot = function() {{
  const root = document.getElementById("surface-root");
  return {{
    surface: state.surface,
    capabilityKey: state.capabilityKey,
    jobId: state.jobId,
    chip: document.getElementById("family-label") && document.getElementById("family-label").textContent,
    title: document.getElementById("stage-title") && document.getElementById("stage-title").textContent,
    error: (document.querySelector("#surface-root .unsupported") || {{}}).textContent || "",
    launchHidden: Boolean(document.getElementById("launch-view").hidden),
    primary: Array.from(document.querySelectorAll("[data-primary='true']")).map((n) => n.textContent),
    buttons: Array.from(document.querySelectorAll("#surface-root button")).map((n) => n.textContent),
    fieldIds: Array.from(document.querySelectorAll("#surface-root [id^='field-']")).map((n) => n.id),
    risk: Array.from(document.querySelectorAll(".risk-block p")).map((n) => n.textContent),
    typed: Boolean(document.querySelector("#surface-root .result-pane")),
    connectUrl: (document.getElementById("connect-url") || {{}}).textContent || "",
    receipt: Boolean(document.getElementById("receipt-json")),
    notice: (document.querySelector("#surface-root .meta") || {{}}).textContent || "",
    contractError: (document.getElementById("contract-error") || {{}}).textContent || "",
    cost: (document.getElementById("generic-cost") || {{}}).textContent || "",
    quotedCost: state.quotedCost || "",
    runDisabled: Boolean((document.querySelector("[data-primary='true']") || {{}}).disabled),
    progressHidden: Boolean(document.getElementById("progress-view").hidden),
    genericStatus: (document.getElementById("generic-progress-status") || {{}}).textContent || "",
  }};
}};
window.__paintSurface = function(id) {{
  window.__calls = [];
  window.__messages = [];
  paintIncoming(window.__FIXTURES[id]);
  const snap = window.__snapshot();
  stopPoll();
  return snap;
}};
window.__stopPoll = stopPoll;
window.__click = async function(label) {{
  window.__calls = [];
  window.__messages = [];
  const btn = Array.from(document.querySelectorAll("button")).find((n) => n.textContent === label);
  if (!btn) return {{ missing: label, snapshot: window.__snapshot() }};
  btn.click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  const out = {{
    calls: window.__calls.slice(),
    messages: window.__messages.slice(),
    snapshot: window.__snapshot(),
  }};
  stopPoll();
  return out;
}};
"""
    html = shell.replace("<!--EXT_APPS_VENDOR-->", "")
    html = html.replace("<script><!--PANEL_JS--></script>", f"<script>{sources}\n{boot}</script>")
    return html


def _run_node_jsdom(html: str, tmp_path: Path) -> dict:
    import shutil
    import subprocess

    node = shutil.which("node")
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if node is None or npm is None:
        pytest.skip("node/npm required to paint panel surfaces")
    page_path = tmp_path / "panel.html"
    page_path.write_text(html, encoding="utf-8")
    harness = tmp_path / "paint.mjs"
    harness.write_text(
        r"""
import { JSDOM } from "jsdom";
import fs from "fs";

const html = fs.readFileSync(process.argv[2], "utf8");
const ids = JSON.parse(process.argv[3]);
const dom = new JSDOM(html, {
  url: "https://panel.local/app.html",
  runScripts: "dangerously",
  pretendToBeVisual: true,
});
const win = dom.window;
if (typeof win.matchMedia !== "function") {
  win.matchMedia = () => ({ matches: true, addListener() {}, addEventListener() {}, removeEventListener() {} });
}

const painted = {};
for (const id of ids) {
  painted[id] = win.__paintSurface(id);
}

const tokenLaunch = win.__paintSurface("capability.launch");
const canceled = (() => {
  win.paintIncoming({
    schemaVersion: "hydracept.interaction.v1",
    surface: "job.progress",
    title: "Hydracept job",
    fields: [{ name: "jobId", label: "Job", value: "job_c", readOnly: true }],
    actions: [
      { id: "refresh", label: "Refresh", intent: "recheck" },
      { id: "receipt", label: "View receipt", intent: "inspect", primary: true, style: "primary" },
    ],
    data: { jobId: "job_c", status: "canceled" },
  });
  return win.__snapshot();
})();

win.__paintSurface("job.progress");
const cancelClick = await win.__click("Cancel job");
win.__paintSurface("job.progress");
const refreshClick = await win.__click("Refresh");
win.paintIncoming({
  schemaVersion: "hydracept.interaction.v1",
  surface: "job.progress",
  title: "Hydracept job",
  fields: [{ name: "jobId", label: "Job", value: "job_c", readOnly: true }],
  actions: [
    { id: "refresh", label: "Refresh", intent: "recheck" },
    { id: "receipt", label: "View receipt", intent: "inspect", primary: true, style: "primary" },
  ],
  data: { jobId: "job_c", status: "canceled", receiptId: "rcpt_1" },
});
const receiptClick = await win.__click("View receipt");
win.__paintSurface("artifact.review");
const useClick = await win.__click("Use");
win.__paintSurface("artifact.review");
const downloadClick = await win.__click("Download");
win.__paintSurface("change.promote");
const promoteClick = await win.__click("Promote");
win.__paintSurface("capability.launch");
await new Promise((resolve) => setTimeout(resolve, 0));
const quotedLaunch = {
  cost: (win.document.getElementById("generic-cost") || {}).textContent || "",
  quotedCost: win.__state.quotedCost || "",
  runDisabled: Boolean((win.document.querySelector("[data-primary='true']") || {}).disabled),
};
const messagesEditor = win.document.getElementById("field-messages");
if (messagesEditor) {
  messagesEditor.value = JSON.stringify([{ role: "user", content: "hi" }]);
  messagesEditor.dispatchEvent(new win.Event("input"));
}
win.__state.formValues.apiKey = "sk-should-not-submit";
const quotedLaunchReady = {
  runDisabled: Boolean((win.document.querySelector("[data-primary='true']") || {}).disabled),
};
const runClick = await win.__click("Run");
const beforeQuote = win.__paintSurface("project.connect");
win.paintIncoming({ pricing: { quote: { customerTotal: { display: "$0.01" } } } });
const quoteEcho = win.__snapshot();
win.paintIncoming({
  schemaVersion: "hydracept.interaction.v1",
  surface: "connection.resolve",
  title: "Connect a provider",
  fields: [],
  actions: [{ id: "connect", label: "Connect provider", intent: "authorize", primary: true, style: "primary" }],
  data: { acceptsSecrets: false },
});
const emptyConnect = await win.__click("Connect provider");
win.paintIncoming({
  schemaVersion: "hydracept.interaction.v1",
  surface: "capability.launch",
  title: "Image",
  fields: [],
  actions: [{ id: "run", label: "Run", intent: "submit", primary: true, style: "primary" }],
  data: { capabilityKey: "image.generate.v1" },
});
const image = win.__snapshot();
win.paintIncoming({
  schemaVersion: "hydracept.interaction.v1",
  surface: "capability.launch",
  title: "Register domain",
  fields: [],
  actions: [{ id: "run", label: "Run", intent: "submit", primary: true, style: "primary" }],
  risk: { irreversibleEffects: ["creates_registered_domain"] },
  data: {
    capabilityKey: "domain.register.v1",
    inputSchema: { type: "object", properties: {} },
    approvalRequirements: { irreversibleEffects: ["creates_registered_domain"] },
  },
});
await new Promise((resolve) => setTimeout(resolve, 0));
const domainQuoted = win.__state.quotedCost || "";
const preflightFromQuote = await win.__click("Run");
win.__paintSurface("project.connect");
win.__state.formValues.displayName = "Edited Arena";
win.__state.formValues.environment = "staging";
win.paintIncoming({
  schemaVersion: "hydracept.interaction.v1",
  surface: "project.connect",
  title: "Connect this project",
  fields: [
    { name: "displayName", value: "Arena" },
    { name: "environment", value: "development" },
  ],
  actions: [],
  data: { status: "interaction_required", action: { url: "https://studio.example/activate" } },
});
await new Promise((resolve) => setTimeout(resolve, 0));
const connectSetupUrl = (win.document.getElementById("connect-url") || {}).textContent || "";
const connectWaiting = Boolean(win.document.getElementById("connect-waiting"));
const connectOpenLinks = win.__openLinks.slice();
const connectButtons = Array.from(win.document.querySelectorAll("#surface-root button")).map((n) => n.textContent);
win.__stopPoll();
win.paintIncoming({
  schemaVersion: "hydracept.interaction.v1",
  surface: "job.progress",
  title: "Hydracept job",
  fields: [{ name: "jobId", label: "Job", value: "job_img", readOnly: true }],
  actions: [
    { id: "receipt", label: "View receipt", intent: "inspect", primary: true, style: "primary" },
  ],
  data: { jobId: "job_img", status: "canceled", capabilityKey: "image.generate.v1" },
});
const imageCanceled = win.__snapshot();
win.__stopPoll();

process.stdout.write(JSON.stringify({
  painted,
  tokenLaunch,
  canceled,
  cancelClick,
  refreshClick,
  receiptClick,
  useClick,
  downloadClick,
  promoteClick,
  quotedLaunch,
  quotedLaunchReady,
  runClick,
  beforeQuote,
  quoteEcho,
  emptyConnect,
  image,
  domainQuoted,
  preflightFromQuote,
  connectSetupUrl,
  connectWaiting,
  connectOpenLinks,
  connectButtons,
  imageCanceled,
}));
""",
        encoding="utf-8",
    )
    npm_prefix = tmp_path / "node_modules"
    if not (npm_prefix / "jsdom").exists():
        install = subprocess.run(
            [npm, "install", "jsdom@26", "--no-fund", "--no-audit"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if install.returncode != 0:
            pytest.skip(f"jsdom install failed: {install.stderr[-400:]}")
    painted = subprocess.run(
        [node, str(harness), str(page_path), json.dumps(list(SURFACE_IDS))],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if painted.returncode != 0:
        pytest.fail(painted.stderr or painted.stdout or "node paint harness failed")
    try:
        return json.loads(painted.stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(f"paint harness did not return JSON: {painted.stdout[:500]} {exc}")


def test_panel_paints_and_clicks_all_seven_surfaces(tmp_path: Path) -> None:
    fixtures = _fixtures()
    html = _harness_html(fixtures)
    result = _run_node_jsdom(html, tmp_path)
    painted = result["painted"]
    expected = {
        "project.connect": {"chip": "Connect", "title": "Connect this project"},
        "capability.launch": {"chip": "Launch", "title": "Fast text"},
        "connection.resolve": {"chip": "Connection", "title": "Connect a provider"},
        "authorization.preflight": {"chip": "Authorize", "title": "Review before execution"},
        "job.progress": {"chip": "Working", "title": "Hydracept job"},
        "artifact.review": {"chip": "Ready", "title": "Review generated artifacts"},
        "change.promote": {"chip": "Promote", "title": "Promote approved changes"},
    }
    for surface_id in SURFACE_IDS:
        snap = painted[surface_id]
        assert snap["error"] == "", snap
        assert snap["surface"] == surface_id, snap
        assert snap["launchHidden"] is True, snap
        assert snap["chip"] == expected[surface_id]["chip"], snap
        assert snap["title"] == expected[surface_id]["title"], snap
        assert snap["primary"], snap
        if surface_id == "connection.resolve":
            assert "https://studio.example/connections?exact=1" in snap["connectUrl"]
        if surface_id == "artifact.review":
            assert snap["typed"] is True
        if surface_id == "job.progress":
            assert snap["jobId"] == "job_p"
            assert "Cancel job" in snap["buttons"]
            assert snap["buttons"].count("Stop watching") == 1
        if surface_id == "authorization.preflight":
            joined = " ".join(snap["risk"])
            assert "account" in joined
            assert "creates_registered_domain" in joined
        if surface_id == "change.promote":
            assert "field-surfacePath" in snap["fieldIds"]

    token = result["tokenLaunch"]
    assert "field-maxOutputTokens" in token["fieldIds"], token
    assert "field-apiKey" not in token["fieldIds"], token

    quoted = result["quotedLaunch"]
    assert "$0.01" in quoted["cost"], quoted
    assert quoted["quotedCost"] == "$0.01", quoted
    assert quoted["runDisabled"] is True, quoted
    assert result["quotedLaunchReady"]["runDisabled"] is False, result["quotedLaunchReady"]

    canceled = result["canceled"]
    assert "View receipt" in canceled["buttons"]
    assert "Cancel job" not in canceled["buttons"]
    assert canceled["buttons"].count("Stop watching") == 0

    assert result["cancelClick"]["calls"][0]["name"] == "hydracept_ui_cancel_job"
    assert result["cancelClick"]["calls"][0]["arguments"]["job_id"] == "job_p"
    assert result["refreshClick"]["calls"][0]["name"] == "hydracept_ui_poll_job"
    assert result["receiptClick"]["calls"][0]["name"] == "hydracept_get_receipt"
    assert result["receiptClick"]["snapshot"]["receipt"] is True

    assert result["useClick"]["messages"], result["useClick"]
    assert result["useClick"]["calls"] == []
    assert "Sent to chat" in result["useClick"]["snapshot"]["notice"]
    assert result["downloadClick"]["calls"][0]["name"] == "hydracept_ui_download_artifact"

    assert result["promoteClick"]["calls"][0]["name"] == "hydracept_ui_promote"
    assert result["promoteClick"]["calls"][0]["arguments"]["path"] == (
        "tools/hydracept/surfaces/hero.json"
    )

    run = result["runClick"]["calls"][0]
    assert run["name"] == "hydracept_ui_run", result["runClick"]
    submitted = ((run["arguments"] or {}).get("body") or {}).get("input") or {}
    assert "apiKey" not in submitted, submitted
    assert submitted.get("maxOutputTokens") is None or "apiKey" not in submitted

    assert result["quoteEcho"]["error"] == "", result["quoteEcho"]
    assert result["quoteEcho"]["surface"] == result["beforeQuote"]["surface"]
    assert "connection URL" in (result["emptyConnect"]["snapshot"]["contractError"] or "")

    image = result["image"]
    assert image["error"] == "", image
    assert image["launchHidden"] is False
    assert image["capabilityKey"] == "image.generate.v1"
    assert image["surface"] == "capability.launch"

    assert result["domainQuoted"] == "$0.01", result["domainQuoted"]
    preflight = result["preflightFromQuote"]["snapshot"]
    assert preflight["surface"] == "authorization.preflight", preflight
    joined = " ".join(preflight.get("risk") or [])
    assert "$0.01" in joined or any("$0.01" in str(value) for value in preflight.values()), preflight

    assert "https://studio.example/activate" in result["connectSetupUrl"]
    assert result["connectWaiting"] is True
    assert any(
        (isinstance(item, dict) and item.get("url") == "https://studio.example/activate")
        or item == "https://studio.example/activate"
        for item in result["connectOpenLinks"]
    ), result["connectOpenLinks"]
    assert "I've completed setup" not in result["connectButtons"]
    assert "Didn't open?" in result["connectButtons"]

    image_canceled = result["imageCanceled"]
    assert image_canceled["error"] == "", image_canceled
    assert image_canceled["launchHidden"] is True, image_canceled
    assert image_canceled["progressHidden"] is True, image_canceled
    assert image_canceled["chip"] == "Working", image_canceled
    assert "canceled" in image_canceled["genericStatus"], image_canceled
    assert "View receipt" in image_canceled["buttons"], image_canceled
