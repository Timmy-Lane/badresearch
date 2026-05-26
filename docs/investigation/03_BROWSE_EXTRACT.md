# 03 — Agentic Browse + Structured Extraction (for the ultimate-research skill)

**Goal:** catalog the best agentic-browse + structured-extraction patterns we reverse-engineered, so the
ultimate-research skill (built on hyperresearch) can handle JS-rendered pages, paywalls, anti-bot, logins, and
typed extraction. hyperresearch today fetches via httpx (`builtin`) + crawl4ai (`crawl4ai`); it has **no
LLM-driven navigation and no schema-driven extraction**. This dossier supplies both.

**Label key:** KNOWN = read verbatim from source/our RE files. INFERRED = derived from probing/blogs. IDEA = my
design proposal for the skill (not in any source). Every KNOWN cites the file it came from.

**Source RE files used:**
- `products/BROWSERBASE_PRODUCT_CODE.md` (Stagehand `act`/`extract`/`observe`, prompts, tools, AXTree, cache)
- `teardowns/BROWSER_USE.md` (indexed-DOM agent loop, action space, DOM serializer, compaction)
- `products/AGENTQL_PRODUCT_CODE.md` (AQL grammar, tree serializer, prompts, grounding)
- hyperresearch source: `web/base.py`, `web/crawl4ai_provider.py`, `web/builtin.py`, `core/fetcher.py`

---

## 0 — The four tools, one sentence each

| Tool | Primitive | What it gives the skill |
|---|---|---|
| **crawl4ai** (have) | Headless Chromium → fit_markdown | JS render + main-content markdown + screenshot + profile auth. Single-shot fetch, no reasoning. |
| **Browserbase / Stagehand** | Remote CDP browser + `act`/`extract`/`observe` LLM primitives | Multi-step LLM-driven navigation against an AXTree, schema-typed `extract`, anti-bot/CAPTCHA infra. |
| **AgentQL** | The AQL query DSL `(accessibility_tree, query) → typed data` | Selector-free typed extraction. Deterministic grounding catches LLM hallucinated refs. |
| **Browser-Use** | Indexed-DOM agent loop | Open-source step loop; LLM picks actions by integer index `click(3)` — eliminates selector hallucination. |

The escalation ladder (detailed in §6): **httpx → crawl4ai (JS render) → AgentQL/Stagehand-extract (typed) →
full agentic browse (login/paywall/anti-bot/multi-step)**.

---

## 1 — Browserbase + Stagehand

### 1.1 Headless-browser infra (sessions / contexts / CDP) — KNOWN

Browserbase is the **infra layer**; Stagehand is the **LLM-driving layer** on top of it. The skill only needs
Stagehand's primitives, but the infra explains the connection model:

- **Session lifecycle (KNOWN, `BROWSERBASE_PRODUCT_CODE.md` §2):** REST `api.browserbase.com` → gRPC
  `CreateSession()` to `browser-boss` → containerd VM boots Chrome on `:9222` (CDP). Response carries
  `cdp_ws_url = ws://10.x.x.x:9222/devtools/browser/<guid>`. Warm pool keeps 5–50 pre-booted Chromes;
  `VM_BOOT_TIME_TARGET_MS = 500`.
- **Client connection (KNOWN):** the client speaks **CDP over a WebSocket proxy** (`connect.browserbase.com`,
  Express). Playwright/Puppeteer connect with `chromium.connectOverCDP(wss://connect.browserbase.com?sessionId=…&apiKey=…)`.
  So Stagehand = "Playwright page object" + LLM primitives; the page can be local or remote-CDP.
- **Contexts (KNOWN, §6):** an encrypted persisted `user-data-dir` (cookies/localStorage), `AES-256-CBC`,
  stored in S3, mounted on session create. **This is the login/paywall persistence mechanism** — log in once,
  reuse the context. (crawl4ai's `profile` = `~/.crawl4ai/profiles/<name>` is the local equivalent.)
- **Stealth (KNOWN, §8/§9.10):** `stealth_level ∈ {0=none, 1=advanced, 2=verified}`; `solve_captchas`,
  `block_ads`, fingerprint config (browsers/devices/locales/OS/screen). Verified mode pins a fixed fingerprint;
  with Google CUA it hardcodes viewport `{1288, 711}`.

### 1.2 The three Stagehand primitives — `act` / `extract` / `observe` (KNOWN)

Each primitive is **one LLM call against the current page's AXTree** (a DOM/accessibility hybrid).
Constants (`BROWSERBASE_PRODUCT_CODE.md` §9.1):
```
ARIA_TREE_MAX_TOKENS = 70_000      ARIA_TREE_MAX_CHARS = 280_000   # 4 chars/token
ACT_TEMPERATURE = 0.1 (1 for GPT-5)  EXTRACT_TEMPERATURE = 0.1  AGENT_TEMPERATURE = 1
```

**`act(instruction)` → element + method to invoke.** Verbatim system prompt (KNOWN):
> You are helping the user automate the browser by finding elements based on what action the user wants to take
> on the page. You will be given: 1. a user defined instruction about what action to take 2. a hierarchical
> accessibility tree showing the semantic structure of the page. The tree is a hybrid of the DOM and the
> accessibility tree. Return the element that matches the instruction if it exists. Otherwise, return an empty object.

Plus a dropdown-specific addendum (`ACT_DROPDOWN_INSTRUCTION`, KNOWN) that branches on `<select>` vs non-select.
Output schema (Zod, KNOWN):
```ts
ActResponseSchema = z.object({
  elementId: z.string().regex(/^\d+-\d+$/),  // "{frameOrdinal}-{backendNodeId}", e.g. "0-142"
  description: z.string(),
  method: z.enum(['click','fill','type','selectOptionFromDropdown','focus','hover']),
  arguments: z.array(z.string()),
  twoStep: z.boolean().default(false),
})
```
The `elementId` is the grounding key — `{frameOrdinal}-{backendNodeId}`, frameOrdinal = DFS frame index
(main=0). A combined xpathMap resolves it to an absolute XPath the framework actually clicks. **The LLM never
emits a selector — it emits an ID drawn from the tree it was shown.** Same anti-hallucination trick as AgentQL
and Browser-Use.

**`extract(instruction, schema)` → structured typed data.** Verbatim system prompt (KNOWN):
> You are extracting content on behalf of a user. If a user asks you to extract a 'list' of information, or
> 'all' information, YOU MUST EXTRACT ALL OF THE INFORMATION THAT THE USER REQUESTS. You will be given: 1. An
> instruction 2. A list of DOM elements to extract from. Print the exact text from the DOM elements with all
> symbols, characters, and endlines as is. Print null or an empty string if no new information is found. ONLY
> print the content using the print_extracted_data tool provided. (Anthropic only) If a user is attempting to
> extract links or URLs, you MUST respond with ONLY the IDs of the link elements. Do not attempt to extract
> links directly from the text unless absolutely necessary.

The **schema is a JSON-Schema-shaped Zod object** (KNOWN, `extractTool.inputSchema`):
```ts
schema: z.object({
  type: z.string().optional(),
  properties: z.record(z.string(), z.unknown()).optional(),
  items: z.unknown().optional(),
  enum: z.array(z.string()).optional(),
  format: z.enum(['url','email','uuid']).optional(),
}).passthrough().optional()
```
So Stagehand-extract is: "here's the AXTree + an instruction + a target schema; fill the schema." Multi-chunk
pages use a **metadata-assessment prompt** (KNOWN, `METADATA_SYSTEM_PROMPT`) that decides `completed: bool` —
stop once the instruction is satisfied, even if chunks remain; only continue if `chunksTotal > chunksSeen` AND
unsatisfied. Output: `{ progress, completed }`.

**`observe(instruction)` → array of candidate elements + methods.** Verbatim system prompt (KNOWN): same shape
as `act` but returns "an array of elements that match the instruction." Output = `ObserveResponseSchema`
(array of `{elementId, description, method, arguments}`). `observe` is the **plan/preview** primitive — used by
`fillForm` to first locate all fields, then `act` each. The recommended pattern (INFERRED from the agent
prompt): `observe` to discover, cache the result, then `act` deterministically against cached IDs.

### 1.3 AXTree processing — how the page becomes LLM input (KNOWN)

- **HybridSnapshot (§9.9):** merges per-frame AXTrees in DFS order; each element ID = `{frameOrdinal}-{backendNodeId}`.
  Cross-iframe focus selectors use `>>` (`"div.main >> iframe >> button"`); XPath selectors start with `/`.
- **CBOR depth reduction (§9.2/§9.8):** `DOM.getDocument` is CBOR-encoded; very deep React trees overflow.
  Retry ladder `DOM_DEPTH_ATTEMPTS = [-1,256,128,64,32,16,8,4,2,1]` (−1 = unlimited first), catching
  `"CBOR: stack limit exceeded"`. Truncated subtrees are rehydrated on demand via `DOM.describeNode`
  (`DESCRIBE_DEPTH_ATTEMPTS = [-1,64,32,16,8,4,2,1]`).
- **Token budget:** AXTree truncated at 280k chars / 70k tokens with a `[CONTENT TRUNCATED…]` marker.

### 1.4 LLM-driven navigation — the V3 agent loop (KNOWN)

`act`/`extract`/`observe` are single calls; the **agent** chains them. From `buildAgentSystemPrompt()`
(§9.4, KNOWN, large XML system prompt). Salient mechanics for the skill:

- **Two modes:** `dom` (act/ariaTree-first, no screenshot grounding) vs `hybrid` (screenshot-first, coordinate
  clicks). DOM mode is cheaper and is the right default for research scraping.
- **Tool registry (§9.7, 12 DOM tools + optional search + done):** `act`, `ariaTree` (full AXTree, 70k cap),
  `extract` (schema), `goto` (`waitUntil:"load"`), `scroll` (percentage, default 80), `fillForm`,
  `screenshot`, `think` (no-op reasoning), `wait`, `navback`, `keys` (supports `%var%` substitution), `search`
  (Browserbase Search API or Brave fallback), `done` (dynamically built with the user's output schema).
- **Tool timeouts:** `DEFAULT_TOOL_TIMEOUT_MS = 45_000`; `think`/`wait` are NOT timeout-wrapped.
- **Strategy rule the skill should copy verbatim (KNOWN):** *"CRITICAL: Use extract ONLY when the task
  explicitly requires structured data output… For reading page content or understanding elements, always use
  ariaTree instead — it's faster and more reliable."* → i.e. **don't burn an extract LLM call when you only need
  to read.**
- **Stop condition (§9.4):** loop ends when `done` tool fires or `maxSteps` (default 20) reached.
  `ensureDone()` forces a final structured `done` call if the model stops early — guarantees typed output even on
  abandonment. `AGENT_TEMPERATURE = 1`.
- **Provider options (KNOWN):** `anthropic: { cacheControl: { type: 'ephemeral' } }` (cache the system msg),
  `openai: { store: false }`, `google: { mediaResolution: 'MEDIA_RESOLUTION_HIGH' }`.

### 1.5 Action cache — replay without re-paying LLM (KNOWN, §9.3)

`ActCache` key = `SHA-256({instruction, url, variableKeys})` (variable **names** only, never values — secrets
never cached). `AgentCache` key adds `{startUrl, options, configSignature}`; screenshots (base64) pruned before
write. **This is the single most important pattern to steal for a research pipeline**: the first agentic browse
of a site produces a replayable action script; subsequent fetches of the same site replay deterministically at
zero LLM cost. (See §6.5.)

---

## 2 — AgentQL: the AQL query DSL

AgentQL's whole product is `(accessibility_tree, query) → typed data` with **no brittle CSS/XPath selectors**.
The skill should treat AQL as the **typed-extraction contract** option.

### 2.1 The AQL grammar (KNOWN — `AGENTQL_PRODUCT_CODE.md` §3, ported from `agentql==1.18.1`)
```
Query       ::= '{' NodeList '}'
NodeList    ::= Node ((',' | NEWLINE) Node)*
Node        ::= IDENTIFIER Description? (Container | List | epsilon)
Description ::= '(' DescContent ')'          # free-text disambiguator, nested parens allowed
Container   ::= '{' NodeList '}'             # scoped: nav { home_link about_link }
List        ::= '[]' Container?              # products[] { name price }
IDENTIFIER  ::= [a-zA-Z_][a-zA-Z0-9_]*       # snake_case field names
```
Four AST node kinds (KNOWN): `IdNode` (single element), `IdListNode` (`links[]`), `ContainerNode`
(`nav { … }`), `ContainerListNode` (`products[] { name price }`). The query **is** the output schema —
field names become JSON keys, `[]` becomes arrays, `{}` becomes nested objects.

Example queries:
```
{ search_input  search_btn  results[] { title  url } }
{ products[] { name  price(integer)  in_stock(boolean) } }
{ login_btn(the blue one at the bottom) }
```
**Type hints live in the description:** `price(integer)`, `is_available(boolean)`, `(float)`. The data-extraction
prompt enforces them (KNOWN): `(integer)` strips currency/commas (`"$1,299.00" → 1299`); `(boolean)` → element
state. Descriptions also disambiguate (`submit_btn(the blue one at the bottom)`).

### 2.2 The API — `query_data` vs `query_elements` (KNOWN, §1)

Two SDK endpoints, both take `(accessibility_tree, query, params, metadata)`:

- **`POST /api/v2/query`** (`query_elements`) → **element location**: maps each query field to a `tf623_id`
  reference. Returns `{ "search_input": 14, "results": [{"title": 23, "url": 24}, …] }` — refs, for clicking.
- **`POST /api/v2/query-data`** (`query_data`) → **data extraction**: returns the **text values**. Two-phase:
  (1) run element pipeline to find matching nodes, (2) extract text programmatically from those nodes; falls
  back to single-phase direct LLM extraction. Returns `{ "page_title": "…", "products": [{"name": "iPhone 15
  Pro", "price": 999, "in_stock": true}, …] }`.
- **`POST /api/v2/queries/generate`** → NL prompt → valid AQL string (so the skill can let an LLM author the
  query, then validate it with the parser before running).
- **`POST /v1/query-data`** (REST) → server-side: AgentQL **navigates to a URL itself**, builds the tree, runs
  the pipeline. Body: `{url|html, query|prompt, params:{mode, wait_for, is_scroll_to_bottom_enabled,
  is_screenshot_enabled, browser_profile:"light"|"stealth"}}`. This is the one-call "give me typed data from a
  URL" endpoint — the closest analog to what the skill wants.

`params.mode ∈ {fast, standard}` (routing hint). `experimental_stealth_mode_enabled` in metadata.

### 2.3 The bridge: `tf623_id` + accessibility tree (KNOWN)

AgentQL injects a `tf623_id` attribute onto every DOM node client-side (the verbatim 383-line
`generate_accessibility_tree.js`, KNOWN). The server-side tree serializer (`tree_serializer.py`, KNOWN) renders
the tree to **token-efficient indented text** the LLM sees:
```
- webArea "Example Store" [ref=1]
  - navigation "Main Nav" [ref=3]
    - link "Home" [ref=4] (href=/)
  - main [ref=6]
    - button "Add to Cart" [ref=11]
```
Pruning rules (KNOWN): flatten single-child generic containers; drop empty nodes; depth-limit deep subtrees to
`- … (N nested elements) [ref=…]`; per-node useful attrs only (`href,type,placeholder,value,src,class`); name
truncated to `MAX_NAME_LENGTH`. For >1000 nodes, `prune_tree_for_query()` scores each node by token-overlap with
query field names (exact-in-name +10, word overlap ×3, role hint match) and keeps scored nodes + ancestors.
Claimed 51–79% smaller than raw JSON.

### 2.4 Grounding — why AQL beats raw LLM-extract (KNOWN, §5)

After the LLM returns refs, `ground_element_response()` **verifies every proposed ref actually exists in the
original tree** (via `build_tree_index()`: `tf623_id → node`). Hallucinated refs become errors; the pipeline
**retries once** with a `CORRECTIVE_PROMPT_TEMPLATE` listing the bad fields (`MAX_RETRIES`). System prompt rule
#7 (KNOWN): *"If an element CANNOT be found, return null… Do NOT guess or return a wrong element."* This
deterministic post-LLM validation is the durable lesson: **never trust LLM-emitted element references; ground
them against the captured tree, retry on failure.**

---

## 3 — Browser-Use: the indexed-DOM agent loop

Open-source (`browser-use/browser-use`, MIT). The reference design for a self-hostable agentic browser the
skill could embed without a paid API.

### 3.1 The novel primitive — indexed-DOM as the action space (KNOWN, `BROWSER_USE.md` §1, §5.4)

The framework enumerates every interactive element, assigns each a **stable integer index**, renders them as
`[i]<tag attr=val/>` tokens, and the LLM picks actions **by index** (`click(3)`, `input(5, "hello")`). The LLM
cannot invent a non-existent index → kills selector hallucination. Serialized format (KNOWN):
```
[33]<div />
    User form
    [35]<input type=text placeholder=Enter name />
   *[38]<button aria-label=Submit form />        # * = NEW since last step
        Submit
|SCROLL|[40]<a />                                 # |SCROLL| = scrollable; |SHADOW(open)| = shadow DOM
```

### 3.2 Step loop (KNOWN, `service.py:1023`, 4 phases)
```
Phase 0: captcha wait (browser may auto-solve)
Phase 1: _prepare_context  → DOM serialize + screenshot + history
Phase 2: _get_next_action  → LLM emits AgentOutput JSON; _execute_actions
Phase 3: _post_process     → downloads, loop detection, failure tracking
```
- **AgentOutput JSON (KNOWN):** `{ thinking, evaluation_previous_goal, memory, next_goal, current_plan_item,
  plan_update, action: [{navigate:{url}}, …] }`. Flash mode strips everything but `memory` + `action`.
- **Timeouts (KNOWN):** `llm_timeout` auto-detected by model (groq 30s, claude/o3/deepseek 90s, default 75s);
  `step_timeout = 180s`; typical 30–100 steps/task.
- **DOM capture (KNOWN, §5.1/§5.4):** talks **CDP directly** (`cdp-use`), not Playwright high-level API:
  `DOM.getDocument(depth=-1, pierce=True)`, `Accessibility.getFullAXTree`, `DOMSnapshot.captureSnapshot`.
  Iframe traversal `max_iframes=100`, `max_iframe_depth=5`. `ClickableElementDetector` (246 lines of heuristics)
  decides interactivity: JS click listeners, interactive tags/roles, `cursor:pointer`, icon-sized clickables,
  ARIA props. Viewport-threshold filtering (`viewport_threshold=1000px`) + paint-order (z-index) filtering.
  Truncation `max_clickable_elements_length=40000`.

### 3.3 The action space (~30 actions, KNOWN, `tools/service.py`) — the menu to copy

`search` (duckduckgo default — "less captchas"; google adds `&udm=14` to strip AI overview), `navigate`
(with empty-DOM retry: wait 3s → reload → wait 5s → error), `go_back`, `wait`, `click`, `input` (autocomplete
detection + sensitive-data redaction), `upload_file`, `switch`/`close` tab, **`extract`** (the expensive one —
see §3.4), **`search_page`** (grep page text, **zero LLM cost**), **`find_elements`** (CSS selector, **zero LLM
cost**), `scroll`, `send_keys`, `find_text`, `screenshot`, `save_as_pdf`, `dropdown_options`/`select_dropdown`,
`write_file`/`replace_file`/`read_file`, `evaluate` (JS, auto-fixes quote bugs), `done`. **`search_page`/
`find_elements` are the cheapest extraction tier** — deterministic, no model call.

### 3.4 `extract` action = self-hostable structured extraction (KNOWN, §4.4)

The closest open-source analog to Stagehand-extract / AgentQL `query_data`:
1. Clean-markdown the page (`extract_clean_markdown`, strips nav/ads).
2. Structure-aware chunking, `max_chunk_chars = 100000`, header carry-over across chunks; `start_from_char` to
   continue.
3. If `output_schema` set → convert dict → Pydantic model; **structured-output system prompt** (KNOWN verbatim):
   > You are an expert at extracting structured data from the markdown of a webpage. … Extract ONLY information
   > present in the webpage. Do not guess or fabricate values. Your response MUST conform to the provided JSON
   > Schema exactly. If a required field's value cannot be found … use null … If <already_collected> items are
   > provided, skip duplicates.
   Prompt frame: `<query>…<output_schema>…<content_stats>…<webpage_content>…<already_collected>`.
4. Else free-text path (verbatim prompt also in source).
5. Memory: <10000 chars → long-term memory; else write to file, memory becomes a pointer.
6. Timeout 120s on a **separate `page_extraction_llm`** (cheaper model than the main loop LLM).

### 3.5 Memory / compaction (KNOWN, §6) — relevant to long research runs
Single-message-per-step (rebuilt fresh, cache-friendly). Compaction every 25 steps when history >40000 chars,
keeps first + last 6 items, summary ≤6000 chars. Compaction prompt's anti-hallucination clause (KNOWN): *"Only
mark a step as completed if you see explicit success confirmation… Never infer completion from context."*

---

## 4 — crawl4ai (hyperresearch's current provider)

### 4.1 What it does today (KNOWN, `web/crawl4ai_provider.py`)

- **JS render via headless Chromium** (`AsyncWebCrawler` + `BrowserConfig`). Smart wait JS: 2s initial, then poll
  `document.body.innerText.length` every 500ms until stable for 2 checks or 16 polls (~10s ceiling).
- **Main-content markdown:** `DefaultMarkdownGenerator(content_filter=PruningContentFilter())` → prefers
  `fit_markdown` (nav/footer stripped) over `raw_markdown`.
- **Run config (KNOWN):** `magic=…, simulate_user=True, screenshot=True, page_timeout=30000, wait_for=<smartwait>`.
- **Auth via browser profiles (KNOWN):** `user_data_dir = ~/.crawl4ai/profiles/<name>` → reuses cookies/
  localStorage. For headless-detecting sites (LinkedIn etc.), `_fetch_visible()` drops to **raw Playwright
  `launch_persistent_context(headless=False)`** because crawl4ai's managed browser forces headless.
- **PDF path:** `_is_pdf_url` → httpx download → pymupdf text extract; post-fetch binary-garbage detection
  (`_looks_like_binary`) re-routes inline-served PDFs.
- **Batch:** `fetch_many` / `arun_many` concurrent.
- Returns `WebResult{url, title, content(markdown), raw_html, metadata, media[], links[], screenshot}`.

### 4.2 Its limits (the gap this dossier fills) — INFERRED from source
1. **No reasoning / no multi-step.** One URL → one fetch. Cannot click "load more", paginate, fill a search box,
   dismiss a modal, or follow a multi-step flow. (Browser-Use/Stagehand do.)
2. **No structured/typed extraction.** Returns markdown; the caller must parse. (AgentQL/Stagehand-extract do.)
3. **No anti-bot beyond `magic`/`simulate_user`.** `WebResult.looks_like_junk()` *detects* Cloudflare/CAPTCHA
   walls but cannot *defeat* them. No CAPTCHA solving, no residential proxy, no stealth fingerprint rotation.
   (Browserbase does.)
4. **`search()` raises NotImplementedError** — crawl4ai cannot discover URLs.
5. **Login = a pre-created profile only.** No on-the-fly login flow; if the cookie expires, `looks_like_login_wall`
   aborts (KNOWN, `core/fetcher.py`).

---

## 5 — Structured-extraction contract: three options compared

The skill needs ONE typed-extraction interface internally; these are the three ways the field does it.

| Approach | Schema form | Grounding / anti-hallucination | Cost | Best when |
|---|---|---|---|---|
| **AgentQL AQL** | the AQL query string IS the schema (`products[] { name price(integer) }`) | deterministic — refs validated against captured tree, 1 corrective retry | 1 LLM call (fast model) + tree serialize | known page shape, repeatable scrapes, lists of records |
| **Stagehand `extract` + Zod/JSON-Schema** | explicit JSON-Schema/Zod object | LLM fills schema; multi-chunk `completed` gate; `format` validators (url/email/uuid) | 1+ LLM calls (per chunk) | one-off, rich nested objects, when you already have a Zod model |
| **LLM-extract (Browser-Use style)** | dict → Pydantic; or free text | prompt-only ("do not fabricate", null on missing); `already_collected` dedup | 1 call on cleaned markdown (cheap `page_extraction_llm`) | self-hosted, no paid API, markdown already in hand |

**Recommendation for the skill (IDEA):** define one `ExtractSpec` = a JSON Schema (or AQL string), and back it
by whichever provider is available, defaulting to **LLM-extract over crawl4ai's `fit_markdown`** (zero new deps,
already have the markdown), escalating to AgentQL `query_data` or Stagehand `extract` only when the page needs a
live DOM/AXTree (interactive widgets, infinite scroll, link-ID extraction). Always apply the two durable rules:
(1) **ground every element reference against the captured tree**; (2) **null, never fabricate, on missing fields.**

---

## 6 — The escalation ladder (decision criteria + cost/latency)

This is the policy the skill's fetcher should implement. Tiers run in order; each tier only escalates when the
cheaper tier's result fails a quality gate (reuse hyperresearch's existing `WebResult.looks_like_junk()` /
`looks_like_login_wall()` — KNOWN, `web/base.py`).

| Tier | Mechanism | When to use | Latency | $ cost | Defeats |
|---|---|---|---|---|---|
| **0 — HTTP** | httpx + bs4/PruningFilter (`builtin`) | static HTML, articles, docs, RSS, sitemaps, APIs returning JSON | 50–500ms | 0 | nothing — fails on JS apps |
| **1 — Crawl (JS render)** | crawl4ai headless Chromium → fit_markdown | SPA / React / Vue, lazy-loaded content, anything `builtin` returns near-empty for | 2–10s (smart wait) | 0 (local) | client-side rendering |
| **2 — Typed extract** | Tier-1 markdown/HTML → LLM-extract OR AgentQL `query_data` / Stagehand `extract` | caller asked for **typed records** (a schema), not prose | +1–4s (1 LLM call) | ~1 cheap LLM call | unstructured → typed |
| **3 — Agentic browse** | Browser-Use loop (self-host) or Stagehand agent (Browserbase) | login, paywall, multi-step (search→paginate→click), interactive widgets, infinite scroll | 10–120s (N steps × 2–20s) | N LLM calls + browser-min | logins, multi-step flows |
| **3b — Anti-bot infra** | Browserbase verified session: stealth fingerprint + residential proxy + CAPTCHA solve | Cloudflare/Datadome walls, aggressive bot detection (`looks_like_junk` = "Bot detection page") | 10–120s | browser-min + proxy bytes + LLM | Cloudflare/CAPTCHA/fingerprint |

**Escalation triggers (concrete, KNOWN signals from `web/base.py`):**
- Tier 0 → 1: `len(content.strip()) < 300` ("Empty or near-empty"), or content has skeleton/placeholder markers.
- Tier 1 → 3b: `looks_like_junk()` returns "Bot detection page" (Cloudflare/CAPTCHA/"just a moment"/"ray id").
- any → 3: `looks_like_login_wall()` true (title/URL has `/login,/signin,/auth,/sso`) AND a credentialed run is
  desired → drop to agentic login OR a persisted context/profile.
- Tier 1 → 2: caller passed an `ExtractSpec` (schema) → the prose result must be made typed.

**Cost discipline (the Stagehand rule, KNOWN):** never escalate to Tier 2/3 for *reading* — only for *typed
output* or *interaction*. For interaction, **cache + replay** (ActCache, §1.5): first agentic visit records an
action script keyed by `SHA-256({instruction, url, variableKeys})`; later visits of the same site replay
deterministically at Tier-0 cost. This is what makes a multi-source research sweep affordable.

---

## 7 — BrowseProvider + ExtractProvider design (the deliverable)

hyperresearch's current contract (KNOWN, `web/base.py`): a `WebProvider` Protocol with `fetch(url)->WebResult`
and optional `search()`, loaded by `get_provider(name, profile, magic, headless)`; the only call site is
`core/fetcher.fetch()` which does `prov.fetch(url)` then junk/login gating. The two new providers slot in
**alongside** crawl4ai/builtin/exa without changing `WebResult`.

### 7.1 `BrowseProvider` — multi-step agentic navigation (IDEA, extends `WebProvider`)
```python
# web/browse_base.py  (IDEA — new abstraction; mirrors the WebProvider Protocol style)
from typing import Protocol, runtime_checkable
from hyperresearch.web.base import WebResult

@runtime_checkable
class BrowseProvider(Protocol):
    """Tier-3: LLM-driven, multi-step browse. Returns a WebResult like any provider,
    but reaches it through an agent loop (login, paginate, click, dismiss modals)."""
    name: str

    def browse(
        self,
        url: str,
        instruction: str,            # NL goal: "log in and open the billing page", "load all reviews"
        *,
        max_steps: int = 20,         # Stagehand default (KNOWN). Browser-Use typical 30-100.
        variables: dict[str, str] | None = None,   # %var% secret substitution (KNOWN, both frameworks)
        replay_key: str | None = None,             # ActCache key → deterministic zero-LLM replay (KNOWN §1.5)
    ) -> WebResult: ...
```
Two concrete impls (IDEA, both produce `WebResult`):
- **`BrowserUseProvider`** (self-host default): wraps a Browser-Use `Agent(task=instruction, llm=…,
  browser_session=…)`; on `done`, dump final page → `fit_markdown` for `WebResult.content`, keep
  `raw_html`/`screenshot`. Zero paid API. Uses the indexed-DOM loop (§3).
- **`BrowserbaseProvider`** (paid, for anti-bot): `chromium.connectOverCDP(connect.browserbase.com?…)` with
  `verified` stealth + proxy + `solveCaptchas`, then drive Stagehand `agent.execute(instruction)`.

### 7.2 `ExtractProvider` — schema-driven typed extraction (IDEA)
```python
# web/extract_base.py  (IDEA)
from typing import Protocol, Any
from hyperresearch.web.base import WebResult

class ExtractProvider(Protocol):
    name: str
    def extract(
        self,
        source: WebResult | str,          # a fetched WebResult, or a raw URL (provider may fetch)
        schema: dict[str, Any] | str,     # JSON Schema, OR an AgentQL query string
        instruction: str | None = None,   # optional NL guidance
    ) -> dict: ...                        # data conforming to schema; missing fields → null (never fabricate)
```
Three impls (IDEA), pick by availability:
- **`LLMExtractProvider`** (default, zero new deps): runs Browser-Use's structured-output prompt (§3.4, KNOWN)
  over `source.content` (already `fit_markdown`); dict-schema → Pydantic; chunk at 100k chars with
  `already_collected` dedup. Grounds: instruct null-on-missing.
- **`AgentQLExtractProvider`**: POST the AQL query + the page's tree to a (self-hosted, per
  `AGENTQL_PRODUCT_CODE.md`, or hosted) AgentQL `query_data`. Inherits deterministic ref-grounding + 1 retry.
  Accepts `schema` as an AQL string directly; if `schema` is JSON Schema, translate JSON-Schema → AQL
  (objects→`{}`, arrays→`[]`, leaf+`type`→`field(integer|boolean|…)`).
- **`StagehandExtractProvider`**: only when a live Browserbase/Stagehand session exists (Tier 3); call
  `page.extract({instruction, schema})` against the AXTree (handles interactive/link-ID extraction crawl4ai can't).

### 7.3 `get_provider()` wiring (IDEA — minimal change to `web/base.py`)
Extend the existing registry so the same factory yields browse/extract providers:
```python
# add to get_provider(): names "browser-use", "browserbase" → BrowseProvider impls.
# add get_extract_provider(name): "llm" (default) | "agentql" | "stagehand".
```
No change to `WebResult` or to `looks_like_junk/looks_like_login_wall` — they remain the **escalation gates**.

### 7.4 Which pipeline stages call them (KNOWN stage names, IDEA wiring)

The V8 research pipeline (KNOWN, `skills/hyperresearch.md`) has the relevant stages:
- **Step 2 `width-sweep`** — parallel fetcher waves over many URLs. **Default Tier 0→1** (httpx→crawl4ai). Cheap,
  broad. Do NOT run agentic browse here — too many URLs. If a width URL trips `looks_like_junk()=="Bot
  detection"`, mark it for a single Tier-3b retry, don't block the wave.
- **Step 5 `depth-investigation`** — K parallel depth-investigators, each "may fetch additional sources beyond
  the width corpus." **This is where Tier 2 (ExtractProvider) and Tier 3 (BrowseProvider) belong**: a depth
  investigator that needs typed records calls `ExtractProvider.extract(webresult, schema)`; one that hits a
  paywall/login/multi-step flow calls `BrowseProvider.browse(url, instruction)`. Budgeted (`source_budget`,
  ≤6 investigators) so cost stays bounded.
- **Step 13 `gap-fetch`** — fetches sources for critic-identified gaps. Same as depth: prefer Tier 0/1; escalate
  to Tier 3 only for the specific gap URL that needs a login/interaction. Use **replay cache** (§1.5) if the gap
  is on a site already browsed in step 5.

**Net:** `core/fetcher.fetch()` gains an optional `tier`/`instruction`/`schema` param. With neither, behavior is
unchanged (Tier 0/1 as today). With a `schema`, it post-processes via `ExtractProvider` (Tier 2). With an
`instruction` (or on junk/login-wall escalation), it routes to a `BrowseProvider` (Tier 3). The width-sweep stays
cheap by default; depth + gap-fetch opt into the expensive tiers per-source.

---

## 8 — Durable lessons to bake into the skill (cross-cutting)

1. **Never let the LLM emit a selector.** Give it a tree of pre-enumerated IDs (`tf623_id` / `frameOrdinal-backendNodeId`
   / integer index) and make it pick. All three RE'd systems converge on this. (KNOWN: AgentQL, Stagehand, Browser-Use.)
2. **Ground LLM output against the captured tree, retry once on failure.** (KNOWN: AgentQL grounding, `MAX_RETRIES`.)
3. **Null on missing, never fabricate** — put it in the system prompt. (KNOWN: all three.)
4. **Serialize the DOM to indented text, not JSON; prune aggressively; cap tokens** (70k Stagehand / 40k chars
   Browser-Use / query-guided pruning AgentQL). The cheapest token is the one you don't send.
5. **Read with the tree, extract only when you need typed output** (KNOWN Stagehand strategy rule) — the single
   biggest cost lever.
6. **Cache + replay action scripts** keyed by `SHA-256({instruction,url,variable NAMES})`; never cache secret values.
7. **Persisted contexts/profiles are the cheap login mechanism**; agentic login is the fallback. crawl4ai profiles
   already give the skill this for free.
8. **A separate cheaper `page_extraction_llm`** for extraction vs the main reasoning LLM (KNOWN: Browser-Use,
   Stagehand model routing).
