"""
Contract → context + knowledge generator (PLAN F10 Phase B)
============================================================
Idempotent — safe to re-run after every re-import. Registers the feed_<domain>
context and regenerates its documentation from the contract yaml.

The logic lives in app/services/datafeed_knowledge.py (Plan 7 Phase 2): a registered
file source re-syncs itself when its contract changes, so this script is only needed
for the import (legacy) mode or to force a regen by hand.

Usage:
    python -m scripts.datafeed.gen_docs_from_contract --domain revenue \
        --contract /path/to/DataFeed/contracts/revenue.yaml
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    parser = argparse.ArgumentParser(description="Generate context + docs from DataFeed contract")
    parser.add_argument("--domain", required=True)
    parser.add_argument("--contract", required=True, help="Path to contract yaml")
    args = parser.parse_args()

    from app.db.session import config_engine
    from app.services.datafeed_knowledge import load_contract, mark_brain_dirty, sync_knowledge

    contract, _ = load_contract(args.contract)
    with config_engine.begin() as conn:
        context_name, meta_count, doc_count = sync_knowledge(conn, args.domain, contract)
    print(f"Context '{context_name}' registered; {meta_count} metadata rows; {doc_count} docs")

    # Trigger brain sync so Vanna picks up the new documentation
    mark_brain_dirty()
    print("Brain marked dirty — will re-sync")


if __name__ == "__main__":
    main()
