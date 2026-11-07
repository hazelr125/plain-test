"""observe -> decide -> act loop with validation, guardrails and evidence checking."""
import json
import re
import time
from urllib.parse import urljoin

from . import llm
from .observe import norm, observe, render

ACTIONS = {"click", "fill", "select", "goto", "wait", "assert", "press", "finish"}
NEEDS_TARGET = {"click", "fill", "select"}
NEEDS_VALUE = {"fill", "select", "goto", "assert", "press"}

SYSTEM = """You are a careful QA engineer driving a real browser to run ONE test case.
Each turn you get the test case, your previous steps, and a compact view of the current page.
Reply with ONE JSON object and nothing else:
{"action": "click|fill|select|goto|wait|assert|press|finish", "target_id": <int>, "value": "<string>", "reason": "<short>"}
Rules:
- click/fill/select need target_id (the [number] from the element list). fill/select/goto/assert/press need value.
- goto value = URL. press value = a key such as Enter. wait value = seconds (max 10).
- assert value = text that must be visible on the page right now (checked by the harness).
- Use ONLY data (usernames, passwords, values) given in the test case. Never invent credentials.
- Dismiss cookie banners or popups only if they block progress.
- Do not leave the site under test unless the test case says so.
- To end, use {"action":"finish","verdict":"pass"|"fail","evidence":"<text copied EXACTLY from the visible page>","reason":"<short>"}.
  A pass needs evidence quoted verbatim from the current page proving the expected outcome (e.g. a heading).
  Fail if the expected outcome is not shown, an error appears, or you are stuck.
- Element ids change after every action; always use ids from the latest page view."""


def extract_json(raw: str):
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ValueError("no JSON object found")
    return json.loads(m.group(0))


def validate(raw: str, valid_ids: set):
    d = extract_json(raw)
    a = d.get("action")
    if a not in ACTIONS:
        raise ValueError(f"unknown action {a!r}")
    if a in NEEDS_TARGET:
        if not isinstance(d.get("target_id"), int) or d["target_id"] not in valid_ids:
            raise ValueError(f"target_id {d.get('target_id')!r} is not in the current element list")
    if a in NEEDS_VALUE and not isinstance(d.get("value"), str):
        raise ValueError(f"'{a}' needs a string value")
    if a == "finish":
        if d.get("verdict") not in ("pass", "fail"):
            raise ValueError("finish needs verdict 'pass' or 'fail'")
        d.setdefault("evidence", "")
    d.setdefault("reason", "")
    return d


def build_prompt(test, view, history):
    hist = "\n".join(f"{i+1}. {h}" for i, h in enumerate(history[-12:])) or "(none yet)"
    return f"TEST CASE:\n{test}\n\nPREVIOUS STEPS:\n{hist}\n\nCURRENT PAGE:\n{render(view)}"


def describe(d, view):
    a = d["action"]
    if a in NEEDS_TARGET:
        el = next((e for e in view["elements"] if e["id"] == d["target_id"]), {})
        t = f'#{d["target_id"]} "{el.get("text", "")}"'
        if a == "fill":
            shown = "***" if el.get("type") == "password" else d["value"]
            return f'fill {t} with "{shown}"'
        return f'{a} {t}' + (f' -> "{d["value"]}"' if a == "select" else "")
    return a + (f' "{d["value"]}"' if "value" in d else "")


def execute(page, d, view):
    loc = lambda: page.locator(f'[data-agent-id="{d["target_id"]}"]').first  # noqa: E731
    a = d["action"]
    if a == "click":
        loc().click(timeout=6000)
    elif a == "fill":
        loc().fill(d["value"], timeout=6000)
    elif a == "select":
        try:
            loc().select_option(label=d["value"], timeout=6000)
        except Exception:  # noqa: BLE001
            loc().select_option(value=d["value"], timeout=6000)
    elif a == "goto":
        page.goto(urljoin(view["url"], d["value"]), wait_until="domcontentloaded", timeout=20000)
    elif a == "press":
        page.keyboard.press(d["value"])
    elif a == "wait":
        try:
            secs = min(float(d.get("value") or 1), 10)
        except ValueError:
            secs = 1
        page.wait_for_timeout(int(secs * 1000))


def settle(page):
    try:
        page.wait_for_load_state("domcontentloaded", timeout=5000)
        page.wait_for_load_state("networkidle", timeout=3000)
    except Exception:  # noqa: BLE001 - networkidle often never happens; fine
        pass
    page.wait_for_timeout(300)


def run(test, start_url, out_dir, max_steps=15, headed=False):
    from playwright.sync_api import sync_playwright

    log, history = [], []
    result = {"verdict": "fail", "reason": "", "evidence": "", "evidence_verified": False}
    t0 = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        ctx.set_default_timeout(8000)
        page = ctx.new_page()
        try:
            page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
            settle(page)
            last_sig, repeats, bad = None, 0, 0
            for step in range(1, max_steps + 1):
                if len(ctx.pages) > 1:  # a click opened a new tab
                    page = ctx.pages[-1]
                    settle(page)
                view = observe(page)
                ids = {e["id"] for e in view["elements"]}
                entry = {"step": step, "url": view["url"]}
                try:
                    raw = llm.complete(SYSTEM, build_prompt(test, view, history))
                    d = validate(raw, ids)
                except RuntimeError as e:  # LLM/transport problem: stop
                    entry.update(action="error", result=str(e))
                    log.append(entry)
                    result["reason"] = f"LLM error: {e}"
                    break
                except Exception as e:  # noqa: BLE001 - bad JSON: tell the model, retry
                    bad += 1
                    entry.update(action="invalid", result=str(e))
                    log.append(entry)
                    history.append(f"(your last reply was invalid: {e})")
                    if bad >= 3:
                        result["reason"] = "Model kept returning invalid JSON"
                        break
                    continue
                bad = 0
                entry.update(action=d["action"], reason=d["reason"], desc=describe(d, view))

                sig = (d["action"], d.get("target_id"), d.get("value"), view["url"])
                repeats = repeats + 1 if sig == last_sig else 1
                last_sig = sig
                if repeats >= 3 and d["action"] != "finish":
                    entry["result"] = "stuck: same action repeated 3 times"
                    log.append(entry)
                    result["reason"] = entry["result"]
                    break

                if d["action"] == "finish":
                    body = norm(view["text"] + " " + view["title"] + " " + view["url"])
                    ev = norm(d["evidence"])
                    verified = bool(ev) and ev in body
                    verdict = d["verdict"]
                    note = d["reason"]
                    if verdict == "pass" and not verified:
                        verdict, note = "fail", f"Model said pass but evidence not found on page: {d['evidence']!r}"
                    result.update(verdict=verdict, reason=note, evidence=d["evidence"], evidence_verified=verified)
                    entry["result"] = f"{verdict.upper()} (evidence verified: {verified})"
                    log.append(entry)
                    break

                try:
                    if d["action"] == "assert":
                        ok = norm(d["value"]) in norm(view["text"])
                        entry["result"] = "assert " + ("passed" if ok else "FAILED")
                    else:
                        execute(page, d, view)
                        settle(page)
                        entry["result"] = "ok"
                except Exception as e:  # noqa: BLE001
                    entry["result"] = "error: " + str(e).splitlines()[0][:160]
                log.append(entry)
                history.append(f'{entry["desc"]} => {entry["result"]}')
            else:
                result["reason"] = f"Hit max steps ({max_steps}) without finishing"
            if not result["reason"]:
                result["reason"] = "Stopped without a verdict"
        except Exception as e:  # noqa: BLE001
            result["reason"] = f"Runner error: {e}"
        shot = out_dir / "final.png"
        try:
            page.screenshot(path=str(shot))
        except Exception:  # noqa: BLE001
            shot = None
        result["final_url"] = page.url
        browser.close()
    result.update(steps=log, screenshot=shot.name if shot else None, seconds=round(time.time() - t0, 1))
    return result
