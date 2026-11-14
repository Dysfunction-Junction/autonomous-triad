"""Compare autonomous-triad (A) with sovereign-exocortex/packages/triad (B).

Writes docs/TRIAD_V34_MERGE_MAP.md and prints a JSON summary. Read-only apart from that file.
Override checkout locations with TRIAD_A and TRIAD_EXO.
"""

import ast
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.request
from datetime import datetime

A = pathlib.Path(os.environ.get("TRIAD_A", r"C:\Users\micha\projects\autonomous-triad"))
EXO = pathlib.Path(os.environ.get("TRIAD_EXO", r"C:\Users\micha\projects\sovereign-exocortex"))
B = EXO / "packages" / "triad"
BROKER = EXO.parent / "sovereign-exocortex-broker"
OUT = pathlib.Path(os.environ.get("TRIAD_OUT", str(A / "docs" / "TRIAD_V34_MERGE_MAP.md")))
VENV_PY = A / ".venv" / "Scripts" / "python.exe"
PYTHON = str(VENV_PY) if VENV_PY.exists() else sys.executable


def run(args, inp=None, cwd=None):
    r = subprocess.run(args, capture_output=True, input=inp, cwd=cwd)
    return r.stdout.decode("utf-8", "replace")


def git(repo, *a, inp=None):
    return run(["git", "-C", str(repo), *a], inp=inp)


def ls(repo, *paths):
    return [p for p in git(repo, "ls-files", "-z", "--", *paths).split("\0") if p]


def last(repo, path):
    return git(repo, "log", "-1", "--format=%h %ad %s", "--date=short", "--", path).strip()


def nb(p):
    return p.read_bytes().replace(b"\r\n", b"\n")


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def inventory(path):
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    out = {}

    def walk(node, prefix=""):
        for n in getattr(node, "body", []):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out[prefix + n.name] = (n.lineno, norm(ast.get_source_segment(src, n)))
            elif isinstance(n, ast.ClassDef):
                out[prefix + n.name] = (n.lineno, None)
                walk(n, prefix + n.name + ".")
            elif not prefix and isinstance(n, (ast.Assign, ast.AnnAssign)):
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                for t in targets:
                    if isinstance(t, ast.Name) and t.id.isupper():
                        out["const " + t.id] = (n.lineno, norm(ast.get_source_segment(src, n)))

    walk(tree)
    return out


def module_test_funcs(path):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return 0
    return sum(1 for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test"))


def collect_ids(root):
    out = run([PYTHON, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", "triad/tests"], cwd=str(root))
    return {line.strip() for line in out.splitlines() if "::" in line}


def commit_presence(repo, commit, ref, path_prefix=None, remap=None):
    args = ["show", "--format=", "-U0", "--no-color", commit]
    if path_prefix:
        args += ["--", path_prefix]
    cur = None
    present = total = 0
    cache = {}
    for line in git(repo, *args).splitlines():
        if line.startswith("+++ "):
            p = line[4:].strip()
            cur = p[2:] if p.startswith("b/") else None
            continue
        if cur and line.startswith("+") and not line.startswith("+++"):
            s = line[1:].strip()
            if len(s) < 8:
                continue
            target_repo, target_path = remap(cur) if remap else (repo, cur)
            key = (str(target_repo), target_path)
            if key not in cache:
                cache[key] = git(target_repo, "show", f"{ref}:{target_path}") if target_path else ""
            total += 1
            if s in cache[key]:
                present += 1
    return present, total


def get_json(url):
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=3) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        return {"error": str(e)}


def main():
    summary = {}
    md = []
    a_head = git(A, "rev-parse", "--short", "HEAD").strip()
    exo_head = git(EXO, "rev-parse", "--short", "HEAD").strip()
    exo_branch = git(EXO, "rev-parse", "--abbrev-ref", "HEAD").strip()
    summary.update(A_head=a_head, B_head=f"{exo_branch}@{exo_head}")
    md.append("# Triad v3.4 merge map (generated)\n")
    md.append(
        f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} by `scripts/triad_unify_audit.py` from "
        f"`autonomous-triad@{a_head}` (side **A**) and `sovereign-exocortex@{exo_head}` ({exo_branch}) "
        "`packages/triad` (side **B**). Tracked files only, CRLF normalized to LF. Regenerate before acting.\n"
    )

    ta = ls(A)
    tb = [p[len("packages/triad/"):] for p in ls(EXO, "packages/triad")]
    sa, sb = set(ta), set(tb)
    shared = sorted(sa & sb)
    same, diff = [], []
    for rel in shared:
        pa, pb = A / rel, B / rel
        (same if pa.is_file() and pb.is_file() and nb(pa) == nb(pb) else diff).append(rel)
    only_a, only_b = sorted(sa - sb), sorted(sb - sa)
    summary["tracked"] = {"A": len(ta), "B": len(tb), "shared": len(shared), "identical": len(same),
                          "diverged": len(diff), "only_A": len(only_a), "only_B": len(only_b)}

    md.append("## 1. Tracked files\n")
    md.append(f"- A tracks {len(ta)} files; B tracks {len(tb)} under `packages/triad`.")
    md.append(f"- Shared paths: {len(shared)} ({len(same)} identical, {len(diff)} diverged).")
    md.append(f"- Only in A: {len(only_a)}. Only in B: {len(only_b)}.\n")
    md.append("### Only in B (must be ported into A)\n")
    for p in only_b:
        md.append(f"- `{p}` (last B commit: {last(EXO, 'packages/triad/' + p)})")
    md.append("\n### Only in A, under `triad/` or packaging (B lacks them)\n")
    for p in only_a:
        if p.startswith(("triad/", "pyproject", "skills/", "bin/", "uv.lock")):
            md.append(f"- `{p}`")
    md.append("\n### Diverged shared files\n")
    md.append("| File | Last A commit | Last B commit |")
    md.append("|---|---|---|")
    for p in diff:
        md.append(f"| `{p}` | {last(A, p)} | {last(EXO, 'packages/triad/' + p)} |")
    md.append("")

    md.append("## 2. Definition-level map for diverged Python files\n")
    md.append("`A-only` and `B-only` are definitions present on one side. `changed` means both sides define it "
              "with different bodies. Line numbers are per side.\n")
    func_summary = {}
    for p in diff:
        if not p.endswith(".py"):
            continue
        ia, ib = inventory(A / p), inventory(B / p)
        a_only = sorted((k, ia[k][0]) for k in ia if k not in ib)
        b_only = sorted((k, ib[k][0]) for k in ib if k not in ia)
        changed = sorted((k, ia[k][0], ib[k][0]) for k in ia
                         if k in ib and ia[k][1] is not None and ia[k][1] != ib[k][1])
        func_summary[p] = {"A_only": len(a_only), "B_only": len(b_only), "changed": len(changed)}
        md.append(f"### `{p}`\n")
        md.append(f"A-only {len(a_only)}, B-only {len(b_only)}, changed {len(changed)}.\n")
        if a_only:
            md.append("- **A-only:** " + ", ".join(f"`{k}` (A:{la})" for k, la in a_only))
        if b_only:
            md.append("- **B-only:** " + ", ".join(f"`{k}` (B:{lb})" for k, lb in b_only))
        if changed:
            md.append("- **changed:** " + ", ".join(f"`{k}` (A:{la} / B:{lb})" for k, la, lb in changed))
        md.append("")
    summary["definition_map"] = func_summary

    ida, idb = collect_ids(A), collect_ids(B)
    summary["tests"] = {"A": len(ida), "B": len(idb), "both": len(ida & idb), "A_only": len(ida - idb),
                        "B_only": len(idb - ida), "union": len(ida | idb)}
    md.append("## 3. Collected test IDs (pytest --collect-only)\n")
    md.append(f"- A {len(ida)}, B {len(idb)}, both {len(ida & idb)}, A-only {len(ida - idb)}, "
              f"B-only {len(idb - ida)}, union {len(ida | idb)}.")
    md.append("- Same-named tests whose bodies differ are listed as `changed` in section 2.\n")
    md.append("### A-only test IDs\n")
    md.extend(f"- `{t}`" for t in sorted(ida - idb))
    md.append("\n### B-only test IDs\n")
    md.extend(f"- `{t}`" for t in sorted(idb - ida))
    md.append("")
    md.append("### Module-level (pytest-only) test functions\n")
    md.append("`python -m unittest discover` does not collect these.\n")
    md.append("| Test file | A | B |")
    md.append("|---|---|---|")
    pytest_only = {}
    for tf in sorted({p for p in sa | sb if p.startswith("triad/tests/test_") and p.endswith(".py")}):
        ca = module_test_funcs(A / tf) if (A / tf).is_file() else 0
        cb = module_test_funcs(B / tf) if (B / tf).is_file() else 0
        if ca or cb:
            md.append(f"| `{tf}` | {ca} | {cb} |")
            pytest_only[tf] = [ca, cb]
    summary["pytest_only_functions"] = pytest_only
    md.append("")

    md.append("## 4. Change ledger since 2026-09-25\n")
    md.append("### A (`triad/`, packaging, skills, bin)\n")
    md.append("```")
    md.append(git(A, "log", "--since=2026-09-25", "--format=%h %ad %s", "--date=short", "--",
                  "triad", "pyproject.toml", "skills", "bin", "uv.lock").strip())
    md.append("```\n")
    md.append("### B (`packages/triad`)\n")
    md.append("```")
    md.append(git(EXO, "log", "--since=2026-09-25", "--format=%h %ad %s", "--date=short", "--", "packages/triad").strip())
    md.append("```\n")

    md.append("## 5. Branch content not on the default branch\n")
    md.append("Share of each commit's added lines (8+ characters) found verbatim in the same file on the target "
              "branch. Low numbers mean the change is probably not merged.\n")
    md.append("### A branches vs `master`\n")
    md.append("| Ref | Commit | Subject | Present on master |")
    md.append("|---|---|---|---|")
    a_refs = [r for r in git(A, "for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes/origin").split()
              if not r.endswith("HEAD") and r not in ("master", "origin/master", "origin")]
    a_report = {}
    for ref in a_refs:
        for c in git(A, "log", "--format=%h|%s", f"master..{ref}").strip().splitlines():
            if "|" not in c:
                continue
            h, subj = c.split("|", 1)
            pres, tot = commit_presence(A, h, "master")
            md.append(f"| `{ref}` | {h} | {subj} | {pres}/{tot} |")
            a_report.setdefault(ref, []).append([h, subj, pres, tot])
    summary["A_branches"] = a_report

    md.append("\n### B branches vs `origin/main` (commits touching `packages/triad`)\n")
    md.append("| Ref | Commit | Subject | Present on B main | Present on A master |")
    md.append("|---|---|---|---|---|")
    b_refs = [r for r in git(EXO, "for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes/origin").split()
              if not r.endswith("HEAD") and r not in ("main", "origin/main", "origin")]

    def to_a(path):
        return (A, path[len("packages/triad/"):]) if path.startswith("packages/triad/") else (A, None)

    seen, b_report = {}, {}
    for ref in b_refs:
        for c in git(EXO, "log", "--format=%h|%s", f"origin/main..{ref}", "--", "packages/triad").strip().splitlines():
            if "|" not in c:
                continue
            h, subj = c.split("|", 1)
            if h not in seen:
                pb_, tb_ = commit_presence(EXO, h, "origin/main", "packages/triad")
                pa_, ta_ = commit_presence(EXO, h, "master", "packages/triad", remap=to_a)
                seen[h] = (pb_, tb_, pa_, ta_)
            pb_, tb_, pa_, ta_ = seen[h]
            md.append(f"| `{ref}` | {h} | {subj} | {pb_}/{tb_} | {pa_}/{ta_} |")
            b_report.setdefault(ref, []).append([h, subj, pb_, tb_, pa_, ta_])
    summary["B_branches"] = b_report
    md.append("")

    excluded = {"node_modules", ".git", "dist", ".turbo", "__pycache__", ".pytest_cache", ".ruff_cache",
                "target", ".cache", ".venv", "build"}
    files = []
    if BROKER.exists():
        for root, dirs, fs in os.walk(BROKER):
            dirs[:] = [d for d in dirs if d not in excluded]
            files.extend(pathlib.Path(root, f) for f in fs)

    def blob(data):
        return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()

    hashes = {}
    for f in files:
        try:
            data = f.read_bytes()
        except OSError:
            continue
        hashes[f] = {blob(data), blob(data.replace(b"\r\n", b"\n"))}
    all_hashes = sorted({h for s in hashes.values() for h in s})

    def known_in(repo):
        if not all_hashes:
            return set()
        out = git(repo, "cat-file", "--batch-check", inp=("\n".join(all_hashes) + "\n").encode())
        return {line.split()[0] for line in out.splitlines() if line and not line.rstrip().endswith("missing")}

    known = known_in(EXO) | known_in(A)
    unique = sorted(str(f.relative_to(BROKER)) for f, hs in hashes.items() if not (hs & known))
    summary["broker"] = {"exists": BROKER.exists(), "files_scanned": len(hashes), "not_in_any_repo_history": len(unique)}
    md.append("## 6. `sovereign-exocortex-broker` audit\n")
    md.append(f"Scanned {len(hashes)} files outside `node_modules` and caches. {len(unique)} have content that is "
              "not a blob in either repository's object database.\n")
    md.extend(f"- `{u}`" for u in unique[:200])
    md.append("")

    models = get_json("http://127.0.0.1:8080/v1/models")
    props = get_json("http://127.0.0.1:8080/props")
    settings = props.get("default_generation_settings") or {}
    summary["llama_server"] = {
        "models": [m.get("id") for m in models.get("data", [])] if "data" in models else models.get("error"),
        "model_path": props.get("model_path"),
        "n_ctx": settings.get("n_ctx") or props.get("n_ctx"),
    }

    OUT.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
