# Approach and limitations (Task 2)

**Approach.** The tool turns a plain-English test case into a browser run with an observe → decide → act loop. On each step it reads the current page and builds a compact list of visible interactive elements, each with a number, role, label text and current value, plus the visible page text. No raw HTML is sent. An LLM sees the test case, its recent steps and that page view, and replies with one JSON action (click, fill, select, goto, wait, assert, press or finish). The harness validates the action before running it (known action, the target id exists on the current page, a value is present) and executes it with Playwright. Nothing is specific to one website: the start URL and any credentials come from the command line or `--var` placeholders, and the prompt contains no site-specific rules.

**How it decides pass or fail.** To finish, the model must give a verdict and quote evidence copied from the page. The harness checks that the quote really appears in the page text, title or URL. A "pass" with evidence that can't be found is downgraded to FAIL, which guards against the model claiming a pass without proof. Other guardrails: a step limit, stuck detection (the same action three times), per-action timeouts, temperature 0, and aborting after three invalid replies in a row. Each run writes an HTML report, a JSON report and a final screenshot.

**Limitations.**
- Results depend on the model. Smaller models need tests that name the exact visible text that proves success.
- The evidence check only proves that the quoted text is somewhere on the page. A vague test can pass on loosely related text, so tests should state specific expectations.
- Only native elements and simple interactions are supported. Iframes, shadow DOM, file uploads, drag and drop, date pickers, custom (non-`<select>`) dropdowns, CAPTCHAs and 2FA are not handled. The model sees only the first 80 visible elements and about 1,500 characters of page text per step, so on long pages it can miss things.
- A click can time out even though it worked (slow navigation, cookie popups), which can waste a step until the agent re-observes.
- One test case per run, with no retries on transient LLM errors and no parallel runs.
- Privacy: the test text, including any password, and the page contents are sent to the LLM provider, so use demo accounts only.
- It has been tried on a small number of sites and flows (login tests), not on a wide range of sites or longer multi-page journeys.