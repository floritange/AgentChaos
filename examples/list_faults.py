# examples/list_faults.py — List all available fault experiments
#
# Usage:  uv run python examples/list_faults.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agentchaos

faults = agentchaos.list_faults()
print(f"AgentChaos v{agentchaos.__version__} — {len(faults)} fault experiments\n")

categories = agentchaos.list_faults_by_category()
for cat, items in categories.items():
    print(f"[{cat}] {len(items)} fault types:")
    for item in items:
        experiments = list(item["experiments"].values())
        print(f"  {item['base_name']}: {item['description']}")
        print(f"    experiments: {', '.join(experiments)}")
    print()

# positional experiments (not in categories)
positional = [f for f in faults if "pos_" in f]
if positional:
    print(f"[positional] {len(positional)} experiments:")
    for name in sorted(positional):
        print(f"  {name}")
    print()

print(f"Total: {len(faults)} experiments")
