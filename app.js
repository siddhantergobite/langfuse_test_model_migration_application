(function () {
  "use strict";

  var root = document.getElementById("app");
  var state = {
    tab: "overview", overview: null, apps: [], activity: [], evaluation: null,
    selected: [], detail: null, rag: null, ragError: null, ragCapture: null, ragEvaluation: null,
    toast: null, oneTimeKey: null, busy: false
  };
  var DEFAULT_EVAL_TOOLS = [{
    type: "function",
    function: {
      name: "calculate_budget",
      description: "Calculate the remaining budget after expenses.",
      parameters: {
        type: "object",
        properties: {
          total_budget: {type: "number"},
          expenses: {type: "number"}
        },
        required: ["total_budget", "expenses"],
        additionalProperties: false
      }
    }
  }];
  var nav = [
    ["overview", "◈", "Overview"],
    ["apps", "▦", "Applications"],
    ["routes", "⇄", "Model routes"],
    ["evaluation", "◷", "Evaluations"],
    ["activity", "≋", "Request activity"]
  ];
  var titles = {
    overview: "Overview", apps: "Connected applications", routes: "Model routes",
    evaluation: "Model evaluation", activity: "Request activity"
  };

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char];
    });
  }
  function fmt(value, digits) {
    if (value == null || value === "") return "—";
    return Number(value).toLocaleString(undefined, {maximumFractionDigits: digits == null ? 2 : digits});
  }
  function percent(value) { return value == null ? "—" : Math.round(Number(value) * 100) + "%"; }
  function api(url, options) {
    return fetch(url, options || {}).then(function (response) {
      return response.text().then(function (raw) {
        var data;
        try { data = JSON.parse(raw); }
        catch (_) { throw new Error("The server returned HTTP " + response.status + ". Check the console running demo.py."); }
        if (!response.ok) {
          var detail = data.error;
          throw new Error(typeof detail === "string" ? detail : (detail && detail.message) || "Request failed.");
        }
        return data;
      });
    });
  }
  function providerName(id) {
    var item = ((state.overview && state.overview.providers) || []).find(function (p) { return p.id === id; });
    return item ? item.name : id;
  }
  function providerOptions(selected) {
    return ((state.overview && state.overview.providers) || []).map(function (p) {
      var suffix = p.configured ? " · ready" : " · not configured";
      return '<option value="' + esc(p.id) + '"' + (p.id === selected ? " selected" : "") +
        (!p.configured && p.id !== selected ? " disabled" : "") + '>' + esc(p.name + suffix) + "</option>";
    }).join("");
  }
  function routeStatus(app) {
    var route = (app.routes || []).find(function (r) { return r.is_default; }) || (app.routes || [])[0];
    if (!app.active) return '<span class="chip off">Paused</span>';
    if (!route || !route.enabled) return '<span class="chip off">Route disabled</span>';
    var provider = ((state.overview && state.overview.providers) || []).find(function (p) { return p.id === route.provider; });
    if (!provider || !provider.configured) return '<span class="chip off">Provider needs setup</span>';
    if (!app.has_api_key) return '<span class="chip off">Create app key</span>';
    return '<span class="chip live">Ready to connect</span>';
  }
  function card(title, body, extra) {
    return '<section class="card ' + (extra || "") + '"><h2 class="section-title">' + title + "</h2>" + body + "</section>";
  }
  function stat(label, value, note) {
    return '<section class="card stat-card"><div class="stat-label">' + esc(label) +
      '</div><div class="stat-value">' + esc(value) + '</div><div class="stat-note">' + esc(note || "") + "</div></section>";
  }
  function empty(message) { return '<div class="empty">' + esc(message) + "</div>"; }
  function button(text, action, cls, extra) {
    return '<button class="btn ' + (cls || "") + '" data-action="' + esc(action) + '"' +
      (extra || "") + ">" + esc(text) + "</button>";
  }
  function pageHead(title, description, action) {
    return '<div class="page-head"><div><h1>' + esc(title) + "</h1><p>" + esc(description) +
      '</p></div>' + (action || "") + "</div>";
  }
  function integrationSnippet(app) {
    var route = (app.routes || []).find(function (r) { return r.is_default; }) || (app.routes || [])[0];
    var alias = route ? route.requested_model : "your-existing-model-id";
    return [
      "from openai import OpenAI",
      "",
      "client = OpenAI(",
      "    api_key=\"<" + app.id + "-gateway-key>\",",
      "    base_url=\"" + ((state.overview && state.overview.gateway_base_url) || "http://127.0.0.1:5001/v1") + "\",",
      ")",
      "",
      "response = client.chat.completions.create(",
      "    model=\"" + alias + "\",  # keep the model name your app already sends",
      "    messages=[...],  # prompts and rules stay in the child app",
      ")"
    ].join("\n");
  }
  function renderShell() {
    var navHtml = nav.map(function (item) {
      return '<button class="' + (state.tab === item[0] ? "active" : "") + '" data-tab="' + item[0] +
        '"><span class="nav-icon">' + item[1] + "</span>" + item[2] + "</button>";
    }).join("");
    var configured = state.overview && state.overview.langfuse_configured;
    root.innerHTML = '<div class="shell"><aside class="sidebar"><div class="brand"><div class="brand-mark">P</div>' +
      '<div><div class="brand-title">Parent System</div><div class="brand-sub">Model control plane</div></div></div>' +
      '<div class="nav-label">Workspace</div><nav class="nav">' + navHtml + "</nav>" +
      '<div class="side-foot"><span class="connection-dot ' + (configured ? "" : "off") + '"></span>Langfuse ' +
      (configured ? "connected" : "not configured") + '<div style="margin-top:8px">Local prototype · API calls stay on this machine</div></div></aside>' +
      '<div class="main"><header class="topbar"><div><div class="eyebrow">Parent System</div><div class="top-title">' +
      esc(titles[state.tab] || "Overview") + '</div></div><div class="top-actions">' +
      '<span class="status-pill ' + (configured ? "good" : "warn") + '"><span class="connection-dot ' +
      (configured ? "" : "off") + '"></span>Langfuse ' + (configured ? "ready" : "setup needed") + "</span>" +
      '<button class="btn secondary" data-action="refresh">Refresh</button></div></header>' +
      '<main class="content" id="content">' + (state.busy ? '<div class="notice">Working…</div>' : "") +
      (state.toast ? '<div class="notice ' + (state.toast.error ? "error" : "") + '">' + esc(state.toast.text) + "</div>" : "") +
      (state.loading ? '<div class="card">Loading workspace…</div>' : renderCurrentPage()) +
      '<div class="footnote">Prototype boundary: connect child requests to this endpoint once. This system preserves request instructions and routes the model field.</div></main></div></div>' +
      (state.oneTimeKey ? renderKeyModal() : "");
  }
  function renderCurrentPage() {
    if (state.tab === "apps") return renderApps();
    if (state.tab === "routes") return renderRoutes();
    if (state.tab === "evaluation") return renderEvaluation();
    if (state.tab === "activity") return renderActivity();
    return renderOverview();
  }
  function renderOverview() {
    if (!state.overview) return '<div class="card">Loading overview…</div>';
    var overview = state.overview;
    var routeRows = [];
    state.apps.forEach(function (app) {
      (app.routes || []).forEach(function (route) {
        routeRows.push('<tr><td><strong>' + esc(app.name) + '</strong><div class="muted">' + esc(app.category) +
          '</div></td><td><code>' + esc(route.requested_model) + '</code></td><td><span class="arrow">→</span></td><td><code>' +
          esc(route.upstream_model) + '</code><div class="muted">' + esc(providerName(route.provider)) + '</div></td><td>' +
          routeStatus(app) + '</td></tr>');
      });
    });
    var providers = overview.providers.map(function (p) {
      return '<div class="provider-card"><div class="row"><strong>' + esc(p.name) + '</strong><span class="chip ' +
        (p.configured ? "live" : "off") + '">' + (p.configured ? "Configured" : "No credentials") + '</span></div>' +
        '<div class="small muted">' + esc(p.base_url || "Add provider credentials in .env") + "</div></div>";
    }).join("");
    var appsPreview = state.apps.slice(0, 3).map(function (app) {
      var route = (app.routes || []).find(function (r) { return r.is_default; }) || (app.routes || [])[0];
      return '<div class="row wrap" style="padding:9px 0;border-bottom:1px solid var(--line)"><div><strong>' +
        esc(app.name) + '</strong><div class="small muted">' + esc(app.category) + "</div></div><div>" +
        (route ? '<span class="route-model">' + esc(route.requested_model) + " → " + esc(route.upstream_model) + "</span>" : "No route") +
        "</div></div>";
    }).join("");
    var langfuseLink = state.evaluation && state.evaluation.langfuse_trace_url_base ?
      '<a href="' + esc(state.evaluation.langfuse_trace_url_base.replace("?peek=", "")) + '" target="_blank" rel="noreferrer">Open Langfuse ↗</a>' :
      '<span class="muted">Set LANGFUSE_HOST and project keys in .env to link traces.</span>';
    return pageHead("Your model control plane", "Manage model routing across different AI apps while leaving their prompts, guardrails, and business rules where they are.") +
      '<section class="hero"><div><h2>One route to manage. App logic stays app-owned.</h2><p>Each connected app keeps sending its existing model ID. The parent maps that ID to an approved provider and target model, then records request metrics through Langfuse.</p></div><div class="hero-tag">Prompts preserved · Models centrally routed</div></section>' +
      '<div class="grid stats">' +
      stat("Connected apps", overview.apps, "Apps registered in this workspace") +
      stat("Model routes", overview.routes, "Active app-to-model mappings") +
      stat("Requests today", overview.requests_today, "Requests through the parent endpoint") +
      stat("Success rate", percent(overview.success_rate), overview.avg_latency_ms == null ? "No gateway traffic yet" : "Average " + fmt(overview.avg_latency_ms) + " ms") +
      "</div>" +
      '<div class="grid two">' +
      card("Model routes", routeRows.length ? '<div class="table-wrap"><table class="table"><thead><tr><th>Application</th><th>App sends</th><th></th><th>Parent routes to</th><th>Status</th></tr></thead><tbody>' + routeRows.slice(0, 8).join("") + "</tbody></table></div>" : empty("Add an app and route a model to get started.")) +
      card("Provider connections", '<div class="provider-row">' + providers + "</div><div class=\"divider\"></div><div class=\"row\"><span class=\"small\">Langfuse tracing and evaluation</span>" + langfuseLink + "</div>") +
      card("Connected applications", (appsPreview || empty("No apps connected yet.")) + '<div class="divider"></div>' + button("Manage applications", "tab-apps", "secondary")) +
      card("Connect an app once", '<div class="code-title">OpenAI-compatible Python client</div><pre class="code">' +
        esc(integrationSnippet(state.apps[0] || {id:"your-app", routes:[]})) +
        '</pre><div class="notice warn">A one-time endpoint or network-routing change is required if the app currently calls a provider directly. No prompt or guardrail rewrite is needed.</div>') +
      "</div>";
  }
  function renderApps() {
    var cards = state.apps.map(function (app) {
      var routes = (app.routes || []).map(function (route) {
        return '<div class="route-box"><div class="route-line"><div><div class="muted small">Child app requests</div><div class="route-model">' +
          esc(route.requested_model) + '</div></div><div class="arrow">→</div><div><div class="muted small">Parent sends to</div><div class="route-model">' +
          esc(route.upstream_model) + '</div><div class="muted small">' + esc(providerName(route.provider)) + "</div></div></div></div>";
      }).join("");
      return '<section class="card app-card"><div class="row wrap"><div><div class="app-category">' + esc(app.category) +
        '</div><div class="app-title">' + esc(app.name) + '</div><div class="subtle small">' + esc(app.description) +
        '</div></div>' + routeStatus(app) + '</div><a class="repo" href="' + esc(app.repository) +
        '" target="_blank" rel="noreferrer">' + esc(app.repository) + " ↗</a>" + (routes || empty("No model route configured.")) +
        '<div class="row wrap"><span class="small ' + (app.has_api_key ? "muted" : "notice warn") + '">' +
        (app.has_api_key ? "Gateway key is active; plaintext is not stored." : "Generate a gateway key to connect this app.") +
        '</span><button class="btn secondary" data-action="rotate-key" data-app-id="' + esc(app.id) + '">' +
        (app.has_api_key ? "Rotate app key" : "Generate app key") + "</button></div></section>";
    }).join("");
    return pageHead("Applications", "Register a child app and give it a scoped gateway key. Its prompts and application rules remain in that app.") +
      '<div class="grid two">' + (cards || empty("No applications are registered.")) +
      '<section class="card"><h2 class="section-title">Connect another application</h2><p class="small muted">Register the model ID the child app already sends and its initial parent route.</p>' +
      '<form data-new-app><div class="field-grid"><div class="field"><label>Application name</label><input name="name" required placeholder="Claims assistant"></div>' +
      '<div class="field"><label>Application type</label><select name="category"><option>RAG</option><option>Agent</option><option>Structured output</option><option>Chat</option><option>Other</option></select></div>' +
      '<div class="field"><label>Existing model ID sent by app</label><input name="requested_model" required placeholder="gpt-4o-mini"></div>' +
      '<div class="field"><label>Provider</label><select name="provider">' + providerOptions("openrouter") + '</select></div>' +
      '<div class="field"><label>Target model</label><input name="upstream_model" required placeholder="provider/model-id"></div>' +
      '<div class="field"><label>Repository URL (optional)</label><input name="repository" placeholder="https://github.com/org/repo"></div></div>' +
      '<div class="field" style="margin-top:12px"><label>Description (optional)</label><input name="description" placeholder="What this application does"></div>' +
      '<div style="margin-top:14px"><button class="btn">Register application</button></div></form>' +
      '<div class="divider"></div><p class="small muted">Each app key is shown once, stored as a hash, and can be rotated. Provider credentials remain in the parent server environment.</p></section></div>';
  }
  function renderRoutes() {
    var content = state.apps.map(function (app) {
      var routeForms = (app.routes || []).map(function (route) {
        return '<form class="card" data-route-form data-app-id="' + esc(app.id) + '"><div class="row wrap"><div><div class="app-category">' +
          esc(app.category) + '</div><div class="app-title">' + esc(app.name) + '</div></div><span class="chip">' +
          (route.is_default ? "Default route" : "Additional route") + '</span></div><div class="field-grid" style="margin-top:14px">' +
          '<div class="field"><label>Exact model ID the app sends</label><input name="requested_model" readonly value="' + esc(route.requested_model) + '"></div>' +
          '<div class="field"><label>Provider</label><select name="provider">' + providerOptions(route.provider) + '</select></div>' +
          '<div class="field"><label>Target model</label><input name="upstream_model" required value="' + esc(route.upstream_model) + '"></div>' +
          '<div class="field"><label>Route status</label><select name="enabled"><option value="true"' + (route.enabled ? " selected" : "") +
          '>Enabled</option><option value="false"' + (!route.enabled ? " selected" : "") + '>Disabled</option></select></div>' +
          '<div class="field"><label>Max output tokens (optional)</label><input name="max_output_tokens" type="number" min="1" value="' +
          esc(route.max_output_tokens || "") + '"><small>Caps the child request for this route. Blank keeps the provider default.</small></div></div>' +
          '<div class="row wrap" style="margin-top:13px"><span class="small muted">Saved changes affect new requests; prompts and child-app rules are not edited.</span><button class="btn">Save route</button></div></form>';
      }).join("");
      routeForms += '<form class="card" data-extra-route data-app-id="' + esc(app.id) + '"><div class="app-title">Add a model alias</div>' +
        '<p class="small muted">Use the exact additional model ID already used by this app, then choose its parent target.</p><div class="field-grid">' +
        '<div class="field"><label>Existing app model ID</label><input name="requested_model" required placeholder="gpt-5-mini"></div>' +
        '<div class="field"><label>Provider</label><select name="provider">' + providerOptions("openrouter") + '</select></div>' +
        '<div class="field"><label>Target model</label><input name="upstream_model" required placeholder="provider/model-id"></div>' +
        '<div class="field"><label>Max output tokens (optional)</label><input name="max_output_tokens" type="number" min="1"><small>Blank keeps the provider default.</small></div></div>' +
        '<div style="margin-top:13px"><button class="btn secondary">Add route</button></div></form>';
      return routeForms;
    }).join("");
    return pageHead("Model routes", "Map the exact model ID a child app already sends to an approved provider and target model. Change the mapping here to migrate centrally.") +
      '<div class="notice">The gateway keeps child instructions and tools intact. A route can optionally cap output tokens to fit a provider limit.</div>' +
      '<div class="stack">' + (content || empty("Register an application first.")) + "</div>" +
      '<div class="grid two" style="margin-top:17px">' + card("Provider readiness", '<div class="provider-row">' +
        ((state.overview && state.overview.providers) || []).map(function (p) {
          return '<div class="provider-card"><div class="row"><strong>' + esc(p.name) + '</strong><span class="chip ' +
            (p.configured ? "live" : "off") + '">' + (p.configured ? "Ready" : "Setup needed") + "</span></div>" +
            '<div class="small muted">' + esc(p.base_url || "Add credentials to the server environment.") + "</div></div>";
        }).join("") + "</div>") +
      card("Current scope", '<p class="small">OpenAI-compatible endpoints: Chat Completions, Responses, Embeddings, and supported file / vector-store paths. Provider support depends on that provider implementing the requested endpoint.</p><p class="small muted">A model swap can change answer quality even when the request is unchanged. Use the evaluation page before promoting a route.</p>') +
      "</div>";
  }
  function summaryMarkup(title, metrics) {
    return '<section class="card"><h2 class="section-title">' + esc(title) + '</h2><div class="grid two">' +
      stat("Request success", metrics.successes + " / " + metrics.total, "") +
      stat("Exact reference match", percent(metrics.exact_rate), "") +
      stat("Valid JSON", percent(metrics.json_rate), "") +
      stat("Average latency", metrics.avg_latency == null ? "—" : fmt(metrics.avg_latency) + " ms", "") +
      '</div><p class="small muted">Tokens in/out: ' + fmt(metrics.input_tokens, 0) + " / " + fmt(metrics.output_tokens, 0) +
      " · Reported cost: $" + fmt(metrics.cost, 6) + "</p></section>";
  }
  function renderRagMigration() {
    var rag = state.rag;
    if (!rag && state.ragError) return '<section class="card"><h2 class="section-title">RAG migration workspace</h2><p class="small muted">Could not load this panel: ' + esc(state.ragError) + '</p></section>';
    if (!rag) return '<section class="card">Loading RAG migration workspaceâ€¦</section>';
    var active = rag.routes.find(function (route) { return route.is_default; }) || rag.routes[0];
    var captureRows = rag.captures.map(function (capture) {
      return '<div class="row wrap" style="padding:10px 0;border-bottom:1px solid var(--line)"><div><strong>#' + esc(capture.id) +
        ' Â· ' + esc(capture.requested_model) + '</strong><div class="small muted">' + esc(capture.created_at) + ' Â· ' + esc(capture.endpoint) +
        ' Â· ' + esc(providerName(capture.provider)) + ' / ' + esc(capture.upstream_model) + ' Â· ' + fmt(capture.latency_ms) + ' ms</div><div class="small">' +
        (capture.includes_tool_result ? '<span class="chip live">Retrieved tool result included</span>' : '<span class="chip off">Pre-retrieval turn</span>') +
        '</div><div class="small muted" style="max-width:680px;margin-top:4px">' + esc(capture.output_preview || "No text output captured") +
        '</div></div><button class="btn secondary" data-action="inspect-rag-capture" data-capture-id="' + esc(capture.id) + '">Inspect</button></div>';
    }).join("");
    var captureDetail = state.ragCapture ? '<section class="card"><div class="row wrap"><h3 class="section-title">Captured request #' + esc(state.ragCapture.id) +
      '</h3><button class="btn ghost" data-action="close-rag-capture">Close</button></div><p class="small muted">This local capture contains the exact child request body and may include resume or retrieval text.</p>' +
      '<div class="result-pair"><div class="result-box"><strong>Original request (instructions, input, tools)</strong><pre>' + esc(JSON.stringify(state.ragCapture.request, null, 2)) +
      '</pre></div><div class="result-box"><strong>Captured baseline answer</strong><pre>' + esc(state.ragCapture.response_text || "No text output") + '</pre></div></div></section>' : "";
    var selectedEligible = state.ragCapture && state.ragCapture.includes_tool_result;
    var compareForm = '<section class="card"><h3 class="section-title">Replay one real RAG turn</h3><p class="small muted">Baseline comes from the captured child response on its active route. The candidate uses the same request, retrieved tool result, and tool schema through the Parent proxy. This replays answer generation; it does not rerun Qdrant retrieval.</p>' +
      (state.ragCapture ? '<div class="notice ' + (selectedEligible ? '' : 'warn') + '">Selected capture #' + esc(state.ragCapture.id) + (selectedEligible ? ' includes a completed retrieval/tool result.' : ' is before retrieval. Choose a capture with a tool result before comparing.') + '</div>' : '<div class="notice warn">Inspect a capture with a completed retrieval/tool result first.</div>') +
      '<form data-rag-compare><input type="hidden" name="capture_id" value="' + esc(state.ragCapture ? state.ragCapture.id : '') + '"><div class="field-grid"><div class="field"><label>Candidate provider</label><select name="candidate_provider">' + providerOptions("openrouter") + '</select></div>' +
      '<div class="field"><label>Candidate model or Azure deployment</label><input name="candidate_model" required placeholder="Exact provider model ID"></div></div><div class="row wrap" style="margin-top:12px"><span class="small muted">Baseline: ' +
      (active ? esc(providerName(active.provider) + ' / ' + active.upstream_model) : 'No enabled route') + '</span><button class="btn"' + (state.busy || !selectedEligible ? ' disabled' : '') + '>' + (state.busy ? 'Replayingâ€¦' : 'Compare candidate through gateway') + '</button></div></form></section>';
    var evaluation = state.ragEvaluation;
    var evaluationPanel = "";
    if (evaluation) {
      var hasReviewed = evaluation.status === "approved" || evaluation.status === "rejected" || evaluation.status === "promoted" || evaluation.status === "rolled_back";
      evaluationPanel = '<section class="card"><div class="row wrap"><div><h3 class="section-title">RAG comparison #' + esc(evaluation.id) + '</h3><div class="small muted">Baseline ' +
        esc(providerName(evaluation.baseline_provider) + ' / ' + evaluation.baseline_model) + ' versus candidate ' + esc(providerName(evaluation.candidate_provider) + ' / ' + evaluation.candidate_model) +
        '</div></div><span class="chip ' + (evaluation.status === 'approved' || evaluation.status === 'promoted' ? 'live' : evaluation.status === 'rejected' ? 'bad' : '') + '">' + esc(evaluation.status) + '</span></div>' +
        '<div class="result-pair" style="margin-top:12px"><div class="result-box"><strong>Real captured baseline</strong><pre>' + esc(evaluation.baseline_output || 'No baseline text') + '</pre><div class="small muted">HTTP ' + esc(evaluation.baseline_status_code) + ' Â· ' + fmt(evaluation.baseline_latency_ms) + ' ms Â· tokens ' + fmt(evaluation.baseline_input_tokens, 0) + '/' + fmt(evaluation.baseline_output_tokens, 0) + ' Â· cost ' + (evaluation.baseline_cost_usd == null ? 'unknown' : '$' + fmt(evaluation.baseline_cost_usd, 6)) + '</div></div>' +
        '<div class="result-box"><strong>Candidate replay</strong><pre>' + esc(evaluation.candidate_output || 'No text output') + '</pre><div class="small muted">HTTP ' + esc(evaluation.candidate_status_code) + ' Â· ' + fmt(evaluation.candidate_latency_ms) + ' ms Â· tokens ' + fmt(evaluation.candidate_input_tokens, 0) + '/' + fmt(evaluation.candidate_output_tokens, 0) + ' Â· cost ' + (evaluation.candidate_cost_usd == null ? 'unknown' : '$' + fmt(evaluation.candidate_cost_usd, 6)) + '</div></div></div>' +
        '<div class="notice ' + (evaluation.status === 'approved' || evaluation.status === 'promoted' ? '' : 'warn') + '" style="margin-top:12px">' + esc(evaluation.recommendation) + '</div>';
      if (!hasReviewed && evaluation.status === 'pending_review') {
        evaluationPanel += '<form data-rag-review><div class="field-grid"><div class="field"><label>Baseline quality (1â€“5)</label><input name="baseline_quality_score" type="number" min="1" max="5" step="0.5" required></div><div class="field"><label>Candidate quality (1â€“5)</label><input name="candidate_quality_score" type="number" min="1" max="5" step="0.5" required></div><div class="field"><label>Baseline cost USD (optional, from Langfuse)</label><input name="baseline_cost_usd" type="number" min="0" step="0.000001" placeholder="Required if provider did not report cost"></div><div class="field"><label>Candidate cost USD (optional, from Langfuse)</label><input name="candidate_cost_usd" type="number" min="0" step="0.000001" placeholder="Required if provider did not report cost"></div></div><p class="small muted">Score factual correctness, retrieval grounding, citation quality, and completeness with the same rubric. Missing cost blocks promotion until supplied.</p><button class="btn">Save review and run gates</button></form>';
      }
      if (evaluation.status === 'approved') evaluationPanel += '<div style="margin-top:12px"><button class="btn" data-action="promote-rag" data-evaluation-id="' + esc(evaluation.id) + '">Promote candidate to RAG routes</button></div>';
      if (evaluation.status === 'promoted') evaluationPanel += '<div style="margin-top:12px"><button class="btn danger" data-action="rollback-rag" data-evaluation-id="' + esc(evaluation.id) + '">Rollback to previous routes</button></div>';
      evaluationPanel += '</section>';
    }
    var history = rag.evaluations.map(function (item) {
      return '<div class="row wrap" style="padding:8px 0;border-bottom:1px solid var(--line)"><button class="link-button" data-action="open-rag-eval" data-evaluation-id="' + esc(item.id) + '">#' + esc(item.id) + ' Â· ' + esc(item.baseline_model) + ' â†’ ' + esc(item.candidate_model) + '</button><span class="chip">' + esc(item.status) + '</span></div>';
    }).join("");
    return '<div class="stack">' +
      '<section class="hero"><div><h2>RAG model migration rehearsal</h2><p>Capture one real child request, replay its exact instructions and retrieved tool output against a candidate through the Parent Gateway, then review before promotion.</p></div><div class="hero-tag">RAG only Â· active route unchanged until approval</div></section>' +
      '<section class="card"><div class="row wrap"><div><h3 class="section-title">Capture real RAG turns</h3><p class="small muted">Capture is local and off by default. Enable it, ask a question in the RAG app, then turn it off. Captured content may contain resume data and is not added to ordinary activity.</p></div><button class="btn ' + (rag.capture_enabled ? 'danger' : '') + '" data-action="toggle-rag-capture">' + (rag.capture_enabled ? 'Stop capture' : 'Enable capture') + '</button></div><div class="small muted">' + (rag.capture_enabled ? 'Capture is currently ON for RAG Responses/Chat Completions.' : 'Capture is OFF.') + ' Â· Up to 100 recent model requests are kept locally.</div></section>' +
      '<div class="grid two">' +
      '<section class="card"><div class="row wrap"><h3 class="section-title">Captured requests</h3><button class="btn ghost" data-action="clear-rag-captures">Clear captures</button></div>' + (captureRows || empty('No RAG requests captured yet. Enable capture, then ask a question in the RAG app.')) + '</section>' +
      '<section class="card"><h3 class="section-title">Per-RAG promotion thresholds</h3><form data-rag-policy><div class="field-grid"><div class="field"><label>Minimum candidate quality (1â€“5)</label><input name="minimum_quality_score" type="number" min="1" max="5" step="0.5" value="' + esc(rag.policy.minimum_quality_score) + '"></div><div class="field"><label>Maximum quality drop from baseline</label><input name="max_quality_drop" type="number" min="0" max="4" step="0.5" value="' + esc(rag.policy.max_quality_drop) + '"></div><div class="field"><label>Maximum latency increase (%)</label><input name="max_latency_regression_pct" type="number" min="0" value="' + esc(rag.policy.max_latency_regression_pct) + '"></div><div class="field"><label>Maximum cost increase (%)</label><input name="max_cost_regression_pct" type="number" min="0" value="' + esc(rag.policy.max_cost_regression_pct) + '"></div></div><button class="btn secondary" style="margin-top:12px">Save RAG thresholds</button></form><p class="small muted">Cost gates require provider-reported cost or a per-request cost copied from Langfuse. Unknown cost never counts as a pass.</p></section></div>' +
      captureDetail + compareForm + evaluationPanel + card('Recent RAG comparisons', history || empty('No RAG model comparisons yet.')) +
      '<div class="notice warn">A candidate cannot be promised identical answers. Promotion needs a human quality score and passing quality, latency, and cost thresholds. Replay evaluates answer generation with the captured retrieval result; it does not rerun the retrieval search.</div></div>';
  }
  function renderEvaluation() {
    var data = state.evaluation;
    if (!data) return '<div class="card">Loading evaluation data…</div>';
    var sameModel = data.baseline_provider === data.candidate_provider &&
      String(data.baseline_model || "").trim().toLowerCase() === String(data.candidate_model || "").trim().toLowerCase();
    if (state.detail) {
      var groups = state.detail.groups.map(function (item) {
        function result(label, value) {
          if (!value) return '<div class="result-box"><strong>' + label + '</strong><p class="muted">No result saved.</p></div>';
          return '<div class="result-box"><strong>' + label + ' · ' + esc(value.model) + '</strong>' +
            '<div class="chip ' + (value.request_success ? "live" : "bad") + '">' + (value.request_success ? "Success" : "Failed") +
            '</div><pre>' + esc(value.error || value.answer || "No response") + '</pre><div class="small muted">Latency: ' +
            (value.latency_ms == null ? "—" : fmt(value.latency_ms) + " ms") + " · JSON: " + (value.valid_json ? "valid" : "invalid") +
            "</div></div>";
        }
        return '<section class="card"><h2 class="section-title">' + esc(item.name) + '</h2><p class="small muted">' +
          esc(item.prompt) + '</p><div class="result-pair">' + result("Baseline", item.baseline) + result("Candidate", item.candidate) + "</div></section>";
      }).join("");
      return '<div class="row wrap" style="margin-bottom:15px"><div><button class="link-button" data-action="back-eval">← Evaluation workspace</button><h1 style="font:800 22px Manrope;margin:8px 0 0">Comparison run #' +
        esc(state.detail.run.id) + '</h1></div><span class="chip">' + esc(state.detail.run.status) + "</span></div>" +
        '<div class="grid two">' + summaryMarkup("Baseline · " + state.detail.run.baseline_model, state.detail.baseline_summary) +
        summaryMarkup("Candidate · " + state.detail.run.candidate_model, state.detail.candidate_summary) + "</div>" + groups;
    }
    var cases = data.cases.map(function (item) {
      return '<label class="case"><input type="checkbox" name="case_ids" value="' + esc(item.id) +
        '"' + (state.selected.indexOf(item.id) >= 0 ? " checked" : "") + '><span><strong>' + esc(item.name) +
        '</strong><p>' + esc(item.prompt) + "</p></span></label>";
    }).join("");
    var history = data.recent_runs.map(function (run) {
      return '<div class="row wrap" style="padding:9px 0;border-bottom:1px solid var(--line)"><div><button class="link-button" data-action="open-run" data-run-id="' +
        esc(run.id) + '">Run #' + esc(run.id) + '</button><div class="small muted">' + esc(run.created_at) + " · " +
        esc(run.case_count) + " cases · " + esc(run.baseline_model) + " vs " + esc(run.candidate_model) +
        '</div></div><span class="chip">' + esc(run.status) + "</span></div>";
    }).join("");
    return pageHead("Evaluate before you switch", "Run the same saved cases against baseline and candidate models. This page does not edit prompts or guardrails in any connected application.") +
      renderRagMigration() +
      '<div class="divider"></div>' +
      '<div class="notice warn">Exact-match and JSON checks are useful for structured tasks. They do not prove semantic accuracy. Add representative expected answers and review important regressions before promoting a model.</div>' +
      (sameModel ? '<div class="notice warn">Baseline and candidate currently use the same provider model. Enter two distinct Azure deployment names before treating a run as a model comparison.</div>' : "") +
      '<div class="grid two"><section class="card"><h2 class="section-title">Evaluation dataset</h2><p class="small muted">Select identical cases for both model runs. Keep cases representative of the child app.</p>' +
      '<form data-eval-form><div class="stack">' + (cases || empty("Add a test case to create a dataset.")) +
      '</div><div class="field-grid" style="margin-top:14px"><div class="field"><label>Baseline model ID</label><input name="baseline_model" required value="' +
      esc(data.baseline_model) + '"></div><div class="field"><label>Candidate model ID</label><input name="candidate_model" required value="' +
      esc(data.candidate_model) + '"></div></div><div class="row wrap" style="margin-top:14px"><span class="small muted">Providers: ' +
      esc(providerName(data.baseline_provider)) + " / " + esc(providerName(data.candidate_provider)) +
      '</span><button class="btn"' + (state.busy ? " disabled" : "") + ">" + (state.busy ? "Running…" : "Compare models") + "</button></div>" +
      '<details style="margin-top:12px"><summary class="small">Tool definitions for this comparison</summary><p class="small muted">The local evaluation runner can execute calculate_budget. Edit this JSON to provide the tool schema your test cases expect.</p>' +
      '<div class="field" style="margin-top:9px"><label>Tools (JSON array)</label><textarea name="tools_json" rows="10">' + esc(JSON.stringify(DEFAULT_EVAL_TOOLS, null, 2)) + '</textarea></div></details></form>' +
      '<details style="margin-top:17px"><summary class="small">Add a dataset case</summary><form data-case-form style="margin-top:12px"><div class="field"><label>Case name</label><input name="name" required></div>' +
      '<div class="field" style="margin-top:9px"><label>User input (include context for RAG tests)</label><textarea name="prompt" required></textarea></div>' +
      '<div class="field" style="margin-top:9px"><label>Expected output as JSON</label><textarea name="expected_output" required placeholder=\'{\"answer\":\"...\"}\'></textarea></div>' +
      '<div style="margin-top:10px"><button class="btn secondary">Save dataset case</button></div></form></details>' +
      '<section class="card"><h2 class="section-title">Recent comparison runs</h2>' + (history || empty("No comparisons have been run yet.")) +
      '<div class="divider"></div><p class="small">Langfuse configured: <strong>' + (data.langfuse_trace_url_base ? "yes" : "check server .env") +
      '</strong></p><p class="small muted">Experiment traces and scores are sent through the Langfuse SDK when configured. Production gateway traces omit prompt and response content by default.</p></section></div>';
  }
  function renderActivity() {
    var rows = state.activity.map(function (r) {
      return "<tr><td>" + esc(new Date(r.created_at).toLocaleString()) + '</td><td><strong>' + esc(r.app_name || r.app_id) +
        '</strong></td><td><code>' + esc(r.requested_model || "—") + '</code></td><td>' + esc(r.provider) +
        '<div class="muted"><code>' + esc(r.upstream_model || "") + "</code></div></td><td><code>/" + esc(r.endpoint) +
        '</code></td><td><span class="chip ' + (r.success ? "live" : "bad") + '">' + esc(r.status_code || "—") +
        '</span></td><td>' + (r.latency_ms == null ? "—" : fmt(r.latency_ms) + " ms") +
        '</td><td>' + fmt(r.input_tokens, 0) + " / " + fmt(r.output_tokens, 0) +
        '</td><td>' + (r.cost_usd == null ? "—" : "$" + fmt(r.cost_usd, 6)) + "</td></tr>";
    }).join("");
    return pageHead("Request activity", "Inspect routing and operational metrics without storing prompts or application content in the local activity table.") +
      card("Recent gateway requests", rows ? '<div class="table-wrap"><table class="table"><thead><tr><th>Time</th><th>App</th><th>App model ID</th><th>Routed model</th><th>Endpoint</th><th>Status</th><th>Latency</th><th>Tokens in/out</th><th>Cost</th></tr></thead><tbody>' +
        rows + "</tbody></table></div>" : empty("No requests have passed through the gateway yet.")) +
      '<p class="footnote">Cost is shown only when the provider returns cost usage. Token usage is provider-reported; missing values stay blank.</p>';
  }
  function renderKeyModal() {
    return '<div class="modal-backdrop" data-action="close-modal"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="key-title">' +
      '<h2 id="key-title">Application key created</h2><p class="small muted">Copy this key now. The parent system stores only its hash. Rotating a key invalidates the previous key.</p>' +
      '<div class="secret" id="created-key">' + esc(state.oneTimeKey.api_key) + '</div><div class="row">' +
      '<button class="btn secondary" data-action="copy-key">Copy key</button><button class="btn" data-action="close-modal">Done</button></div></section></div>';
  }
  function render() { renderShell(); }
  function notify(text, error) { state.toast = {text: text, error: !!error}; render(); }
  function loadAll() {
    state.loading = true;
    render();
    return Promise.all([
      api("/api/control/overview"), api("/api/control/apps"), api("/api/control/requests?limit=150"),
      api("/api/state")
    ]).then(function (values) {
      state.overview = values[0];
      state.apps = values[1].apps || [];
      state.activity = values[2].requests || [];
      state.evaluation = values[3];
      if (!state.selected.length) state.selected = state.evaluation.cases.map(function (item) { return item.id; });
      state.loading = false;
      state.ragError = null;
      state.toast = null;
      render();
      api("/api/control/rag").then(function (rag) {
        state.rag = rag;
        state.ragError = null;
        if (state.toast && state.toast.text.indexOf("RAG migration panel could not load:") === 0) state.toast = null;
        render();
      }).catch(function (error) {
        state.rag = null;
        state.ragError = error.message;
        state.toast = {text: "RAG migration panel could not load: " + state.ragError, error: true};
        render();
      });
    }).catch(function (error) {
      state.loading = false;
      state.toast = {text: error.message, error: true};
      render();
    });
  }
  function formValue(form, name) {
    var field = form.elements.namedItem(name);
    return field ? field.value : "";
  }
  function selectedCases(form) {
    return Array.prototype.slice.call(form.querySelectorAll('input[name="case_ids"]:checked')).map(function (item) { return Number(item.value); });
  }

  root.addEventListener("click", function (event) {
    var tabButton = event.target.closest("[data-tab]");
    if (tabButton) {
      state.tab = tabButton.getAttribute("data-tab");
      state.detail = null;
      state.toast = null;
      render();
      return;
    }
    var actionButton = event.target.closest("[data-action]");
    if (!actionButton) return;
    var action = actionButton.getAttribute("data-action");
    if (action === "tab-apps") { state.tab = "apps"; render(); return; }
    if (action === "refresh") { loadAll(); return; }
    if (action === "back-eval") { state.detail = null; render(); return; }
    if (action === "toggle-rag-capture") {
      api("/api/control/rag/capture", {method:"PUT", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({enabled:!(state.rag && state.rag.capture_enabled)})})
        .then(function () { return loadAll(); }).then(function () { state.toast = {text:"RAG capture setting updated.", error:false}; render(); })
        .catch(function (error) { notify(error.message, true); });
      return;
    }
    if (action === "clear-rag-captures") {
      if (!window.confirm("Delete the locally captured RAG requests and their comparison records?")) return;
      api("/api/control/rag/captures", {method:"DELETE"}).then(function () {
        state.ragCapture = null; state.ragEvaluation = null; return loadAll();
      }).then(function () { state.toast = {text:"Local RAG captures and comparison records cleared.", error:false}; render(); })
        .catch(function (error) { notify(error.message, true); });
      return;
    }
    if (action === "inspect-rag-capture") {
      api("/api/control/rag/captures/" + encodeURIComponent(actionButton.getAttribute("data-capture-id")))
        .then(function (data) { state.ragCapture = data.capture; render(); })
        .catch(function (error) { notify(error.message, true); });
      return;
    }
    if (action === "close-rag-capture") { state.ragCapture = null; render(); return; }
    if (action === "open-rag-eval") {
      api("/api/control/rag/evaluations/" + encodeURIComponent(actionButton.getAttribute("data-evaluation-id")))
        .then(function (data) { state.ragEvaluation = data.evaluation; render(); })
        .catch(function (error) { notify(error.message, true); });
      return;
    }
    if (action === "promote-rag" || action === "rollback-rag") {
      var evaluationId = encodeURIComponent(actionButton.getAttribute("data-evaluation-id"));
      var verb = action === "promote-rag" ? "promote" : "rollback";
      var confirmText = action === "promote-rag" ? "Promote this candidate to all active RAG generation aliases?" : "Restore the RAG routes saved before this promotion?";
      if (!window.confirm(confirmText)) return;
      api("/api/control/rag/evaluations/" + evaluationId + "/" + verb, {method:"POST"})
        .then(function (data) { state.ragEvaluation = data.evaluation; return loadAll(); })
        .then(function () { state.toast = {text:action === "promote-rag" ? "Candidate promoted to RAG generation routes." : "Previous RAG routes restored.", error:false}; render(); })
        .catch(function (error) { notify(error.message, true); });
      return;
    }
    if (action === "open-run") {
      state.busy = true; render();
      api("/api/runs/" + encodeURIComponent(actionButton.getAttribute("data-run-id"))).then(function (data) {
        state.detail = data; state.busy = false; render();
      }).catch(function (error) { state.busy = false; notify(error.message, true); });
      return;
    }
    if (action === "rotate-key") {
      var appId = actionButton.getAttribute("data-app-id");
      actionButton.disabled = true;
      api("/api/control/apps/" + encodeURIComponent(appId) + "/key", {method:"POST"}).then(function (data) {
        state.oneTimeKey = data; loadAll();
      }).catch(function (error) { actionButton.disabled = false; notify(error.message, true); });
      return;
    }
    if (action === "copy-key") {
      if (!state.oneTimeKey) return;
      navigator.clipboard.writeText(state.oneTimeKey.api_key).then(function () { notify("Key copied to clipboard.", false); })
        .catch(function () { notify("Select and copy the key manually.", true); });
      return;
    }
    if (action === "close-modal") {
      if (event.target.closest(".modal") && actionButton.classList.contains("modal-backdrop")) return;
      state.oneTimeKey = null; loadAll(); return;
    }
    if (event.target.classList.contains("modal-backdrop")) { state.oneTimeKey = null; render(); }
  });

  root.addEventListener("change", function (event) {
    if (event.target.matches('input[name="case_ids"]')) {
      var id = Number(event.target.value);
      state.selected = event.target.checked ? state.selected.concat([id]) : state.selected.filter(function (value) { return value !== id; });
    }
  });

  root.addEventListener("submit", function (event) {
    var form = event.target;
    event.preventDefault();
    if (form.matches("[data-rag-policy]")) {
      var ragPolicy = {
        minimum_quality_score: Number(formValue(form, "minimum_quality_score")),
        max_quality_drop: Number(formValue(form, "max_quality_drop")),
        max_latency_regression_pct: Number(formValue(form, "max_latency_regression_pct")),
        max_cost_regression_pct: Number(formValue(form, "max_cost_regression_pct"))
      };
      api("/api/control/rag/policy", {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify(ragPolicy)})
        .then(function () { return loadAll(); }).then(function () { state.toast = {text:"RAG promotion thresholds saved.", error:false}; render(); })
        .catch(function (error) { notify(error.message, true); });
      return;
    }
    if (form.matches("[data-rag-compare]")) {
      var captureId = Number(formValue(form, "capture_id"));
      if (!captureId) { notify("Inspect a captured RAG request first.", true); return; }
      state.busy = true; render();
      api("/api/control/rag/evaluations", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({
        capture_id:captureId, candidate_provider:formValue(form, "candidate_provider"), candidate_model:formValue(form, "candidate_model").trim()
      })}).then(function (data) {
        state.ragEvaluation = data.evaluation; state.busy = false;
        state.toast = {text:"Candidate replay completed through the Parent Gateway. Review both answers.", error:false};
        return loadAll();
      }).then(function () { render(); }).catch(function (error) { state.busy = false; notify(error.message, true); });
      return;
    }
    if (form.matches("[data-rag-review]")) {
      var review = {
        baseline_quality_score: Number(formValue(form, "baseline_quality_score")),
        candidate_quality_score: Number(formValue(form, "candidate_quality_score")),
        baseline_cost_usd: formValue(form, "baseline_cost_usd") || null,
        candidate_cost_usd: formValue(form, "candidate_cost_usd") || null
      };
      if (!state.ragEvaluation) { notify("Open a RAG comparison before reviewing it.", true); return; }
      api("/api/control/rag/evaluations/" + encodeURIComponent(state.ragEvaluation.id) + "/review", {
        method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(review)
      }).then(function (data) {
        state.ragEvaluation = data.evaluation;
        state.toast = {text:data.evaluation.status === "approved" ? "All configured gates passed. Promotion is available." : "Review saved. Promotion is blocked by the reported gates.", error:data.evaluation.status !== "approved"};
        return loadAll();
      }).then(function () { render(); }).catch(function (error) { notify(error.message, true); });
      return;
    }
    if (form.matches("[data-new-app]")) {
      var appData = {
        name: formValue(form, "name"), category: formValue(form, "category"),
        requested_model: formValue(form, "requested_model"), provider: formValue(form, "provider"),
        upstream_model: formValue(form, "upstream_model"), repository: formValue(form, "repository"),
        description: formValue(form, "description")
      };
      api("/api/control/apps", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(appData)})
        .then(function () { state.toast = {text:"Application registered. Generate an app key to connect it.", error:false}; return loadAll(); })
        .catch(function (error) { notify(error.message, true); });
      return;
    }
    if (form.matches("[data-route-form]")) {
      var appRouteId = form.getAttribute("data-app-id");
      var routeData = {
        requested_model: formValue(form, "requested_model"), provider: formValue(form, "provider"),
        upstream_model: formValue(form, "upstream_model"), enabled: formValue(form, "enabled") === "true",
        max_output_tokens: formValue(form, "max_output_tokens") || null
      };
      api("/api/control/apps/" + encodeURIComponent(appRouteId) + "/route", {
        method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify(routeData)
      }).then(function () { state.toast = {text:"Route saved. New requests will use this mapping.", error:false}; return loadAll(); })
        .catch(function (error) { notify(error.message, true); });
      return;
    }
    if (form.matches("[data-extra-route]")) {
      var extraAppId = form.getAttribute("data-app-id");
      var extraRoute = {
        requested_model: formValue(form, "requested_model"), provider: formValue(form, "provider"),
        upstream_model: formValue(form, "upstream_model"), max_output_tokens: formValue(form, "max_output_tokens") || null
      };
      api("/api/control/apps/" + encodeURIComponent(extraAppId) + "/routes", {
        method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(extraRoute)
      }).then(function () { state.toast = {text:"Additional model route added.", error:false}; return loadAll(); })
        .catch(function (error) { notify(error.message, true); });
      return;
    }
    if (form.matches("[data-eval-form]")) {
      var ids = selectedCases(form);
      if (!ids.length) { notify("Select at least one dataset case.", true); return; }
      if (state.evaluation && state.evaluation.baseline_provider === state.evaluation.candidate_provider &&
          formValue(form, "baseline_model").trim().toLowerCase() === formValue(form, "candidate_model").trim().toLowerCase()) {
        notify("Enter two distinct model deployment names to compare model quality.", true);
        return;
      }
      var tools = [];
      try {
        var rawTools = formValue(form, "tools_json").trim();
        tools = rawTools ? JSON.parse(rawTools) : [];
        if (!Array.isArray(tools)) throw new Error("Tools must be a JSON array.");
      } catch (error) {
        notify("Tool definitions must be a valid JSON array.", true);
        return;
      }
      state.busy = true; state.toast = {text:"Comparing the same cases against both configured providers…", error:false}; render();
      var runData = {
        case_ids: ids, baseline_model: formValue(form, "baseline_model"),
        candidate_model: formValue(form, "candidate_model"), system_prompt: "", examples: [], tools: tools,
        temperature: "0", max_tokens: "2048"
      };
      api("/api/run", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(runData)})
        .then(function (result) {
          return Promise.all([api("/api/runs/" + result.run_id), loadAll()]).then(function (values) {
            state.detail = values[0]; state.busy = false; state.toast = {text:"Comparison " + result.status + " and saved locally.", error:false}; render();
          });
        }).catch(function (error) { state.busy = false; notify(error.message, true); });
      return;
    }
    if (form.matches("[data-case-form]")) {
      var caseData = {name:formValue(form,"name"), prompt:formValue(form,"prompt"), expected_output:formValue(form,"expected_output")};
      api("/api/cases", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(caseData)})
        .then(function () { state.toast = {text:"Dataset case saved.", error:false}; return loadAll(); })
        .catch(function (error) { notify(error.message, true); });
    }
  });

  loadAll();
}());
