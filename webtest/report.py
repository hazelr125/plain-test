import html
import json


def write(result, test, start_url, out_dir):
    (out_dir / "report.json").write_text(json.dumps(
        {"test": test, "start_url": start_url, **result}, indent=2))
    rows = "".join(
        f"<tr><td>{s['step']}</td><td>{html.escape(s.get('desc') or s.get('action', ''))}</td>"
        f"<td>{html.escape(s.get('reason', ''))}</td><td>{html.escape(s.get('result', ''))}</td></tr>"
        for s in result["steps"])
    color = "#1a7f37" if result["verdict"] == "pass" else "#cf222e"
    img = f'<img src="{result["screenshot"]}" style="max-width:100%;border:1px solid #ccc">' if result["screenshot"] else ""
    (out_dir / "report.html").write_text(f"""<!doctype html><meta charset="utf-8"><title>Test report</title>
<body style="font-family:system-ui;max-width:900px;margin:2em auto;padding:0 1em">
<h1 style="color:{color}">{result['verdict'].upper()}</h1>
<p><b>Test:</b> {html.escape(test)}</p><p><b>Start URL:</b> {html.escape(start_url)}</p>
<p><b>Reason:</b> {html.escape(result['reason'])}</p>
<p><b>Evidence:</b> "{html.escape(result['evidence'])}" (verified on page: {result['evidence_verified']})</p>
<p><b>Final URL:</b> {html.escape(result.get('final_url', ''))} &middot; {result['seconds']}s</p>
<table border="1" cellpadding="6" style="border-collapse:collapse;width:100%"><tr><th>#</th><th>Action</th><th>Reason</th><th>Result</th></tr>{rows}</table>
<h3>Final screenshot</h3>{img}</body>""")
