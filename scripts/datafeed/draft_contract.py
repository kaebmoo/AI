"""Draft a contract from a bundle's data, or score drafts against contracts an owner wrote (Plan 8 §9.3).

    # one bundle (a folder of CSV / parquet, or a registered source) → draft YAML with evidence + questions
    python -m scripts.datafeed.draft_contract draft /path/to/bundle --domain expense -o expense.draft.yaml
    python -m scripts.datafeed.draft_contract draft --source datafeed_expense

    # NT-Report as the answer key: draft every domain with the real contract hidden, then compare
    python -m scripts.datafeed.draft_contract score --dist ../NT-Report/DataFeed/dist \
        --contracts ../NT-Report/DataFeed/contracts \
        --expect ebt.fact_ebt=expense.fact_expense --expect ebt.fact_ebt=sales.fact_sales

Reads files read-only; writes nothing but the output file. No LLM.
"""
import argparse
import itertools
import json
import sys
import time
from pathlib import Path

import yaml

from app.services import contract_draft as cd


def source_root(name: str) -> Path:
    from sqlalchemy import text

    from app.db.session import config_engine
    with config_engine.connect() as conn:
        root = conn.execute(text("SELECT root_path FROM data_sources WHERE name = :n"), {"n": name}).scalar()
    if not root:
        sys.exit(f"source {name!r} has no root_path in data_sources")
    return Path(root)


def domain_of(root: Path) -> str:
    return root.parent.name if root.name == "latest" else root.name


def dump(doc, out):
    text = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=140)
    if out:
        Path(out).write_text(text, encoding="utf-8")
        print(f"wrote {out}")
    else:
        print(text)


def cmd_draft(args):
    root = source_root(args.source) if args.source else Path(args.root)
    con = cd.connect()
    bundle = cd.draft(con, root, args.domain or domain_of(root))
    dump(cd.to_contract(bundle), args.out)


def cmd_score(args):
    dist, contracts = Path(args.dist), Path(args.contracts)
    domains = args.domains.split(",") if args.domains else sorted(p.stem for p in contracts.glob("*.yaml"))
    con = cd.connect()
    bundles, report = {}, {"domains": {}, "relationships": []}
    for d in domains:
        t0 = time.time()
        bundles[d] = cd.draft(con, dist / d / "latest", d)
        doc = cd.to_contract(bundles[d])
        owner = yaml.safe_load((contracts / f"{d}.yaml").read_text(encoding="utf-8"))
        score = cd.compare(doc, owner)
        score["seconds"] = round(time.time() - t0, 1)
        score["questions"] = len(doc["draft"]["questions"])
        report["domains"][d] = score
        if args.out_dir:
            dump(doc, Path(args.out_dir) / f"{d}.draft.yaml")
        print(f"\n== {d} ({score['seconds']} s)")
        for k, v in score.items():
            print(f"  {k}: {v}")
    t0 = time.time()
    for a, b in itertools.combinations(domains, 2):
        report["relationships"] += cd.find_bridges(con, bundles[a], bundles[b])
    print(f"\n== relationships ({round(time.time() - t0, 1)} s)")
    for r in report["relationships"]:
        print(f"  {r['left']}:{r['left_measure']} = {r['right']}:{r['right_measure']}  by {' × '.join(r['grain'])}  "
              f"{r['cells_matched']}/{r['cells']} cells ({r['rate']:.1%}), exceptions {len(r['exceptions'])}")
    report["expected"] = {}
    for e in args.expect or []:
        left, right = e.split("=")
        hit = [r for r in report["relationships"] if {r["left"], r["right"]} == {left, right}]
        report["expected"][e] = bool(hit)
        print(f"  expected {e}: {'FOUND' if hit else 'missing'}")
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"wrote {args.out}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draft")
    d.add_argument("root", nargs="?")
    d.add_argument("--source", help="a registered source (data_sources.name) instead of a folder")
    d.add_argument("--domain")
    d.add_argument("-o", "--out")
    s = sub.add_parser("score")
    s.add_argument("--dist", required=True)
    s.add_argument("--contracts", required=True)
    s.add_argument("--domains")
    s.add_argument("--expect", action="append", help="left.dataset=right.dataset a relationship should link")
    s.add_argument("--out-dir", help="also write each draft YAML here")
    s.add_argument("-o", "--out", help="report JSON")
    args = p.parse_args()
    if args.cmd == "draft" and not (args.root or args.source):
        p.error("draft needs a folder or --source")
    {"draft": cmd_draft, "score": cmd_score}[args.cmd](args)


if __name__ == "__main__":
    main()
