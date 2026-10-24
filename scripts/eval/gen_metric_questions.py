"""Write Thai metric questions with a compiler-on-parquet oracle.

Usage:
    python -m scripts.eval.gen_metric_questions --contract ebt.yaml --dist dist/ebt/latest --period 202609
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import warnings

import yaml

# The AI package imports Chroma, whose Python 3.14 compatibility warning is unrelated to this CLI.
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Core Pydantic V1 functionality isn't compatible.*", category=UserWarning)
    from scripts.eval.metric_eval_lib import generate


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--period", type=int, required=True)
    parser.add_argument("--phrasings", type=int, default=3)
    parser.add_argument("--max-rows", type=int, default=50)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        contract = yaml.safe_load(args.contract.read_text(encoding="utf-8"))
        spec = generate(contract, args.dist, args.period, phrasings=args.phrasings,
                        max_rows=args.max_rows, contract_name=str(args.contract))
        output = args.out or PROJECT_ROOT / "eval_results" / f"metric_{contract['domain']}_{args.period}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        sys.exit("error: " + " ".join(str(exc).splitlines()))
    questions = spec["questions"]
    print("Questions per shape: " + json.dumps(Counter(q["shape"] for q in questions), sort_keys=True))
    print(f"Classes: {len({q['class'] for q in questions})}; questions: {len(questions)}")
    print("Skipped per reason: " + json.dumps(Counter(s["reason"] for s in spec["skipped"]), sort_keys=True))
    print(f"Output: {output}")


if __name__ == "__main__":
    main()
