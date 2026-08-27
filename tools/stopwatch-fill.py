#!/usr/bin/env python3
"""Fill in everything after the key is opened.

Usage (from the repo root, after all five decisions are written):
    python3 tools/stopwatch-fill.py >> report/findings/stopwatch-review-2026-08-26.md
"""
import glob, json, os, re, sys

REPO = os.path.expanduser("~/Developer-Agent-Tokenomics-Decision-Lab")
KEY = os.path.expanduser("~/stopwatch-key.txt")


def parse_key(text):
    """Key format: 'candidate-a  results/<dataset>/<run_id>/agent-solution.diff'."""
    out = {}
    for line in text.splitlines():
        m = re.match(r"\s*candidate[-_ ]?([a-e])\b\s+(\S+)", line, re.I)
        if not m:
            continue
        letter, path = m.group(1).lower(), m.group(2)
        parts = [p for p in path.split("/") if "__" in p]
        out[letter] = parts[0] if parts else path
    return out

def find_run_dir(run_id):
    hits = glob.glob(os.path.join(REPO, "results", "*", run_id))
    if hits:
        return hits[0]
    stem = run_id.split("__")[0:3]
    if len(stem) == 3:
        pat = os.path.join(REPO, "results", "*", "__".join(stem) + "__*")
        hits = glob.glob(pat)
        if hits:
            return hits[0]
    return None


def load(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return {}


def dig(d, *keys, default="-"):
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return d if d not in (None, "") else default


def row(letter, run_id):
    rd = find_run_dir(run_id)
    if not rd:
        return f"| {letter} | `{run_id}` | NOT FOUND | - | - | - | - | - |"
    res = load(os.path.join(rd, "result.json"))
    qual = load(os.path.join(rd, "quality-score.json"))
    cost = load(os.path.join(rd, "recost.json"))

    dataset = os.path.basename(os.path.dirname(rd))
    arm = dig(res, "configuration_id")
    task = dig(res, "task_id")
    verdict = dig(res, "acceptance", "result")
    public = dig(res, "acceptance", "public_gate")

    # quality: score / max, and fabrications if recorded
    q = "-"
    for a, b in (("score", "max"), ("median", "max_possible"), ("value", "max")):
        s, m = dig(qual, a), dig(qual, b)
        if s != "-" and m != "-":
            q = f"{s}/{m}"
            break
    fab = "-"
    for k in ("fabrications", "fabrications_total", "fabricated"):
        v = dig(qual, k)
        if v != "-":
            fab = v
            break

    usd = dig(cost, "marginal_operating_usd", "value")
    bound = dig(cost, "bound", default="")
    if usd != "-":
        usd = f"{'≤' if bound == 'upper' else ''}${float(usd):.4f}"

    return (f"| {letter} | `{run_id}` | {task} | **{arm}** | {verdict} "
            f"| {public} | {q} (fab {fab}) | {usd} |")


def main():
    if not os.path.exists(KEY):
        sys.exit(f"key file not found: {KEY}")
    mapping = parse_key(open(KEY).read())
    if not mapping:
        sys.exit(f"could not parse {KEY} — paste its contents and adjust parse_key()")

    print("\n## After opening the key (auto-filled)\n")
    print("| Cand | Run id | Task | Arm | Sealed verdict | Public gate | Quality | Cost/attempt |")
    print("|---|---|---|---|---|---|---|---|")
    for letter in sorted(mapping):
        print(row(letter, mapping[letter]))
    print("\n*Auto-filled by `tools/stopwatch-fill.py` from the run artifacts. "
          "Cost is the run's own recost figure; `≤` marks a cache-blind upper bound.*")


if __name__ == "__main__":
    main()
