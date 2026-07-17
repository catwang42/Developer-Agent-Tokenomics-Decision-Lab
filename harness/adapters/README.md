# Adapters (built in Phase 3)
claude_code.py  - Product A; usage from claude -p --output-format json metadata (authoritative)
agy.py          - Product B; WORKSHOP-OWNED wrapper: our exit codes/timeouts; records the
                  product selector label verbatim; unexposed usage -> unavailable
hybrid_c5.py    - integrated workflow; two billing legs tagged; frontier-share diagnostic
stub_*.py       - synthetic-fixture adapters for tests ONLY (never write under results/)
