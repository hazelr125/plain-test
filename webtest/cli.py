import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from . import agent, report


def load_env(path):
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            v = v.strip()
            if v[:1] in "\"'":
                v = v.strip('"').strip("'")
            else:
                v = v.split(" #")[0].strip()
            os.environ.setdefault(k.strip(), v)
def main():
    ap = argparse.ArgumentParser(prog="webtest", description="Run a plain-English test in a real browser.")
    ap.add_argument("test", nargs="?", help="test case text (or use --file)")
    ap.add_argument("--file", "-f", help="read test case from a text file")
    ap.add_argument("--url", "-u", required=True, help="start URL")
    ap.add_argument("--var", "-v", action="append", default=[], metavar="KEY=VALUE",
                    help="fill {{KEY}} placeholders in the test text (repeatable)")
    ap.add_argument("--max-steps", type=int, default=15)
    ap.add_argument("--headed", action="store_true", help="show the browser window")
    ap.add_argument("--out", default="runs", help="output folder (default: runs)")
    ap.add_argument("--env-file", default=".env")
    a = ap.parse_args()

    load_env(a.env_file)
    test = Path(a.file).read_text() if a.file else a.test
    if not test:
        ap.error("give the test case as text or with --file")
    vars_ = dict(v.split("=", 1) for v in a.var if "=" in v)
    test = re.sub(r"\{\{(\w+)\}\}", lambda m: vars_.get(m.group(1), os.environ.get(m.group(1), m.group(0))), test).strip()
    if re.search(r"\{\{\w+\}\}", test):
        ap.error("unfilled {{placeholders}} in test text - pass them with --var KEY=VALUE")

    out_dir = Path(a.out) / datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Running: {test}\nStart:   {a.url}\n")

    result = agent.run(test, a.url, out_dir, a.max_steps, a.headed)
    for s in result["steps"]:
        print(f"step {s['step']:>2}: {s.get('desc') or s.get('action')}  ->  {s.get('result', '')}")
    print(f"\n{result['verdict'].upper()}: {result['reason']}")
    if result["evidence"]:
        print(f'Evidence: "{result["evidence"]}" (verified on page: {result["evidence_verified"]})')
    report.write(result, test, a.url, out_dir)
    print(f"Report: {out_dir / 'report.html'}")
    return 0 if result["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
