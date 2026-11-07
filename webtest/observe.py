"""Compact page view: numbered interactive elements + visible text (no raw HTML)."""

_JS = r"""
() => {
  document.querySelectorAll('[data-agent-id]').forEach(e => e.removeAttribute('data-agent-id'));
  const sel = 'a[href],button,input,select,textarea,summary,[role=button],[role=link],' +
              '[role=checkbox],[role=tab],[role=menuitem],[role=option],[onclick]';
  const out = []; let id = 1;
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    if (r.width < 2 || r.height < 2 || cs.visibility === 'hidden' || cs.display === 'none') continue;
    const tag = el.tagName.toLowerCase(), type = (el.getAttribute('type') || '').toLowerCase();
    if (tag === 'input' && type === 'hidden') continue;
    el.setAttribute('data-agent-id', String(id));
    const lbl = el.labels && el.labels[0] ? el.labels[0].innerText : '';
    let text = el.getAttribute('aria-label') || lbl || '';
    if (!text && (type === 'submit' || type === 'button')) text = el.value || '';
    if (!text) text = (tag === 'input' || tag === 'textarea') ? '' : (el.innerText || '');
    if (!text) text = el.getAttribute('placeholder') || el.title || el.name || el.id || '';
    const o = {id, tag, role: el.getAttribute('role') || '', type,
               text: text.replace(/\s+/g, ' ').trim().slice(0, 60),
               disabled: !!el.disabled};
    if (tag === 'input' || tag === 'textarea') {
      if (type === 'checkbox' || type === 'radio') o.checked = el.checked;
      else o.value = type === 'password' ? (el.value ? '***' : '') : (el.value || '').slice(0, 40);
      o.placeholder = (el.getAttribute('placeholder') || '').slice(0, 40);
    }
    if (tag === 'select') {
      o.options = [...el.options].slice(0, 15).map(x => x.text.trim());
      o.value = el.options[el.selectedIndex] ? el.options[el.selectedIndex].text.trim() : '';
    }
    out.push(o); id++;
    if (out.length >= 80) break;
  }
  return {title: document.title, url: location.href,
          text: document.body ? document.body.innerText : '', elements: out};
}
"""


def observe(page):
    last = None
    for _ in range(3):  # retry if a navigation interrupts evaluation
        try:
            return page.evaluate(_JS)
        except Exception as e:  # noqa: BLE001
            last = e
            page.wait_for_timeout(500)
    raise last


def norm(s: str) -> str:
    return " ".join((s or "").split()).lower()


def render(view) -> str:
    lines = []
    for e in view["elements"]:
        kind = e["tag"] + (f"[{e['type']}]" if e["type"] else "") + (f"({e['role']})" if e["role"] else "")
        s = f'[{e["id"]}] {kind} "{e["text"]}"'
        if "value" in e:
            s += f' value="{e["value"]}"'
        if "checked" in e:
            s += f' checked={e["checked"]}'
        if e.get("placeholder") and not e["text"]:
            s += f' placeholder="{e["placeholder"]}"'
        if e.get("options"):
            s += " options=" + "|".join(e["options"])
        if e["disabled"]:
            s += " DISABLED"
        lines.append(s)
    text = " ".join(view["text"].split())[:1500]
    return (f"URL: {view['url']}\nTitle: {view['title']}\n"
            f"Interactive elements:\n" + ("\n".join(lines) or "(none)") +
            f"\n\nVisible text (truncated):\n{text}")
