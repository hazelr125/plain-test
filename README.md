# webtest: plain-English → browser test

Write a test case in plain English, give a start URL, and an LLM drives a real browser (Playwright)
through an **observe → decide → act** loop, then reports PASS/FAIL with verified evidence.
Nothing is specific to one website: URLs and credentials come from the command line or the test text.

## Setup
Requires Python 3.9+.
```bash
python -m venv .venv
.venv\Scripts\activate               # macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium   # one-time, ~150 MB
copy .env.example .env               # macOS/Linux: cp .env.example .env
```
Edit `.env` and add your key. Supported providers (see `.env.example`):
- **Ollama Cloud** (default): `LLM_PROVIDER=ollama`, `OLLAMA_API_KEY`, `LLM_MODEL` (e.g. `gemma4:31b-cloud` or `gpt-oss:120b`)
- **Anthropic**: `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`
- **Any OpenAI-compatible API** (Gemini, Groq, local Ollama): `LLM_PROVIDER=openai`, `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `LLM_MODEL`

Put values on their own line, no quotes needed. Never commit `.env` (it is git-ignored).

## Run
```bash
# test text from a file
python -m webtest -f examples/saucedemo_login.txt -u https://www.saucedemo.com

# test text inline
python -m webtest "Log in with standard_user / secret_sauce. Pass if the heading Products is visible." -u https://www.saucedemo.com

# placeholders keep credentials out of the file
python -m webtest -f examples/phptravels_login.txt -u https://phptravels.net/login \
    --var EMAIL=user@phptravels.com --var PASSWORD=yourpass --headed
```
Options: `--headed` (watch the browser), `--max-steps N` (default 15), `--out DIR`, `--env-file PATH`.
Exit code: `0` = pass, `1` = fail. Each run writes `runs/<timestamp>/report.html`, `report.json`, `final.png`.

phptravels demo credentials and URL are issued on https://phptravels.com/demo.

## Approach
1. **Observe**: injected JS lists visible interactive elements with numbered IDs, role, text and current value
   (passwords masked), plus visible page text. No raw HTML is sent to the model.
2. **Decide**: the model receives the test goal, its last 12 steps and the page view, and must reply with strict JSON:
   `{action: click|fill|select|goto|wait|assert|press|finish, target_id, value, reason}` at temperature 0.
3. **Act**: the JSON is validated before anything runs (known action, `target_id` exists on the current page,
   value present). Invalid replies are fed back to the model; three in a row abort the run. IDs are mapped back
   to elements via a `data-agent-id` attribute and executed with Playwright.
4. **Verdict**: `finish` must quote visible page text. The harness checks the quote really exists in the page text,
   title or URL; a "pass" with unverifiable evidence is downgraded to FAIL. This guards against hallucinated passes.
5. **Guardrails**: max steps, stuck detection (same action 3x), per-action timeouts, temperature 0.
6. **Report**: console step log, HTML + JSON summary, final screenshot.

## Limitations
- **LLM dependent**: pass/fail quality depends on the model. Smaller models need explicit pass conditions
  (name the exact visible text that proves success).
- **Weak evidence is possible**: the quote only has to appear somewhere on the page, so vague tests can pass
  on loosely related text. Write specific expectations.
- **Click timeouts are not always failures**: slow navigations or overlays (cookie/consent popups) can make a click
  time out even though it worked; the agent usually recovers by re-observing.
- **Not covered**: iframes, shadow DOM, file uploads, drag-and-drop, CAPTCHAs/2FA, multi-window flows beyond
  switching to the newest tab. Only the top 80 visible elements are shown to the model per step.
- **Privacy**: test text (including any password) and page contents are sent to the LLM provider. Use demo accounts.
- **No retries or parallelism**: one test case per run; LLM calls are not retried on transient errors.

## Files
```
webtest/cli.py      CLI, {{placeholder}} filling, .env loader
webtest/agent.py    loop, JSON validation, guardrails, evidence check
webtest/observe.py  page → numbered element list
webtest/llm.py      stdlib LLM client (ollama / anthropic / openai-compatible)
webtest/report.py   report.json + report.html
examples/           sample test cases
```