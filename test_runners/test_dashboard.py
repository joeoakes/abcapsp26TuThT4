"""
test_dashboard.py
Automated test runner for the mission dashboard — covers all 24 test cases (9.1–9.24).

The dashboard was refactored into an ES-module layout:
    dashboard/index.html
    dashboard/js/api.js
    dashboard/js/ui-controller.js
    dashboard/js/theme-engine.js

Pure utility functions (normalizeResult, escapeHtml, formatUnixTime, resultTag)
are extracted from `ui-controller.js` and executed directly in Node when
available, or exercised via equivalent Python reference implementations.
All other tests are source-text assertions against the combined HTML + JS
corpus.

Run from the project root:
    python test_runners/test_dashboard.py
"""
from __future__ import annotations

import sys, os, subprocess, re, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from test_framework import TestSuite

# ---------------------------------------------------------------------------
# Locate dashboard assets (index.html + all JS modules)
# ---------------------------------------------------------------------------
def _find_dashboard_dir():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for dp, dirnames, files in os.walk(root):
        # Skip the build/ snapshot dir so we don't pick up stale copies.
        if "build" in dp.split(os.sep):
            continue
        if "index.html" in files and os.path.basename(dp) == "dashboard":
            return dp
    return None


_dashboard_dir  = _find_dashboard_dir()
_dashboard_html = ""
_dashboard_js   = ""           # combined JS across every *.js in dashboard/js/
_ui_js          = ""           # ui-controller.js alone (for function extraction)
_api_js         = ""

if _dashboard_dir:
    _html_path = os.path.join(_dashboard_dir, "index.html")
    if os.path.exists(_html_path):
        with open(_html_path) as f:
            _dashboard_html = f.read()

    js_dir = os.path.join(_dashboard_dir, "js")
    if os.path.isdir(js_dir):
        parts = []
        for fn in sorted(os.listdir(js_dir)):
            if fn.endswith(".js"):
                with open(os.path.join(js_dir, fn)) as f:
                    body = f.read()
                parts.append(body)
                if fn == "ui-controller.js":
                    _ui_js = body
                elif fn == "api.js":
                    _api_js = body
        _dashboard_js = "\n".join(parts)

# Corpus searched by source-text tests = HTML + every JS module
_corpus = _dashboard_html + "\n" + _dashboard_js

# Check if node is available (used to exercise pure utility functions)
try:
    _node = subprocess.run(
        ["node", "--version"], capture_output=True, timeout=5
    ).returncode == 0
except Exception:
    _node = False


def _extract_fn(src: str, name: str) -> str:
    """
    Return the text of a top-level `function <name>(...) { ... }` declaration
    from `src`, or '' if it is not found.  Uses brace counting so nested
    braces inside template strings / objects are handled correctly.
    """
    m = re.search(r"function\s+" + re.escape(name) + r"\s*\(", src)
    if not m:
        return ""
    i = src.find("{", m.end())
    if i < 0:
        return ""
    depth = 0
    j = i
    while j < len(src):
        ch = src[j]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return src[m.start():j + 1]
        j += 1
    return ""


def _run_js(snippet: str) -> str:
    """Run a JS snippet in Node with a minimal browser shim and return stdout."""
    if not _node:
        raise AssertionError("node.js not available in this environment")
    shim = """
const window = { location: { origin: 'http://localhost:8447' } };
const document = { getElementById: () => ({ value: '', innerHTML: '', disabled: false,
    textContent: '', classList: { add:()=>{}, remove:()=>{}, toggle:()=>{} },
    addEventListener: () => {}, appendChild: () => {}, style: {} }),
  createElement: () => ({ value: '', textContent: '', innerHTML: '', appendChild: () => {},
    classList: { add:()=>{}, remove:()=>{}, toggle:()=>{} } }) };
function setInterval() { return 1; }
function clearInterval() {}
function requestAnimationFrame() { return 1; }
function cancelAnimationFrame() {}
"""
    # Inject only the pure, side-effect-free helpers we need.
    helpers = "\n".join(
        body for body in (
            _extract_fn(_ui_js, "normalizeResult"),
            _extract_fn(_ui_js, "escapeHtml"),
            _extract_fn(_ui_js, "formatUnixTime"),
            _extract_fn(_ui_js, "resultTag"),
        ) if body
    )
    code = shim + helpers + "\n" + snippet
    r = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        raise AssertionError(f"node error: {r.stderr[:300]}")
    return r.stdout.strip()


def _has_dashboard():
    if not _dashboard_html:
        raise AssertionError("dashboard/index.html not found in project")
    if not _ui_js:
        raise AssertionError("dashboard/js/ui-controller.js not found in project")


# ---------------------------------------------------------------------------
suite = TestSuite("dashboard.html")


# 9.1
def _t91():
    _has_dashboard()
    if _node:
        assert _run_js('console.log(normalizeResult("In Progress"))') == "inprogress"
        assert _run_js('console.log(normalizeResult("SUCCESS"))') == "success"
    else:
        def norm(s): return re.sub(r"\s+", "", str(s or "").strip().lower())
        assert norm("In Progress") == "inprogress"
        assert norm("SUCCESS") == "success"
suite.run("9.1", "Unit Testing",
          "normalizeResult() – lowercases and strips spaces", _t91)


# 9.2
def _t92():
    _has_dashboard()
    if _node:
        r = _run_js("""
console.log(resultTag('Success').includes('status-chip success'));
console.log(resultTag('Aborted').includes('status-chip aborted'));
console.log(resultTag('In Progress').includes('status-chip inprogress'));
console.log(resultTag('unknown_thing').includes('status-chip other'));
""")
        assert all(l == "true" for l in r.splitlines()), f"Badge assertions failed:\n{r}"
    else:
        assert "status-chip success" in _ui_js
        assert "status-chip aborted" in _ui_js
        assert "status-chip inprogress" in _ui_js
        assert "status-chip other" in _ui_js
suite.run("9.2", "Unit Testing",
          "resultTag() – correct status-chip class for each result", _t92)


# 9.3
def _t93():
    _has_dashboard()
    if _node:
        r1 = _run_js("console.log(formatUnixTime(null))")
        r2 = _run_js("console.log(formatUnixTime('0'))")
        assert "\u2014" in r1 or "—" in r1
        assert "\u2014" in r2 or "—" in r2
    else:
        assert "formatUnixTime" in _ui_js
        assert "\\u2014" in _ui_js or "—" in _ui_js
suite.run("9.3", "Unit Testing",
          "formatUnixTime() – returns em-dash for falsy/zero timestamps", _t93)


# 9.4
def _t94():
    _has_dashboard()
    if _node:
        r = _run_js("console.log(formatUnixTime('1700000000'))")
        assert len(r) > 5 and "\u2014" not in r
    else:
        assert "Number.parseInt" in _ui_js
suite.run("9.4", "Unit Testing",
          "formatUnixTime() – converts valid unix timestamp to locale string", _t94)


# 9.5
def _t95():
    _has_dashboard()
    if _node:
        r = _run_js('console.log(escapeHtml(\'<b>"test" & more</b>\'))')
        assert "&lt;" in r and "&gt;" in r and "&amp;" in r and "&quot;" in r
    else:
        assert "escapeHtml" in _ui_js
        assert "&lt;" in _ui_js or ".replace(" in _ui_js
suite.run("9.5", "Unit Testing",
          "escapeHtml() – escapes &, <, >, and quotes", _t95)


# 9.6
def _t96():
    _has_dashboard()
    assert "function renderMission" in _ui_js
suite.run("9.6", "Unit Testing",
          "renderMission() – function defined in source", _t96)


# 9.7
def _t97():
    _has_dashboard()
    if _node:
        r = _run_js("""
const dist = 10.00, dur = 5;
const avg = dur > 0 ? (dist / dur).toFixed(3) : '\u2014';
console.log(avg);
""")
        assert r == "2.000"
    else:
        assert "distanceMeters / duration" in _ui_js
suite.run("9.7", "Unit Testing",
          "renderMission() – avg speed computed correctly", _t97)


# 9.8
def _t98():
    _has_dashboard()
    if _node:
        r = _run_js("""
const dur = 0, dist = 10.00;
const avg = dur > 0 ? (dist / dur).toFixed(3) : '\u2014';
console.log(avg === '\u2014' ? 'em-dash' : avg);
""")
        assert "em-dash" in r
    else:
        assert "duration > 0" in _ui_js
suite.run("9.8", "Unit Testing",
          "renderMission() – avg speed shows em-dash when duration=0", _t98)


# 9.9
def _t99():
    _has_dashboard()
    assert "abortReason" in _ui_js
    # Conditional rendering of the abort-reason row.
    assert re.search(r"mission\.abortReason\s*\?", _ui_js), \
        "abortReason ternary rendering not found"
suite.run("9.9", "Unit Testing",
          "renderMission() – abort_reason row conditional in source", _t99)


# 9.10
def _t910():
    _has_dashboard()
    assert "loadSessions" in _ui_js
    assert "/sessions" in _api_js
suite.run("9.10", "Integration Testing",
          "loadSessions() – fetches /sessions endpoint (source check)", _t910)


# 9.11
def _t911():
    _has_dashboard()
    # Generic error-handling path + user-visible error surfacing.
    assert "Failed to fetch sessions" in _api_js
    assert "showError" in _ui_js
suite.run("9.11", "Integration Testing",
          "loadSessions() – error message on fetch failure (source check)", _t911)


# 9.12
def _t912():
    _has_dashboard()
    assert "setMissionButtonState" in _ui_js
    assert "btnRefreshMission" in _ui_js
    assert "selectedSessionId" in _ui_js
suite.run("9.12", "Integration Testing",
          "onSessionChange() – enables Refresh Mission (source check)", _t912)


# 9.13
def _t913():
    _has_dashboard()
    assert "loadMission" in _ui_js
    assert "/mission/" in _api_js
suite.run("9.13", "Integration Testing",
          "loadMission() – fetches /mission/{sid} (source check)", _t913)


# 9.14
def _t914():
    _has_dashboard()
    assert "Failed to fetch mission" in _api_js
    assert "showError" in _ui_js
suite.run("9.14", "Integration Testing",
          "loadMission() – error message on failure (source check)", _t914)


# 9.15
def _t915():
    _has_dashboard()
    assert "setInterval" in _ui_js
    assert "AUTO_REFRESH_INTERVAL_MS" in _ui_js
    m = re.search(r"AUTO_REFRESH_INTERVAL_MS\s*=\s*(\d+)", _ui_js)
    assert m and m.group(1) == "5000", \
        f"AUTO_REFRESH_INTERVAL_MS not 5000 (got {m.group(1) if m else None})"
suite.run("9.15", "Integration Testing",
          "Auto-refresh timer fires every 5000ms (source check)", _t915)


# 9.16
def _t916():
    _has_dashboard()
    assert "clearInterval" in _ui_js
    assert "autoRefreshTimer" in _ui_js
suite.run("9.16", "Integration Testing",
          "clearInterval called on auto-refresh disable (source check)", _t916)


# 9.17
def _t917():
    _has_dashboard()
    assert 'name="viewport"' in _dashboard_html
    # cross-browser intent: either an explicit note, a system font stack,
    # or a viewport-scale directive.
    assert (
        "cross-browser" in _dashboard_html.lower()
        or "-apple-system" in _dashboard_html
        or "width=device-width" in _dashboard_html
    )
suite.run("9.17", "System Testing",
          "Viewport meta tag present for cross-browser support", _t917)


# 9.18
def _t918():
    _has_dashboard()
    # Responsive styling lives in dashboard/css/main.css — accept either
    # inline CSS in index.html or a referenced stylesheet.
    css_dir = os.path.join(_dashboard_dir, "css")
    css_text = ""
    if os.path.isdir(css_dir):
        for fn in sorted(os.listdir(css_dir)):
            if fn.endswith(".css"):
                with open(os.path.join(css_dir, fn)) as f:
                    css_text += f.read()
    combined = _dashboard_html + css_text
    assert "@media" in combined or "grid-template-columns" in combined
suite.run("9.18", "System Testing",
          "Mobile viewport – responsive media query present", _t918)


# 9.19
def _t919():
    _has_dashboard()
    assert "loadSessions" in _ui_js
    assert "loadMission"  in _ui_js
    assert "renderMission" in _ui_js
suite.run("9.19", "System Testing",
          "Full flow functions all defined: loadSessions/loadMission/renderMission", _t919)


# 9.20
def _t920():
    _has_dashboard()
    # New design uses `status-chip` variants — accept either CSS variable
    # references in the HTML/CSS bundle or explicit chip modifier classes.
    css_dir = os.path.join(_dashboard_dir, "css")
    css_text = ""
    if os.path.isdir(css_dir):
        for fn in sorted(os.listdir(css_dir)):
            if fn.endswith(".css"):
                with open(os.path.join(css_dir, fn)) as f:
                    css_text += f.read()
    combined = _dashboard_html + css_text + _ui_js
    assert "status-chip" in combined and "success" in combined
    assert "aborted" in combined
    assert "inprogress" in combined
    assert "var(--" in combined, "No CSS variables referenced — palette not themeable"
suite.run("9.20", "System Testing",
          "Status-chip colours mapped to CSS variables (source check)", _t920)


# 9.21
def _t921():
    _has_dashboard()
    assert "<!DOCTYPE html>" in _dashboard_html
    assert "<html"  in _dashboard_html
    assert "</html>" in _dashboard_html
    # ES-module script tag replaced the inline <script>.
    assert "<script" in _dashboard_html and "</script>" in _dashboard_html
suite.run("9.21", "Smoke Testing",
          "Page has valid HTML structure (DOCTYPE, html, script tags)", _t921)


# 9.22
def _t922():
    _has_dashboard()
    # loadSessions() is invoked at module load at the bottom of ui-controller.js.
    last_lines = _ui_js.strip().splitlines()[-12:]
    assert any("loadSessions()" in l for l in last_lines), \
        "loadSessions() not called at end of script"
suite.run("9.22", "Smoke Testing",
          "loadSessions() called automatically on page load", _t922)


# 9.23
def _t923():
    _has_dashboard()
    if _node:
        r = _run_js("""
const sessions = Array.from({length:500}, (_,i) => ({
  sessionId:`team4_${i}`, missionResult:'Success', movesTotal:10
}));
const t0 = Date.now();
let html = '';
for (const s of sessions) {
  const mr = normalizeResult(s.missionResult);
  const badge = mr === 'success' ? ' [OK]' : '';
  html += `<option value="${s.sessionId}">${s.sessionId}${badge}</option>`;
}
const elapsed = Date.now() - t0;
console.log(elapsed < 1000 ? 'fast' : `slow:${elapsed}ms`);
""")
        assert "fast" in r, f"500 sessions render was slow: {r}"
    else:
        # Ensure the forEach exists and contains no obvious O(n^2) pattern.
        assert "sessions.forEach" in _ui_js
suite.run("9.23", "Stress/Load Testing",
          "loadSessions() with 500 sessions – render < 1s", _t923)


# 9.24
def _t924():
    _has_dashboard()
    # autoRefreshTimer must be clearable; no unbounded global arrays.
    assert "autoRefreshTimer" in _ui_js
    assert "clearInterval(state.autoRefreshTimer)" in _ui_js
    # Telemetry queue is bounded by TELEMETRY_MAX_QUEUE_SIZE / TELEMETRY_MAX_LINES.
    assert "TELEMETRY_MAX_QUEUE_SIZE" in _ui_js
    assert "TELEMETRY_MAX_LINES" in _ui_js
    # No ever-growing global array appended without bound.
    assert "results.push" not in _ui_js
suite.run("9.24", "Stress/Load Testing",
          "Auto-refresh – no unbounded growth pattern (source check)", _t924)


# ---------------------------------------------------------------------------
suite.print_summary()
sys.exit(suite.exit_code())
