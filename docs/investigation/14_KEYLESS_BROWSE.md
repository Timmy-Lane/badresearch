# 14 — Keyless Agentic Browse + Structured Extraction

**Goal:** A complete, reimplementable design for how the Bad Research skill does agentic browsing and
typed extraction **with no API keys** — using only the Claude Code host model as the agent brain, driving
**local, open-source, keyless browser tools**. The primary tool is **`vercel-labs/agent-browser`** (a native
Rust CLI that drives local headless Chrome over CDP, no Node, no Playwright, no cloud). We port the
*structured-extraction patterns* (Stagehand's `act`/`extract`/`observe` prompts, AgentQL's AQL query DSL,
Browser-Use's indexed-action loop) onto agent-browser's `snapshot`/`@eN`/`eval` primitives, with Claude Code
acting as the LLM that those products use as a paid SaaS call.

**The keyless rule (load-bearing):** every product in the reference set (Browserbase/Stagehand, AgentQL,
Browser-Use cloud) costs money because (a) they run a *remote* browser, and (b) they make a *server-side LLM
call* per primitive. We pay $0 because (a) agent-browser launches a *local* Chrome and (b) **Claude Code IS
the LLM** — when a pattern says "call GPT-4o with this prompt and this AXTree", we instead reason over the
agent-browser snapshot text directly in the Claude Code turn. No model is ever called over a network we pay
for.

**Label key:** KNOWN = read verbatim from source (`/tmp/m-agentbrowser` clone at HEAD, or our RE files,
cited). INFERRED = derived from code/probing. DESIGNED = my reimplementation proposal for the skill (not in any
source). Every KNOWN cites `file:line`.

**Sources read for this dossier:**
- `vercel-labs/agent-browser` cloned `--depth=1` to `/tmp/m-agentbrowser` (Rust CLI, 55k LOC). Files read in
  full: `README.md`, `skills/agent-browser/SKILL.md`, `skill-data/core/SKILL.md`, `AGENTS.md`,
  `cli/src/native/snapshot.rs` (1586 L), `cli/src/native/element.rs` (1119 L), `cli/src/native/interaction.rs`
  (1183 L), `cli/src/native/stream/chat.rs` (the built-in LLM loop), `cli/src/native/providers.rs`,
  `cli/src/commands.rs` (5107 L, spot-read).
- `products/BROWSERBASE_PRODUCT_CODE.md` (Stagehand verbatim prompts + AXTree pipeline) — researchfms.
- `products/AGENTQL_PRODUCT_CODE.md` + `agentql/AGENTQL_GAP_02_GRAMMAR.md` (the AQL grammar from the installed
  `agentql==1.18.1` SDK) — researchfms.
- `docs/investigation/03_BROWSE_EXTRACT.md` (first-pass, this repo).

---

## 0 — Executive summary: the keyless stack in one diagram

```
                          ┌─────────────────────────────────────────┐
                          │  CLAUDE CODE (the host model)            │
                          │  = the agent brain. Reasons over snapshot │
                          │    text, decides next action, extracts    │
                          │    typed data. NO network LLM call.       │
                          └───────────────┬───────────────────────────┘
                                          │ issues Bash tool calls
                                          ▼
   HTTP (httpx)  ──fail/JS?──►  crawl4ai (local Chromium → markdown) ──need interaction?──►
                                          │
                                          ▼
                          ┌─────────────────────────────────────────┐
                          │  agent-browser  (native Rust CLI)         │
                          │  local Chrome (Chrome-for-Testing) via    │
                          │  CDP. Persistent daemon. KEYLESS.         │
                          │                                           │
                          │  open → snapshot -i → click @e3 → ...      │
                          │  accessibility-tree snapshot w/ @eN refs   │
                          │  eval --stdin  (arbitrary JS extraction)   │
                          └─────────────────────────────────────────┘
```

The three escalation rungs and when each fires (DESIGNED, formalized in §7):

| Rung | Tool | Cost | Use when |
|---|---|---|---|
| 1 | `httpx` GET | $0 | static HTML, APIs, sitemaps |
| 2 | `crawl4ai` (local) | $0 | JS render needed, want clean markdown of one page, no interaction |
| 3 | `agent-browser` (local) | $0 | login, multi-step nav, click/fill, forms, paywall-with-cookies, typed extraction over a live DOM |

There is **no rung 4 that costs money** in the keyless build. Browserbase/AgentQL/Stagehand-cloud are
*replaced*, not *called*. (When a cloud browser is genuinely unavoidable — e.g. residential-IP anti-bot — see
§9, but it is out of scope for the keyless skill.)

---

## 1 — agent-browser is truly keyless (confirmed from source)

This is the first thing to nail down, because the whole design rests on it.

**KNOWN — default path launches a LOCAL browser, no key:** `README.md:1210-1219` ("Architecture"):
> agent-browser uses a client-daemon architecture: 1. Rust CLI 2. Rust Daemon — Pure Rust daemon using direct
> CDP, no Node.js required. Browser Engine: Uses Chrome (from Chrome for Testing) by default.

`install` downloads Chrome from Google's Chrome-for-Testing channel (`README.md:451`,
`AGENTS.md:92`: "The `install` command downloads Chrome from Chrome for Testing directly"). No account, no
token. The daemon talks raw CDP over a local WebSocket to a local Chrome process.

**KNOWN — keys are needed ONLY for two opt-in things, both of which we skip:**

1. **Cloud browser providers** (`-p browserbase|browserless|browseruse|kernel|agentcore`). `providers.rs:26-70`
   is the only place env keys are read, and only when `-p <provider>` is passed:
   `providers.rs:135` `let api_key = env::var("BROWSERBASE_API_KEY").map_err(|_| "BROWSERBASE_API_KEY ... not set")?;`
   Without `-p`, `connect_provider` is never called — the daemon launches local Chrome. **We never pass `-p`.**

2. **The built-in `chat` command** (natural-language → commands). `chat.rs` (top-level
   `cli/src/chat.rs:131`) reads `AI_GATEWAY_API_KEY` and POSTs to `https://ai-gateway.vercel.sh` (Vercel AI
   Gateway). This is the ONE keyed LLM path in the tool — and **we never use it.** Claude Code *replaces* that
   loop entirely (see §4). The `chat` command is agent-browser's own little agent for users who don't already
   have one; we already are one.

**Verdict:** the local Chrome + CDP + `snapshot`/`click`/`eval` surface is 100% keyless. The only keyed
surfaces are optional and we route around both. INFERRED corollary: the only "cost" is local CPU/RAM for a
headless Chrome, which is what crawl4ai already spends today.

---

## 2 — The load-bearing primitive: accessibility-snapshot + `@eN` refs

This is the mechanism that makes keyless agentic browsing *work* — it is the exact same idea Stagehand and
AgentQL sell (an accessibility-tree the LLM reasons over), but produced locally and handed to Claude Code as
plain text. Understanding it is the whole game.

### 2.1 What a snapshot is and why it's cheap (KNOWN)

`skill-data/core/SKILL.md:9-12`:
> Chrome/Chromium via CDP ... Accessibility-tree snapshots with compact `@eN` refs let agents interact with
> pages in ~200-400 tokens instead of parsing raw HTML.

The output format (`skill-data/core/SKILL.md:69-81`, KNOWN):
```
Page: Example - Log in
URL: https://example.com/login

@e1 [heading] "Log in"
@e2 [form]
  @e3 [input type="email"] placeholder="Email"
  @e4 [input type="password"] placeholder="Password"
  @e5 [button type="submit"] "Continue"
  @e6 [link] "Forgot password?"
```
Each line is `role + accessible-name + properties + [ref=eN]`. The agent (Claude Code) reads this, picks a
ref, and acts: `click @e5`. This is *the* selector-hallucination fix — the agent never invents a CSS selector;
it picks from an enumerated list the tool generated from the real page.

### 2.2 How the snapshot is built — the exact algorithm (KNOWN, `cli/src/native/snapshot.rs`)

`take_snapshot()` (`snapshot.rs:216`) runs this pipeline against the local Chrome session:

1. **Enable CDP domains** (`snapshot.rs:224-229`): `DOM.enable`, `Accessibility.enable`.
2. **Optional CSS scope** (`snapshot.rs:234-284`): if `-s "#main"` given, `Runtime.evaluate` a
   `document.querySelector(...)`, then `DOM.describeNode` with `depth:-1`, collect every `backendNodeId` in the
   subtree (`collect_backend_node_ids`, recurses into shadow DOM + content documents, `snapshot.rs:1323`).
3. **Pull the AX tree** (`snapshot.rs:298-304`): `Accessibility.getFullAXTree`. This is the single source of
   truth — one CDP call gives the whole semantic tree.
4. **Build the tree** (`build_tree`, `snapshot.rs:926`): map AX nodes → `TreeNode{role,name,level,checked,
   expanded,selected,disabled,required,value_text,backend_node_id,children,...}`. Ignored nodes and
   `InlineTextBox` are dropped (`snapshot.rs:938`). **StaticText aggregation** (`snapshot.rs:978-1028`):
   consecutive `StaticText` siblings are concatenated into the first one (HTML splits text across inline tags;
   this rejoins it) — this is why the snapshot reads like prose, not fragments.
5. **Cursor-interactive discovery** (`find_cursor_interactive_elements`, `snapshot.rs:609`): a single big
   `Runtime.evaluate` walks `document.body.querySelectorAll('*')` and flags elements that are *visually*
   interactive but not semantically tagged — `getComputedStyle(el).cursor === 'pointer'`, `onclick`,
   `tabindex !== -1`, or `contenteditable`. It skips native interactive tags (`a,button,input,select,textarea,
   details,summary`) and ARIA-interactive roles, dedups inherited `cursor:pointer` from a parent
   (`snapshot.rs:658-662`), skips zero-size and hidden elements, then **tags each match with `data-__ab-ci=<i>`**
   so backendNodeIds can be batch-resolved via `DOM.querySelectorAll('[data-__ab-ci]')`, and finally **removes
   the attribute** (`snapshot.rs:798`). This is how a `<div onclick=...>` styled as a button still gets a ref.
   Each is classified `clickable` / `editable` / `focusable` with hints (`snapshot.rs:839-859`).
6. **Hidden-input promotion** (`promote_hidden_inputs`, `snapshot.rs:899`): a `<label>` wrapping a
   `display:none` `<input type=radio>` shows up in the AX tree as a nameless `LabelText`; this promotes it to
   `role=radio` with the right `checked` state so the snapshot shows real radios.
7. **Ref assignment** (`snapshot.rs:354-403`): a node gets a `@eN` ref if its role is in `INTERACTIVE_ROLES`
   (button, link, textbox, checkbox, radio, combobox, listbox, menuitem*, option, searchbox, slider, spinbutton,
   switch, tab, treeitem, Iframe — `snapshot.rs:11-30`), OR it's a `CONTENT_ROLE` *with a non-empty name*
   (heading, cell, gridcell, columnheader, listitem, article, region, main, navigation — `snapshot.rs:32-43`),
   OR it's cursor-interactive. Refs are sequential `e1,e2,...`; the counter persists across snapshots in the
   session (`set_next_ref_num`, `snapshot.rs:414`).
8. **Duplicate disambiguation** (`RoleNameTracker`, `snapshot.rs:185-214`): every `(role,name)` pair is counted;
   if a pair occurs >1 time, each ref also records its `nth` index. This is what lets a stale ref re-resolve
   ("the 2nd button named 'Delete'").
9. **Render** (`render_tree`, `snapshot.rs:1060`): DFS to indented text. Skips empty `generic` wrappers, the
   `RootWebArea`, and (in `-i` mode) any node without a ref. Iframes are recursively snapshotted and inlined
   under their parent line (`snapshot.rs:494-557`) — cross-origin iframes that block AX access are silently
   skipped.
10. **Filters** (`SnapshotOptions`, `snapshot.rs:77-84`): `-i` interactive-only, `-c` compact (keep only lines
    with `ref=` or a value, plus their ancestors — `compact_tree`, `snapshot.rs:1190`), `-d N` depth cap,
    `-u` include link hrefs (resolved in parallel via `DOM.resolveNode` + `callFunctionOn`, `snapshot.rs:416`).

**Why this matters for the keyless port:** the *entire* "accessibility tree the LLM reasons over" that
Browserbase/AgentQL charge for is produced here, locally, for free, as ~200-400 tokens of text. Claude Code
ingests it directly in the Bash tool result. No `ARIA_TREE_MAX_TOKENS=70000` server round-trip
(`BROWSERBASE_PRODUCT_CODE.md:4267`) — the budget is just Claude Code's own context.

### 2.3 How a ref resolves to an action — the deterministic grounding (KNOWN, `cli/src/native/element.rs`)

The ref→element resolution is the keyless equivalent of AgentQL's "grounding" (deterministic post-LLM
validation that catches hallucinated refs). `RefMap` (`element.rs:18`) maps `ref_id → RefEntry{backend_node_id,
role, name, nth, frame_id}`. `resolve_element_center` (`element.rs:149`) and `resolve_element_object_id`
(`element.rs:216`):

1. **Fast path:** use cached `backendNodeId` → `DOM.getBoxModel` (for clicks) or `DOM.resolveNode` (for JS ops).
2. **Stale-ref fallback** (`find_node_id_by_role_name`, `element.rs:340`): if the backendNodeId is stale (page
   re-rendered), **re-query `Accessibility.getFullAXTree` and find the node by `role+name+nth`** — the exact
   same data source that minted the ref, so matching is guaranteed consistent. This is the deterministic
   regrounding: a ref is never a fragile coordinate, it's a `(role,name,nth)` identity that survives re-render.
3. **CSS/XPath fallback** (`build_find_element_js`, `element.rs:400`): `@e`-prefixed → ref; else
   `document.querySelector(...)` or `document.evaluate(...)` for `xpath=`.

`parse_ref` (`element.rs:124`) accepts `@e1`, `ref=e1`, or bare `e1`.

### 2.4 Actions dispatch real input events, not JS .click() (KNOWN, `cli/src/native/interaction.rs`)

This is why agent-browser beats naive `eval('el.click()')` scraping — it drives Chrome's real input pipeline,
so React/Vue synthetic-event handlers, hover menus, and bot-detection-sensitive sites behave as if a human
acted:

- **click** (`interaction.rs:9`): resolve ref → center `(x,y)` from `DOM.getBoxModel` content-quad average
  (`box_model_center`, `element.rs:470`) → `Input.dispatchMouseEvent` (a *real* mouse event at coordinates),
  not `el.click()`.
- **hover** (`interaction.rs:48`): `Input.dispatchMouseEvent{mouseMoved}` at element center.
- **fill** (`interaction.rs:83`): `callFunctionOn this.focus()` → clear (`this.select(); this.value='';` +
  dispatch `input` event) → `Input.insertText`. Clears then inserts in one shot.
- **type** (`interaction.rs:150`): focus → optional clear → `type_text_into_active_context` (`interaction.rs:208`)
  which sends `Input.insertText` per printable char, but real `Input.dispatchKeyEvent` keyDown/keyUp for
  `\n \r \t` (so Enter/Tab fire handlers). Optional per-char `delay_ms`.
- **press** (`interaction.rs:276`), **select_option** (`393`), **check/uncheck** (`439`/`491`), **scroll** (`341`),
  **drag** (in `actions.rs`), **upload** (file chooser), **scroll_into_view** (`724`).

`is_element_checked` (`element.rs:638`) even mirrors Playwright's follow-label retargeting (native input → ARIA
role → `label.control` → nested input). This is production-grade fidelity, free and local.

---

## 3 — Complete agent-browser CLI command map (which we use, why)

KNOWN from `README.md:101-473` + `skill-data/core/SKILL.md`. Grouped by purpose; the **Use?** column marks what
the keyless skill actually drives. ~15+ categories, ~80 commands.

### 3.1 Lifecycle / navigation
| Command | Does | Use? |
|---|---|---|
| `open [url]` (aliases `goto`,`navigate`) | launch local Chrome (no url → about:blank), navigate | ✅ core |
| `close [--all]` | close session / all sessions | ✅ |
| `back` / `forward` / `reload` | history nav | ✅ |
| `pushstate <url>` | SPA client-side nav; auto-detects `window.next.router.push`, falls back to `history.pushState`+popstate | ◻ SPA only |
| `connect <port>` / `--cdp <port\|url>` / `--auto-connect` | attach to an *existing* Chrome you launched (incl. your real logged-in profile) | ◻ auth reuse |

### 3.2 Inspect / read (the extraction read-side)
| Command | Does | Use? |
|---|---|---|
| **`snapshot [-i] [-c] [-u] [-d N] [-s sel] [--json]`** | accessibility tree with `@eN` refs — **the primary perception primitive** | ✅✅ core |
| `get text\|html\|value\|attr\|title\|url\|count\|box\|styles <sel>` | targeted reads by ref/selector | ✅ extract |
| `is visible\|enabled\|checked <sel>` | state checks | ✅ |
| `screenshot [path] [--full] [--annotate]` | PNG/JPEG; `--annotate` overlays `[N]`→`@eN` numbered labels for multimodal reasoning | ✅ (annotate for icon-only UIs) |
| `pdf <path>` | save page as PDF | ◻ |
| **`eval <js>` / `eval -b <base64>` / `eval --stdin`** | run arbitrary JS in page; **the escape hatch for typed extraction** | ✅✅ extract |

### 3.3 Interact (the action-side)
| Command | Does | Use? |
|---|---|---|
| `click <sel> [--new-tab]`, `dblclick`, `focus`, `hover` | mouse actions (real CDP input events) | ✅ |
| `type <sel> <text>`, `fill <sel> <text>` | keyboard input (fill = clear+type) | ✅ |
| `press <key>` (e.g. `Enter`, `Control+a`), `keyboard type\|inserttext`, `keydown`/`keyup` | key events | ✅ |
| `select <sel> <val…>`, `check`/`uncheck <sel>` | form controls | ✅ |
| `scroll <dir> [px]`, `scrollintoview <sel>`, `drag <src> <tgt>`, `upload <sel> <files>` | misc | ✅ |
| `mouse move\|down\|up\|wheel`, `set viewport\|device\|geo\|offline\|media` | low-level / emulation | ◻ |

### 3.4 Find (semantic locators — no prior snapshot needed)
`find role\|text\|label\|placeholder\|alt\|title\|testid\|first\|last\|nth <q> <action> [value]`
(`README.md:166-193`). Actions: `click,fill,type,hover,focus,check,uncheck,text`. Options `--name`, `--exact`.
**Use?** ✅ as a fallback when re-snapshotting is wasteful (e.g. `find role button click --name "Submit"`).

### 3.5 Wait (agents fail more from bad waits than bad selectors — `SKILL.md:144`)
`wait <sel>` (visible) / `wait <ms>` / `wait --text "…"` / `wait --url "**/dash"` / `wait --load
load|domcontentloaded|networkidle` / `wait --fn "<js condition>"` / `wait "#x" --state hidden`. Default timeout
25s (below the 30s IPC read timeout, `README.md:842`). **Use?** ✅✅ — always wait for a concrete signal after a
page-changing action.

### 3.6 Auth / session persistence (the login + paywall mechanism — keyless)
| Command | Does | Use? |
|---|---|---|
| `--profile <name\|path>` | reuse an existing Chrome profile's cookies/logins (read-only snapshot copy) | ✅ login reuse |
| `--session-name <name>` | auto-save/restore cookies+localStorage by name to `~/.agent-browser/sessions/` | ✅ |
| `state save\|load\|list\|show\|rename\|clear <path>` | export/import storage state JSON | ✅ |
| `auth save\|login <name>` | encrypted local credential vault; LLM never sees the password (`README.md:634`) | ✅ secrets |
| `cookies [set] [--curl <file>] [clear]`, `storage local\|session …` | cookie/storage import (incl. Copy-as-cURL dumps) | ✅ paywall cookies |
| `--headers '{"Authorization":"Bearer …"}'` | origin-scoped auth headers (skip login UI), not leaked cross-domain | ✅ |
| `set credentials <u> <p>` | HTTP basic auth | ◻ |
| `AGENT_BROWSER_ENCRYPTION_KEY` | AES-256-GCM at-rest encryption of saved state | ◻ |

### 3.7 Network (mock / inspect — useful for finding the JSON API behind a page)
`network route <url> [--abort] [--body <json>] [--resource-type …]` / `unroute` / `requests [--filter|--type|
--method|--status]` / `request <id>` / `har start|stop`. **Use?** ◻ `network requests` + `network har` to
discover an underlying API endpoint, then drop to httpx (rung-1) — often the cheapest extraction.

### 3.8 Tabs / frames / dialogs
`tab [new|close|<t1|label>]` (stable `t1,t2` ids + optional labels), `window new`, `frame <sel>|main`,
`dialog accept|dismiss|status`. `alert`/`beforeunload` auto-accepted (`SKILL.md:324`); `confirm`/`prompt` need
explicit handling. **Use?** ✅ as needed.

### 3.9 Batch (multi-step in one process invocation — latency win)
`batch "open …" "snapshot -i" "click @e1"` (args) or `… | agent-browser batch --json` (JSON array of
`[cmd, args…]`), `--bail` stops on first error (`README.md:212-232`). Pre-navigation setup (cookies/routes
before first nav) needs `open` with no url then batch (`README.md:396-409`). **Use?** ✅ for deterministic
known sequences (login flow you've already mapped); NOT for the exploratory loop (where you need to read
snapshot output before deciding the next ref).

### 3.10 Debug / introspection (skip for scraping; useful for QA)
`trace`, `profiler`, `console [--json]`, `errors`, `highlight`, `inspect`, `react tree|inspect|renders|
suspense`, `vitals`, `diff snapshot|screenshot|url`. **Use?** ◻ mostly out of scope; `console`/`errors` handy
to debug why an extraction returned empty.

### 3.11 Sessions / setup / skills
`--session <name>` (isolated browser: own cookies/tabs/refs — parallel scraping), `session [list]`, `install`,
`doctor [--fix|--offline|--json]`, `upgrade`, `skills list|get <name> [--full]`. `skills get core` serves the
version-matched usage guide (the skill stub redirects here, `skills/agent-browser/SKILL.md:20-23`). **Use?**
✅ `--session` for parallelism; `doctor --json` for health pre-flight.

### 3.12 The one keyed command we DON'T use
`chat ["<instruction>"]` — agent-browser's own NL→commands agent (Vercel AI Gateway, needs
`AI_GATEWAY_API_KEY`). **We replace it with Claude Code** (§4). Listed here only to be explicit about what we
route around.

---

## 4 — Claude Code as the agent brain (replacing the keyed `chat` loop)

agent-browser ships its own little agent — and reading it tells us *exactly* the shape Claude Code should
adopt, because Vercel built it to drive these same commands.

### 4.1 What agent-browser's built-in loop looks like (KNOWN, `cli/src/native/stream/chat.rs`)

- **One tool, one string arg** (`CHAT_TOOLS`, `chat.rs:156`):
  ```json
  [{"type":"function","function":{"name":"agent_browser",
    "description":"Execute an agent-browser command. Runs against the active session by default…",
    "parameters":{"type":"object","properties":{"command":{"type":"string",
      "description":"…e.g. 'agent-browser open https://google.com' or 'agent-browser snapshot -i' or 'agent-browser click @e3'"}},
    "required":["command"]}}}]
  ```
  The entire action space is "emit one agent-browser command string." That's the whole interface. Claude Code
  driving Bash *is exactly this* — except the tool is `Bash` and the command is `agent-browser …`.

- **System prompt** (`get_system_prompt`, `chat.rs:124-153`, KNOWN verbatim, paraphrased rules):
  ```
  You are an AI assistant that controls a browser through agent-browser. You have an active browser session…
  RULES:
  - You MUST use the agent_browser tool for every browser action. NEVER claim you performed an action without
    calling the tool.
  - If a request is outside your capabilities, say so honestly. Do not improvise or pretend.
  - One tool call per command. Do not chain with `&&` or `;`.
  - Do not add `--json`.
  - Do not run non-agent-browser programs.
  - For screenshots, omit the path argument so they save to the default location…
  - To create a new session: add `--session <name>` to any command…
  ```
  Then it inlines the full `skill-data/core/SKILL.md` content as `<skill name="core">…`. (`chat.rs:127-132`.)

- **The loop** (`run_chat_turn`, top-level `cli/src/chat.rs:195-389`): stream completions → collect text +
  tool_calls → for each tool_call, `execute_chat_tool(session, command)` → append `{"role":"tool",…}` →
  repeat until the model returns no more tool calls. Tool timeout 60s (`chat.rs:226`). Context compaction at
  `COMPACT_THRESHOLD_CHARS = 200_000` (`stream/chat.rs:158`).

- **Command allow-listing** (`execute_chat_tool`, `stream/chat.rs:457-505`): strips a leading `agent-browser`,
  splits on `&&`/`;` and keeps only the first, validates `first_cmd ∈ ALLOWED_COMMANDS` (`chat.rs:369`), only
  permits `--session`/`--engine` global flags (`ALLOWED_GLOBAL_FLAGS`, `chat.rs:455`). Security hardening for
  an untrusted-LLM scenario.

### 4.2 The keyless reimplementation (DESIGNED)

Claude Code is already a tool-calling agent with a `Bash` tool. So the keyless agent loop is *literally*:

1. **Skill prompt** (port the system prompt above into the Bad Research skill's instructions). Keep the hard
   rules verbatim — especially: "re-snapshot after any page change," "never claim an action you didn't run,"
   "one command, read the output, then decide." Drop the `--json`/allow-list constraints (those exist because
   Vercel doesn't trust *its* LLM; we trust Claude Code, and `--json` is actively useful for us — see §6).
2. **Perception** = `agent-browser snapshot -i --json` → Claude Code reads the `@eN` list from the Bash result.
3. **Decision** = Claude Code picks a ref (no model call — it *is* the model).
4. **Action** = `agent-browser click @e3` / `fill @e4 "…"` / `press Enter` via Bash.
5. **Wait** = `agent-browser wait --text "…"` or `wait --load networkidle`.
6. **Re-snapshot** (refs go stale on any page change — `SKILL.md:26-30`), goto 2.
7. **Terminate** when the goal text/data is present.

This is the ReAct loop, but the "Thought→Action→Observation" is "Claude Code reasoning → Bash agent-browser →
Bash stdout." **Zero paid LLM calls**: every Stagehand-style `act`/`extract`/`observe` "one LLM call against
the AXTree" becomes "Claude Code reasons over the snapshot text it already has." The product's cost center
(server-side inference) evaporates because the host model is free to the skill.

---

## 5 — Porting Stagehand's act / extract / observe (keyless)

Stagehand's three primitives are each "one LLM call against the page's accessibility tree." The verbatim
prompts (KNOWN from `BROWSERBASE_PRODUCT_CODE.md:4259-4367`) are reproduced below, then mapped onto
agent-browser + Claude Code so the LLM call is *Claude Code itself*.

### 5.1 act — "do this action on the page" (KNOWN prompt)
```
You are helping the user automate the browser by finding elements based on what action the user wants to take
on the page. You will be given: 1. a user defined instruction about what action to take 2. a hierarchical
accessibility tree showing the semantic structure of the page. The tree is a hybrid of the DOM and the
accessibility tree. Return the element that matches the instruction if it exists. Otherwise, return an empty
object.
```
Output schema (`ActResponseSchema`, `BROWSERBASE_PRODUCT_CODE.md:4302`): `{elementId:"frameOrdinal-backendNodeId",
description, method ∈ {click,fill,type,selectOptionFromDropdown,focus,hover}, arguments[], twoStep}`. There's a
dropdown special case (`ACT_DROPDOWN_INSTRUCTION`, `:4288`): `<select>` → `selectOptionFromDropdown` with exact
option text; non-select → click the closest node (even StaticText), `twoStep=true`.

**Keyless reimplementation (DESIGNED):** `act("instruction")` becomes a Claude Code micro-routine:
1. `agent-browser snapshot -i --json` (the "hybrid accessibility tree" — exactly what Stagehand feeds the LLM,
   produced locally per §2).
2. Claude Code reasons over the snapshot with the act prompt's logic: find the `@eN` matching the instruction;
   pick a method (button/link→`click`, text input→`fill`, `<select>`→`select`, etc.).
3. Emit the agent-browser command. `elementId` (Stagehand's `frameOrdinal-backendNodeId`) maps to our `@eN`
   ref — the same backendNodeId, just named differently. The dropdown rule maps to: snapshot shows
   `role=combobox`/`role=listbox` → `agent-browser select @eN "option text"`; non-native dropdown (`role=button`
   that opens a menu) → `click @eN`, re-snapshot, `click @eM` on the option (the "twoStep" pattern).

### 5.2 extract — "pull structured/typed data" (KNOWN prompt)
```
You are extracting content on behalf of a user. If a user asks you to extract a 'list' of information, or 'all'
information, YOU MUST EXTRACT ALL OF THE INFORMATION THAT THE USER REQUESTS. You will be given: 1. An
instruction 2. A list of DOM elements to extract from. Print the exact text from the DOM elements with all
symbols, characters, and endlines as is. Print null or an empty string if no new information is found. ONLY
print the content using the print_extracted_data tool provided. (Anthropic only) If a user is attempting to
extract links or URLs, you MUST respond with ONLY the IDs of the link elements. Do not attempt to extract links
directly from the text unless absolutely necessary.
```
Stagehand pairs this with a chunked-completion loop + a `METADATA_SYSTEM_PROMPT` (`:4330`) that decides if the
extraction is `completed` (stop) or needs more chunks (`progress`, `completed` booleans). And a Zod/JSON schema
defines the typed output shape.

**Keyless reimplementation (DESIGNED) — two modes:**

- **Mode A — snapshot/get extraction (no JS):** feed `agent-browser snapshot --json` (full tree, refs +
  names) to Claude Code with the user's schema. Claude Code reads the names directly off the tree and fills the
  schema. For exact text of a node, `agent-browser get text @eN`. For links, the rule "respond with only the
  IDs of link elements" maps to: snapshot with `-u` (link hrefs included, `snapshot.rs:416`), or
  `get attr @eN href`. The "extract ALL of a list" rule is enforced by Claude Code's own reasoning over the
  full (non-`-i`) tree.

- **Mode B — `eval` extraction (typed, arbitrary shape):** for tabular/repeated data, generate JS and run it
  via `eval --stdin` (heredoc). This is the *deterministic* extraction — no LLM ambiguity, exact text:
  ```bash
  cat <<'EOF' | agent-browser eval --stdin
  const rows = document.querySelectorAll("table tbody tr");
  Array.from(rows).map(r => ({
    name: r.cells[0].innerText.trim(),
    price: r.cells[1].innerText.trim(),
  }));
  EOF
  ```
  (KNOWN-as-pattern from `SKILL.md:224-231`.) Claude Code writes the selector JS by *looking at the snapshot
  first* (so it knows the table structure), runs it, gets back a JSON array, validates it against the schema.
  `eval -b <base64>` for scripts with quotes/special chars (`commands.rs:745-777`).

- **The metadata/completion loop** maps to Claude Code's own judgment: after extraction, ask "did I get all the
  rows the user wanted? Is there a 'next page'/'load more' in the snapshot?" If yes → `click @eN` (next),
  re-snapshot, extract again, merge. This is the chunked-extraction loop without a second paid LLM call.

- **Pagination/long pages:** Stagehand chunks the AXTree because of `ARIA_TREE_MAX_TOKENS=70000`. We chunk by
  *scrolling* (`scroll down 1000` → re-snapshot, `SKILL.md:357-366`) or by `snapshot -s "#main"` scoping
  (`snapshot.rs:234`) to fit Claude Code's context, accumulating results across scrolls/sections.

### 5.3 observe — "what can I do / what's here" (KNOWN prompt)
```
You are helping the user automate the browser by finding elements based on what the user wants to observe in
the page. You will be given: 1. a instruction of elements to observe 2. a hierarchical accessibility tree…
Return an array of elements that match the instruction if they exist, otherwise return an empty array. When
returning elements, include the appropriate method from the supported actions list.
```
Output `ObserveResponseSchema` (`:4360`): array of `{elementId, description, method, arguments}`.

**Keyless reimplementation (DESIGNED):** `observe` is literally `agent-browser snapshot -i --json` + Claude
Code filtering the ref list to those matching the instruction, annotating each with a method. No extra call —
`observe` and the perception step of the loop are the same operation. (This is why the agent-browser core loop
*is* observe: snapshot → reason → act.)

### 5.4 Constants we drop vs keep
KNOWN Stagehand constants (`BROWSERBASE_PRODUCT_CODE.md:4267-4271`): `ARIA_TREE_MAX_TOKENS=70000`,
`ARIA_TREE_MAX_CHARS=280000`, `ACT_TEMPERATURE=0.1`, `EXTRACT_TEMPERATURE=0.1`, `AGENT_TEMPERATURE=1`.
- **Drop the temperatures** — we don't set a sampling temperature on Claude Code; the skill prompt does the
  steering. (Low-temp determinism is approximated by the deterministic `eval` path and the deterministic
  ref-grounding in §2.3.)
- **Keep the token budget as a chunking heuristic** — when a snapshot would blow Claude Code's context, scope
  with `-s`, cap with `-d`, or scroll-chunk (§5.2). 70k tokens ≈ the size at which to start chunking.

---

## 6 — Porting AgentQL's AQL query DSL (keyless, selector-free typed extraction)

AgentQL's whole value is a tiny declarative query language: you write the *shape* of the data you want, and the
engine (LLM + grounding) maps your field names to real elements on the page and returns typed data. It's the
cleanest "structured extraction" primitive of the three products, and it ports onto agent-browser beautifully
because both speak "accessibility tree → typed result."

### 6.1 The AQL grammar (KNOWN verbatim from the installed `agentql==1.18.1` SDK)

Source: `agentql/_core/_syntax/` (lexer.py, parser.py, node.py, token_kind.py) — documented in
`AGENTQL_GAP_02_GRAMMAR.md` and reconstructed runnable in `AGENTQL_PRODUCT_CODE.md:1229-1338`.

**Grammar (EBNF, KNOWN — `AGENTQL_PRODUCT_CODE.md:1240-1247`):**
```
Query       ::= '{' NodeList '}'
NodeList    ::= Node ((',' | NEWLINE) Node)*
Node        ::= IDENTIFIER Description? (Container | List | epsilon)
Description ::= '(' DescContent ')'
DescContent ::= (Letter | Digit | Symbol | WS | '(' DescContent ')')*
Container   ::= '{' NodeList '}'
List        ::= '[]' Container?
IDENTIFIER  ::= [a-zA-Z_][a-zA-Z0-9_]*
```

**Token kinds (KNOWN — 10 values, `AGENTQL_GAP_02_GRAMMAR.md` §1):** `SOF, EOF, BRACE_L {, BRACE_R },
BRACKET_L [, BRACKET_R ], IDENTIFIER, DESCRIPTION, COMMA, NEWLINE`. **Zero reserved words** — `query`,
`select`, `from`, `true`, `null` are all legal identifiers; the language is GraphQL-selection-set-shaped, not
SQL. `COMMA` is optional between siblings (newline/whitespace separates). `NEWLINE` is emitted for line-counting
then filtered (`IGNORED_TOKENS`).

**Four AST node types (KNOWN — `AGENTQL_PRODUCT_CODE.md:1295-1337`):**
| Node | AQL syntax | Meaning |
|---|---|---|
| `IdNode` | `search_btn` or `search_btn(the big blue one)` | one element; optional `(...)` description disambiguates |
| `IdListNode` | `links[]` | a list of like elements |
| `ContainerNode` | `nav { home_link about_link }` | a scoped group (and the root query) |
| `ContainerListNode` | `products[] { name price }` | a list of structured objects |

The `(description)` in parens is free-text the LLM uses to pick the right element when the field name is
ambiguous (`price(sale price not list price)`). Descriptions can nest parens (`DescContent` recursion).

**Example queries (KNOWN — canonical AgentQL shapes):**
```
{ search_box  search_button }                          # two elements
{ products[] { name  price  rating } }                 # list of objects
{ login_form { username_input  password_input  submit_button } }
{ nav_links[]  footer { copyright  privacy_link } }    # mixed list + container
```

**The wire format (KNOWN — `AGENTQL_GAP_02_GRAMMAR.md` preamble):** there is NO separate serializer. The wire
payload is the **AQL string itself** (the un-minified pretty form), embedded as a JSON string field alongside
the accessibility tree. `Node.dump()` round-trips the AST back to the string.

### 6.2 What AgentQL does server-side with `(tree, query)` (KNOWN, `AGENTQL_PRODUCT_CODE.md`)

`/api/v2/query` ("element location": query → element refs/`tf623_id`) and `/api/v2/query-data` ("data
extraction": query → text values). Pipeline (`pipeline.py`, `run_element_query`): parse AQL → build prompt with
the serialized accessibility tree + the query → one LLM call → **grounding.py** = deterministic post-LLM
validation that every returned ref actually exists in the tree (catches hallucinated elements). Result cached
by `compute_tree_hash(tree) + query + mode`. The AQL query is validated at request time
(`field_validator("query")` runs `QueryParser(v).parse()`, `AGENTQL_PRODUCT_CODE.md:184-190`).

### 6.3 Keyless reimplementation (DESIGNED): AQL on agent-browser + Claude Code

The keyless port keeps AQL as the *user-facing extraction spec* but makes Claude Code the resolver and
agent-browser the tree source + grounder. Two pieces:

**(a) The query language — port the parser verbatim.** `AGENTQL_PRODUCT_CODE.md:1229-1338` is a complete,
runnable Python recursive-descent parser for exactly this grammar. The skill ships it as-is (it's ~250 lines,
no deps). The skill accepts an AQL string from the user (or Claude Code writes one), validates it with the
parser, and walks the AST.

**(b) The resolver — Claude Code instead of a paid LLM.** Replace the AgentQL server's "build prompt with tree
+ query → call GPT/Claude over the network" with:
1. `agent-browser snapshot --json` → the accessibility tree + the `refs` map
   (`{"e1":{"role":"heading","name":"…"},…}`, KNOWN output shape `README.md:913`).
2. Claude Code maps each AQL leaf field (`name`, `price`, …) to a `@eN` ref by matching the field
   name + its `(description)` against the snapshot's role/name lines. For `[]` lists, it finds the repeated
   structure (e.g. all `@eN` under each `listitem`/`article`/`row`).
3. **Grounding (keep this — it's the deterministic safety net):** every ref Claude Code picks MUST exist in the
   snapshot's `refs` map. If Claude Code names a ref not in the map → reject and re-snapshot. This is
   agent-browser's own stale-ref re-resolution (`element.rs:340`) plus AgentQL's grounding, fused: a ref is
   valid iff it round-trips through `Accessibility.getFullAXTree`.
4. Pull values: `query` mode → return the `@eN` refs; `query-data` mode → `get text @eN` per leaf (or batch via
   one `eval --stdin` that reads all the resolved elements at once for speed).

**Why AQL beats raw "extract instruction" for typed data (DESIGNED rationale):** the field names ARE the schema
keys, the `[]` ARE the array markers, the `{}` ARE the nesting — so the output JSON shape is fully determined by
the query, with no separate Zod/JSON-schema needed and no free-form LLM drift in the *structure* (only in the
*element selection*, which grounding validates). It's the most token-efficient of the three extraction styles.

### 6.4 Minimal AQL → JSON example (DESIGNED, end-to-end keyless)

User asks: "get every product's name and price from this page."
```bash
agent-browser open https://shop.example.com/category && \
  agent-browser wait --load networkidle
agent-browser snapshot --json   # Claude Code reads tree + refs
```
Claude Code writes the AQL: `{ products[] { name  price } }`, validates it with the ported parser, then
resolves: finds the repeating `article`/`listitem` blocks in the snapshot, maps `name`→the heading ref and
`price`→the ref whose name looks like currency in each block, grounds each ref against the `refs` map, and emits
one `eval` to read them:
```bash
cat <<'EOF' | agent-browser eval --stdin
Array.from(document.querySelectorAll('[data-product], li.product, article.product')).map(el => ({
  name: el.querySelector('h2,h3,.name')?.innerText.trim() ?? null,
  price: el.querySelector('.price,[class*="price"]')?.innerText.trim() ?? null,
})).filter(p => p.name)
EOF
```
→ returns a typed JSON array matching the AQL shape. The selectors come from *reading the real snapshot first*,
so they're grounded, not guessed.

---

## 7 — The escalation ladder (DESIGNED — when each rung fires)

Formalized decision procedure for the skill. Always start cheap; escalate only on a concrete signal.

```
fetch(url, goal):
  # RUNG 1 — httpx (static)
  html = httpx.get(url)
  if goal_satisfiable(html) and not needs_js(html):        # has the data, no client-render shell
      return extract_static(html)                          # $0, ~100ms

  # RUNG 2 — crawl4ai (local JS render → markdown), single page, NO interaction
  if needs_js(html) and not needs_interaction(goal):
      md = crawl4ai.fit_markdown(url)                       # local Chromium, $0
      if goal_satisfiable(md): return extract_markdown(md)

  # RUNG 3 — agent-browser (local, interactive / typed / login / multi-step)
  agent-browser open <url>; wait --load networkidle
  loop (the §4.2 ReAct loop):
      snapshot -i --json                                   # perceive (= Stagehand observe)
      if goal needs login:        do auth (§3.6: --profile / cookies set --curl / auth login)
      if goal needs navigation:   click @eN / fill @eN / press Enter ; wait <signal> ; re-snapshot
      if goal needs typed data:   AQL-resolve (§6.3) or eval --stdin (§5.2 Mode B)
      until goal_satisfied or max_steps
  return result
```

**Signals (INFERRED heuristics):**
- `needs_js`: body is a near-empty `<div id="root">` / `<div id="__next">` shell, or content count after parse
  is implausibly low for the page title. (Also: rung-1 returned a 200 but the data isn't in the HTML.)
- `needs_interaction`: goal mentions login, "click", "next page", "load more", form submission, filtering, a
  date-picker, or the data is behind a tab/accordion.
- **Cheapest-win shortcut:** before rung 3's loop, run `agent-browser network requests --type xhr,fetch` after
  one navigation — if the page hydrates from a clean JSON API, grab that endpoint and drop back to **rung 1**
  (httpx the API directly). Often the whole "agentic browse" collapses to one API call.

**Parallelism (KNOWN, `SKILL.md:261-271`):** `--session a` / `--session b` are isolated browsers (own
cookies/refs). For scraping N independent pages, fan out N sessions. Each is still local + keyless.

---

## 8 — Auth, paywalls, anti-bot — keyless tactics (KNOWN + DESIGNED)

These are the cases that *seem* to require a paid cloud browser. They don't, in most realistic skill use:

- **Login once, reuse forever (KNOWN, `SKILL.md:196-210`):** log in interactively (or via `auth login`), then
  `state save ./auth.json`; later runs `--state ./auth.json open …` start already-authenticated. Or
  `--session-name <app>` auto-persists. This is the keyless equivalent of Browserbase's encrypted-S3 "context"
  (`03_BROWSE_EXTRACT.md` §1.1; `BROWSERBASE_PRODUCT_CODE.md` AES-256-CBC user-data-dir) — same idea, stored
  locally, optionally AES-256-GCM encrypted with `AGENT_BROWSER_ENCRYPTION_KEY`.
- **Reuse your real browser's session (KNOWN, `README.md:549-567`):** `--profile Default` copies your existing
  Chrome profile (read-only snapshot) so you're logged into Gmail/etc. with zero setup. Or `--auto-connect` to
  attach to an already-running Chrome you logged into manually.
- **Paywall via cookies (KNOWN, `README.md:269`):** `cookies set --curl cookies.curl` imports a Copy-as-cURL
  dump / JSON array / bare Cookie header — the user logs in in their own browser, copies the request as cURL,
  the skill replays the cookies. The LLM never sees credentials.
- **Header auth (KNOWN, `README.md:964-985`):** `--headers '{"Authorization":"Bearer …"}'`, origin-scoped (not
  leaked cross-domain). Skips the login UI entirely for API-style auth.
- **Real-input fidelity (KNOWN, §2.4):** because clicks/types are real CDP `Input.dispatch*` events at real
  coordinates (not `el.click()`), naive bot-detection that checks for synthetic events is already defeated.
  `--user-agent`, `--proxy`, `--viewport`/`set device`, `--args` cover UA/proxy/fingerprint basics, all local.
- **Where keyless genuinely ends (INFERRED):** sites requiring residential-IP rotation, CAPTCHA-solving
  services, or a "verified fingerprint" farm. agent-browser *supports* delegating those to a paid provider
  (`-p browserbase|kernel`, with stealth/CAPTCHA flags — `README.md:1411-1489`), but that crosses the keyless
  line and is **out of scope** for the Bad Research skill. For research targets (docs, news, listings, dashboards
  the user can log into), the keyless path covers the realistic surface.

---

## 9 — Is agent-browser's local mode truly keyless? (CONFIRMED) + when a key is ever needed

**CONFIRMED keyless** for the default local path: `install` pulls Chrome-for-Testing with no account; the daemon
drives it over local CDP; `open/snapshot/click/fill/eval/...` make zero network calls to any paid service. The
only network egress is to the *target site you're browsing*. Verified by: `providers.rs` reads env keys ONLY
inside `connect_provider`, which is ONLY reached when `-p <provider>` is passed (`providers.rs:26-70`); and the
only other key reader is `cli/src/chat.rs` for the optional `chat` command (`AI_GATEWAY_API_KEY`).

**A key/cloud is needed only if you opt into one of these (all avoided):**
| Trigger | Key | Why we skip it |
|---|---|---|
| `-p browserbase` | `BROWSERBASE_API_KEY` | remote browser; we use local Chrome |
| `-p browserless` | `BROWSERLESS_API_KEY` | remote browser |
| `-p browseruse` | `BROWSER_USE_API_KEY` | remote browser |
| `-p kernel` | `KERNEL_API_KEY` | remote browser (stealth/CAPTCHA) |
| `-p agentcore` | AWS SigV4 creds | remote browser |
| `chat "…"` command | `AI_GATEWAY_API_KEY` | Claude Code replaces this loop (§4) |

`AGENT_BROWSER_ENCRYPTION_KEY` is *not* an API key — it's a locally-generated AES-256-GCM key for state-at-rest
(`README.md:617`), auto-generated at `~/.agent-browser/.encryption-key` if unset. No external service.

---

## 10 — Verbatim quick-reference (the load-bearing artifacts to copy into the skill)

**(A) agent-browser core loop (KNOWN, `skill-data/core/SKILL.md:20-30`):**
```
agent-browser open <url>        # 1. Open a page
agent-browser snapshot -i       # 2. See what's on it (interactive elements only)
agent-browser click @e3         # 3. Act on refs from the snapshot
agent-browser snapshot -i       # 4. Re-snapshot after any page change
```
Refs go stale on every page change (navigate, submit, re-render, dialog) — ALWAYS re-snapshot first.

**(B) JSON agent mode (KNOWN, `README.md:911-913`):**
```
agent-browser snapshot -i --json
# {"success":true,"data":{"snapshot":"…","refs":{"e1":{"role":"heading","name":"Title"},…}}}
```
The `refs` map is the grounding source: a ref is valid iff it's a key here.

**(C) Stagehand prompts to embed (KNOWN, §5):** ACT/EXTRACT/OBSERVE/METADATA system prompts verbatim above
(`BROWSERBASE_PRODUCT_CODE.md:4279-4353`). Use EXTRACT's "extract ALL / print exact text / links→IDs only"
rules as the skill's extraction contract.

**(D) AQL parser to port (KNOWN, §6):** `AGENTQL_PRODUCT_CODE.md:1229-1338` — complete runnable
recursive-descent parser for the 10-token, 4-node grammar. Ship verbatim.

**(E) `eval --stdin` extraction template (KNOWN pattern, `SKILL.md:224`):** heredoc JS returning a JSON array —
the deterministic typed-extraction escape hatch. Write the selectors by reading the snapshot first.

**(F) Skill system-prompt seed (KNOWN, `stream/chat.rs:136-148`):** "You MUST run the command for every browser
action; never claim an action without running it; honestly say when something's out of scope; re-snapshot after
changes." Keep these rules; drop the `--json`-ban and command-allowlist (those are for an untrusted LLM; Claude
Code is trusted and `--json` is useful).

---

## 11 — Gaps I could not resolve

- **No live agent-browser run in this dossier.** The CLI is a Rust binary that requires `cargo build` +
  `agent-browser install` (downloads Chrome). I read the source line-by-line but did not execute it here; the
  command surface and snapshot algorithm are KNOWN-from-source, not KNOWN-from-trace. The skill should do one
  live smoke test (`open example.com && snapshot -i`) on first install.
- **`crawl4ai` ↔ `agent-browser` handoff details** (cookie/profile sharing between rung 2 and rung 3) are
  DESIGNED, not verified. Both can load a profile dir; whether crawl4ai's `~/.crawl4ai/profiles/<name>` is
  byte-compatible with agent-browser's `--profile <path>` is untested (likely not — different Chrome user-data
  layouts; safer to do auth in agent-browser and `state save`).
- **AQL list-structure detection** (finding the repeating block for `products[]`) is the one place Claude Code's
  reasoning carries real risk of mis-grouping; the grounding step catches *bad refs* but not *bad grouping*. A
  calibration pass against real listing pages (compare AQL output to a hand-labeled set) is the right way to
  measure this; not done here.
- **Token cost of full (non-`-i`) snapshots on large pages** — I cite Stagehand's 70k-token heuristic as the
  chunking trigger but did not measure agent-browser snapshot sizes on real heavy pages. Scope/scroll-chunk
  strategy (§5.2) is the mitigation; the exact thresholds need calibration.
- **Lightpanda engine** (`--engine lightpanda`) is an even-lighter keyless browser option mentioned throughout
  the source (`cli/src/native/cdp/lightpanda.rs`) but I did not deep-read it; it may be a faster keyless backend
  than full Chrome for simple pages. Worth a follow-up. **→ RESOLVED in §12.**
- **Keyless authed scraping** (login-walled / bot-protected sources without a paid proxy) was sketched in §8
  but the concrete persist-and-reuse flow and the crawl4ai↔agent-browser handoff were left untested.
  **→ RESOLVED in §13.**

---

## 12 — Lightpanda engine: deep-read + verdict (KNOWN, two repos cloned at HEAD)

**Sources read for this section (both cloned `--depth=1`, read line-by-line, then deleted):**
- `vercel-labs/agent-browser` → the lightpanda integration: `cli/src/native/cdp/lightpanda.rs` (496 L, full),
  `cli/src/native/browser.rs` (engine dispatch + `validate_lightpanda_options`), `cli/src/flags.rs`
  (`--engine`/`AGENT_BROWSER_ENGINE`), `cli/src/native/cdp/types.rs` (AX-tree compat shim), `CHANGELOG.md`,
  `docs/src/app/engines/lightpanda/page.mdx`.
- `lightpanda-io/browser` → the engine itself: `README.md`, `src/` tree, `src/cdp/domains/` (every CDP domain
  file), `src/cdp/domains/page.zig`, `src/cdp/domains/{accessibility,input,runtime,dom}.zig`, `src/cookies.zig`,
  `src/SemanticTree.zig`, `src/cdp/AXNode.zig`.

### 12.1 What lightpanda is (KNOWN, `lightpanda-io/browser` `README.md`)

A **headless browser engine written from scratch in Zig** — *not* a Chromium fork or WebKit patch
(`README.md:6-8`). It uses real **V8** for JS (`README.md:191`, `build.zig.zon` depends on
`chromium.googlesource.com/v8`), **html5ever** (Servo's Rust HTML parser) for parsing, and **libcurl** for
HTTP (`README.md:185-187`). It is **AGPL-3.0** (`LICENSE`, headers in every `.zig` file) — relevant if the Bad
Research skill ever *redistributes* a lightpanda binary; just *invoking* it as a separate process is fine.

**KNOWN — it is keyless and local, exactly like Chrome-for-Testing:** the binary is a single static download
from GitHub releases (`README.md:60-78`: `curl -L .../nightly/lightpanda-aarch64-macos`), or `brew install
lightpanda-io/browser/lightpanda`, or `docker run lightpanda/browser:nightly`. No account, no token. It runs a
**local CDP server** (`lightpanda serve --host 127.0.0.1 --port 9222`, `README.md:113-116`) that any CDP client
(Puppeteer/Playwright/agent-browser) connects to over a local WebSocket. The only network egress is to the
target site. **INFERRED caveat (keyless-relevant):** lightpanda ships **telemetry ON by default**
(`README.md:163-165`) — set `LIGHTPANDA_DISABLE_TELEMETRY=true` to silence it. Not a paid key, but worth
disabling for a research tool.

**KNOWN — the speed/memory claim, from lightpanda's own benchmark** (`README.md:30-37`, 933 real pages on an
AWS `m5.large`): peak memory for 100 pages **123 MB vs Chrome's 2 GB (~16× less)**; execution time for 100
pages **5 s vs 46 s (~9× faster)**. (The marketing "10× lighter / 10× faster" is this benchmark rounded.) The
mechanism: no rendering/layout/paint engine, no GPU process, no multi-process Chromium overhead — just
parse → DOM → V8 → CDP.

### 12.2 How agent-browser drives it (KNOWN, `vercel-labs/agent-browser`)

`--engine lightpanda` (or `AGENT_BROWSER_ENGINE=lightpanda`, or `{"engine":"lightpanda"}` in
`agent-browser.json`) landed in **v0.20.0 (#646)** and implies `--native` mode (`CHANGELOG.md:645`,
`flags.rs:481`, `flags.rs:761`). The selection is a plain string match in `BrowserManager::launch`
(`browser.rs:316`): `"chrome"` (default) | `"lightpanda"` | else → `"Unknown engine '{}'. Supported engines:
chrome, lightpanda"` (`browser.rs:332-336`).

For lightpanda, agent-browser **spawns and supervises the engine itself** — it does NOT require you to start
`lightpanda serve` manually (`lightpanda.rs:149` `launch_lightpanda`):
1. **Locate the binary** (`find_lightpanda`, `lightpanda.rs:104`): `which lightpanda` / `where` on Windows, then
   `~/.lightpanda/lightpanda`, then `~/.local/bin/lightpanda`. Override with `--executable-path`. If absent:
   `"Lightpanda not found. Install it from https://lightpanda.io/docs/open-source/installation or use
   --executable-path."` (`lightpanda.rs:155`).
2. **Pick a free port** (`lightpanda.rs:159`: bind `127.0.0.1:0` to get an OS-assigned port), then spawn
   `lightpanda serve --host 127.0.0.1 --port <p> --timeout 604800` (the 1-week session max, hard-coded
   `LIGHTPANDA_SESSION_TIMEOUT_SECS = 604800`, `lightpanda.rs:14`; `--http_proxy <p>` appended iff a proxy is set,
   `lightpanda.rs:54`).
3. **Wait for CDP readiness** (`wait_for_lightpanda_ready`, `lightpanda.rs:234`): poll the `/json/version`
   endpoint every 100 ms for the `webSocketDebuggerUrl`, up to a **10 s startup timeout**
   (`LIGHTPANDA_STARTUP_TIMEOUT`, `lightpanda.rs:11`); surface the child's last 40 stdout/stderr lines on failure
   (`MAX_LOG_LINES = 40`).
4. **Attach + init targets** (`initialize_lightpanda_manager`, `browser.rs:1584`): a 5 s CDP-connect timeout +
   10 s `Target`-domain-init timeout, because lightpanda's `Target` domain comes up slightly after the socket.
5. **Drop = kill** (`impl Drop for LightpandaProcess`, `lightpanda.rs:30`): the child is SIGKILLed when the
   daemon drops it. No orphaned process.

**One compatibility shim worth knowing** (KNOWN, `cdp/types.rs:5-7`, `CHANGELOG.md:567`, #775): lightpanda
sends **numeric** `nodeId`/`childIds` in `Accessibility.getFullAXTree` responses where Chrome sends **strings**;
agent-browser deserializes with a `string_or_int` helper so the *same* snapshot-builder (`snapshot.rs`, §2.2)
works against both engines unchanged. This is the proof that the §2 snapshot primitive is engine-portable.

### 12.3 Which of our keyless primitives actually work on lightpanda (KNOWN, from `src/cdp/domains/`)

Lightpanda implements the exact CDP domains the §4.2 loop + §5/§6 extraction depend on. Verified present in
`lightpanda-io/browser/src/cdp/domains/`:

| Our primitive (this dossier) | CDP method | lightpanda support |
|---|---|---|
| `snapshot` perception (§2.2) | `Accessibility.getFullAXTree` | ✅ `accessibility.zig:35,47` (+ `queryAXTree`, `SemanticTree.zig`, `AXNode.zig`) |
| ref→element grounding (§2.3) | `DOM.getDocument/querySelector(All)/describeNode/resolveNode/getBoxModel` | ✅ `dom.zig:38-67` |
| `click` (§2.4) | `Input.dispatchMouseEvent` | ⚠️ partial — `input.zig:80` handles only `mousePressed` via `frame.triggerMouseClick(x,y)`; `mouseMoved`/`mouseReleased`/`mouseWheel` are **silently dropped** (`input.zig:98-101`). So **click works, `hover` is a no-op, real `drag`/`scroll`-by-wheel don't** |
| `fill`/`type` (§2.4) | `Input.insertText` / `Input.dispatchKeyEvent` | ✅ `input.zig:24-32` |
| `eval` extraction (§5.2 Mode B, §6.3) | `Runtime.evaluate` / `callFunctionOn` | ✅ `runtime.zig:33-85` (real V8) |
| cookies/headers auth (§13) | `Network.setCookies` / `Network.setExtraHTTPHeaders` / `Fetch` interception | ✅ `network.zig`, `fetch.zig`, `src/cookies.zig` |
| `screenshot` / `pdf` | `Page.captureScreenshot` / `Page.printToPDF` | ❌ **FAKE** — both return a hard-coded embedded placeholder, NOT a real render: `page.zig:863` "Return a fake screenshot" → `base64Encode(@embedFile("screenshot.png"))`; `printToPDF` → `@embedFile("screenshot.pdf")` (`page.zig:23-24,896,904`). There is no layout/paint engine, so pixels are impossible. This is the load-bearing limitation. |

**The agent-browser docs say this plainly** (`docs/.../engines/lightpanda/page.mdx:64-80`): Extensions,
**Persistent profiles (`--profile`)**, **Storage state (`--state`)**, file access, and headed mode are **"Not
supported"**; Screenshots are "Depends on Lightpanda CDP support" (which, per the source above, means "returns a
placeholder"). agent-browser **enforces** this at launch — `validate_lightpanda_options` (`browser.rs:62`)
returns a hard error for any of: `--profile` ("Profiles are not supported with Lightpanda"), `--state`/
storage_state, extensions, `--allow-file-access`, headed mode, `--args`.

### 12.4 The two big functional gaps for *research* scraping (KNOWN)

1. **No `--profile` / `--state`** → you cannot reuse a logged-in Chrome profile or replay a Playwright
   storage-state JSON (`browser.rs:71-76`). The keyless **localStorage/sessionStorage** half of an authed session
   (§13) is therefore unavailable. *Cookies* can still be injected via `Network.setCookies` (lightpanda
   implements it + `src/cookies.zig` even loads/saves a cookie-jar JSON), so **cookie-only** auth still works;
   token-in-localStorage auth does not.
2. **CORS not yet implemented** (`README.md:159`, #2015 open). Pages that fetch their data from a *different*
   origin via XHR/fetch with CORS preflight may fail to hydrate on lightpanda where they'd succeed on Chrome.
   Combined with "hundreds of Web APIs… coverage will increase over time" (`README.md:170`) and Beta status
   (`README.md:152`), expect a non-trivial slice of heavy SPAs to render incompletely.

### 12.5 Verdict — **use lightpanda for a SUBSET (default fast rung-2.5), Chrome for the rest**

Not "default for everything" (screenshots + profiles + CORS gaps are too common in research targets), and not
"skip" (the 9×/16× win on simple JS pages is real and free). Concretely, slot it **between crawl4ai and
full-Chrome agent-browser** as a fast keyless tier:

- **USE lightpanda when:** the page needs JS execution (so rung-1 httpx and even rung-2 crawl4ai-without-JS
  fail) but is *static-ish after hydration* — docs sites, blogs, listing/search pages, JSON-rendering SPAs that
  don't depend on cross-origin CORS — **and** the goal is text/DOM extraction (`snapshot` + `eval`), **and** no
  login-via-profile and no screenshot are needed. This is the bulk of "render this JS page and give me the
  data" research work. `agent-browser --engine lightpanda open <url> && agent-browser --engine lightpanda
  snapshot -i` then `eval --stdin` (§5.2). 9× faster / 16× lighter than Chrome here, so it's the right default
  for high-volume parallel fan-out (§7).
- **FALL BACK to `--engine chrome` (default) when:** you need a **screenshot/PDF** (lightpanda fakes them); a
  **persistent profile or `--state` reuse** for login (§13 — blocked on lightpanda); **`hover`/`drag`** menus
  (lightpanda's `dispatchMouseEvent` drops `mouseMoved`); a **CORS-heavy SPA** that won't hydrate; or any page
  where lightpanda's partial Web-API coverage returns an empty/incomplete snapshot.
- **Detection heuristic (DESIGNED):** try lightpanda first for a rung-3 JS page; if the snapshot is implausibly
  empty (near-zero refs for a page with a real title) or `console`/`errors` show unimplemented-API throws, **fall
  back to the same command with `--engine chrome`**. One retry, same command surface — because the snapshot/
  click/fill/eval interface is byte-identical across engines (that's the whole point of the CDP-portable design
  in §2 + the §12.2 type shim).

**Keyless reimplementation:** ship the skill with a 4-rung ladder (revise §7): rung-1 httpx → rung-2 crawl4ai →
**rung-2.5 `agent-browser --engine lightpanda`** (fast keyless JS render + DOM/`eval` extraction) → rung-3
`agent-browser --engine chrome` (screenshots, profile/state auth, hover/drag, CORS-heavy SPAs). Install
lightpanda once via the GitHub-release `curl` (or `brew`), set `LIGHTPANDA_DISABLE_TELEMETRY=true`, and let the
engine fall back to chrome on an empty/error snapshot. Both engines are 100% keyless and local.

---

## 13 — Keyless anti-bot + authed scraping (login-walled / bot-protected research sources)

The question: reach a login-walled or bot-protected source **without a paid proxy or anti-bot SaaS**. The
answer is agent-browser's **persist-once-reuse-forever** session model on the **local Chrome** engine — log in a
single time (human or scripted), persist the resulting cookies + storage, and replay it on every later run.
KNOWN mechanics below, then the concrete flow, then honest limits.

### 13.1 The four keyless auth on-ramps (KNOWN, `vercel-labs/agent-browser`)

All four run against **local Chrome** ($0). They differ in where the credential comes from:

1. **`state save` / `--state` (Playwright-compatible storage state) — the primary mechanism.** `state.rs:17-38`
   defines `StorageState { cookies: Vec<Cookie>, origins: Vec<OriginStorage{ origin, local_storage,
   session_storage }> }` — i.e. it captures **cookies + per-origin localStorage + sessionStorage**, the complete
   auth surface (most modern apps keep the session token in a cookie *or* localStorage; this grabs both).
   `save_state` walks every visited frame origin (`collect_frame_origins`, `state.rs:40`), `eval`s
   `localStorage`/`sessionStorage` per origin, and writes a JSON file. `state load`/`--state <path>` replays it:
   cookies via `Network.setCookies` (`state.rs:376`) and storage via per-origin `eval`. Optionally
   **AES-256-GCM encrypted at rest** (`state.rs:1` `aes_gcm`, keyed by `AGENT_BROWSER_ENCRYPTION_KEY`, auto-gen
   at `~/.agent-browser/.encryption-key`). This is the keyless equivalent of Browserbase's encrypted-S3
   "context" — same idea, stored on your own disk.
2. **`--session-name <name>` — auto-persist.** Any command with `--session-name app` auto-saves cookies +
   localStorage to `~/.agent-browser/sessions/<name>` on exit and auto-restores on the next run. Zero explicit
   save/load calls — log in once under a name, and every later `--session-name app` run is already
   authenticated.
3. **`cookies set --curl <file>` — replay a Copy-as-cURL dump (the no-automation path).** The user logs in *in
   their own everyday browser*, opens DevTools → Network → right-clicks the authed request → "Copy as cURL",
   saves it to a file; the skill runs `agent-browser cookies set --curl cookies.curl` → `Network.setCookies`
   (`cookies.rs:62-86`). It also accepts a JSON cookie array or a bare `Cookie:` header. **The LLM never sees
   the password** — only the resulting cookies. Best for sites where scripting the login form is brittle (SSO,
   MFA, CAPTCHA-on-login).
4. **`--profile <name|path>` — borrow your real Chrome's logins.** Copies your existing Chrome profile
   (read-only snapshot of its cookie/login DB) so you start already-signed-in to Gmail/GitHub/etc. with zero
   setup. Or `--auto-connect`/`connect <port>` to attach to a Chrome you already launched and logged into
   manually.

Plus **`--headers '{"Authorization":"Bearer …"}'`** (`network.rs:19` → `Network.setExtraHTTPHeaders`,
origin-scoped, not leaked cross-domain) for API-token auth that skips the login UI entirely, and `auth
save|login <name>` for an encrypted local credential vault that feeds a scripted form-fill without exposing the
secret to the model.

### 13.2 The concrete keyless authed-fetch flow (DESIGNED, end-to-end)

**One-time login (interactive — the robust path for SSO/MFA/CAPTCHA):**
```bash
# Launch HEADED local Chrome so a human can complete login (incl. MFA/CAPTCHA) once:
agent-browser --headed open https://research-source.example/login
#   ... human types credentials / solves MFA in the real window ...
agent-browser wait --url "**/dashboard"          # concrete post-login signal
agent-browser state save ./auth/source.json      # cookies + localStorage + sessionStorage, optionally AES-GCM
agent-browser close
```
**One-time login (scripted — when the form is simple, no MFA):**
```bash
agent-browser open https://research-source.example/login && agent-browser wait "@e_user"
agent-browser snapshot -i                          # read the @eN refs
agent-browser fill @e_user "$USER" && agent-browser fill @e_pass "$PASS"
agent-browser click @e_submit && agent-browser wait --url "**/dashboard"
agent-browser state save ./auth/source.json && agent-browser close
```
(Credentials come from env/`auth login`, never from the model's context.)

**Every later run (fully keyless, no re-login):**
```bash
agent-browser --state ./auth/source.json open https://research-source.example/article/123
agent-browser wait --load networkidle
agent-browser snapshot -i                          # already authenticated; extract per §5/§6
# ... eval --stdin / AQL-resolve the typed data ...
```
For the no-automation variant, replace the one-time login with a human Copy-as-cURL and
`agent-browser cookies set --curl ./auth/source.curl` before the first `open`.

### 13.3 The crawl4ai ↔ agent-browser handoff — RESOLVED (DESIGNED, do NOT hand off)

The §11 gap asked whether crawl4ai's `~/.crawl4ai/profiles/<name>` is byte-compatible with agent-browser's
`--profile`/`--state`. **Resolution: don't try to share profiles across the two tools — do *all* authed
fetching inside agent-browser.** Rationale (INFERRED, but well-grounded): (a) crawl4ai persists a *Chrome
user-data-dir* (Playwright `storage_state`/profile-dir layout), while agent-browser's `--state` is its own
`StorageState` JSON (`state.rs:17`) and its `--profile` is a read-only *copy* of a Chrome user-data-dir — the
two are different artifacts with different on-disk shapes, and there's no contract that one loads the other; (b)
agent-browser's `state save` already captures the complete auth surface (cookies + localStorage +
sessionStorage) in a clean, portable, optionally-encrypted JSON, so there is **no functional reason** to involve
crawl4ai in an authed flow at all. Concrete rule for the skill: **the moment a fetch needs auth, it is a rung-3
agent-browser job from login through extraction.** crawl4ai stays on the unauthenticated rung-2 (fast clean
markdown of public JS pages); it never participates in the authed path. This removes the untested handoff
entirely instead of trying to make it work.

### 13.4 Anti-bot, keyless — what actually helps and what doesn't (KNOWN + honest limits)

**Helps (KNOWN, local, $0):**
- **Real input events defeat naive synthetic-event detection.** Because agent-browser clicks/types via real CDP
  `Input.dispatchMouseEvent` at real box-model coordinates and `Input.insertText`/`dispatchKeyEvent` (§2.4), not
  `el.click()`, bot checks that look for `isTrusted=false` synthetic events see human-shaped input.
- **A persisted real session sails past most "are you logged in?" gates** — once §13.2 has cookies+storage from
  a genuine login, the site treats you as the returning logged-in user; there's nothing left to challenge for
  most research sources (docs portals, dashboards, paywalled articles the user subscribes to).
- **Local fingerprint knobs:** `--user-agent`, `--viewport`/`set device`, `--args`, `--proxy` (use a *free*/own
  proxy, not a paid residential one) tune the basic surface (`README.md`, all local flags). `set media`/`set
  geo`/`set offline` for emulation. These are free and cover the "default-headless-UA looks like a bot" class.

**Does NOT help keylessly (honest limits — INFERRED):**
- **Cloudflare/DataDome/PerimeterX interactive challenges and CAPTCHAs.** A persisted session avoids *re-*
  challenging, but a *fresh* hard challenge (Turnstile, hCaptcha, "press and hold") needs either a human in a
  `--headed` window (do it once, then `state save`) or a paid solver — out of scope. **Accept that some targets
  will fail; the skill should detect a challenge page (title/snapshot says "Verifying you are human" / a
  Turnstile/hCaptcha widget in the snapshot) and either prompt the user to solve it once in headed mode or
  report the source as unreachable-keyless.**
- **Residential-IP gating / datacenter-IP blocks.** Sites that block your server's datacenter IP need a
  residential/rotating proxy — inherently a paid service. agent-browser *can* delegate to `-p browserbase|kernel`
  with stealth/CAPTCHA flags, but that crosses the keyless line and is **explicitly out of scope** (§8). For the
  realistic research surface (sources the user can personally log into from their own browser), the persist-once
  flow covers it.

**Keyless reimplementation:** for any login-walled/bot-protected source, do a **one-time** login on the local
Chrome engine — headed for MFA/CAPTCHA/SSO, scripted for simple forms, or a human Copy-as-cURL — then
`state save ./auth/<src>.json` (optionally AES-GCM encrypted) and replay with `--state` on every later run; all
authed fetching stays inside agent-browser (no crawl4ai handoff); real CDP input events + the persisted session
handle the common anti-bot surface for free; and the skill detects a hard CAPTCHA/residential-IP wall and
degrades honestly (prompt for a one-time headed solve, or mark the source unreachable-keyless) rather than
pretending to bypass it.
