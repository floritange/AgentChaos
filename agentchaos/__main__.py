# python -m agentchaos list            → list all 65 fault experiments
# python -m agentchaos list --category crash  → filter by category
import sys


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"

    if cmd == "list":
        import agentchaos

        # optional --category filter
        category = None
        if "--category" in sys.argv:
            idx = sys.argv.index("--category")
            if idx + 1 < len(sys.argv):
                category = sys.argv[idx + 1]

        if category:
            by_cat = agentchaos.list_faults_by_category()
            faults = by_cat.get(category, [])
            if not faults:
                print(f"Unknown category: {category}")
                print(f"Available: {', '.join(by_cat.keys())}")
                sys.exit(1)
            print(f"[{category}] {len(faults)} faults:")
            for name in faults:
                print(f"  {name}")
        else:
            all_faults = agentchaos.list_faults()
            print(f"AgentChaos v{agentchaos.__version__} — {len(all_faults)} fault experiments\n")
            for name in all_faults:
                print(f"  {name}")
            print("\nUsage:")
            print("  import agentchaos")
            print("  agentchaos.inject('llm_error_single')  # inject fault")
            print("  result = await my_agent(query)         # agent unaware")
            print("  agentchaos.disable()                   # stop")
            print("  agentchaos.save_trace('trace.json')    # save trace")

    elif cmd in ("-h", "--help", "help"):
        print("agentchaos — Chaos engineering for robust agent evaluation")
        print()
        print("Commands:")
        print("  list [--category <cat>]   List all 65 fault experiments")
        print()
        print("Usage (Python SDK):")
        print("  import agentchaos")
        print("  agentchaos.inject('llm_error_single')")
        print("  result = await my_agent(query)")
        print("  agentchaos.disable()")
        print("  agentchaos.save_trace('trace.json')")
        print()
        print("Examples:")
        print("  python examples/agent_openai.py")
        print("  python examples/eval_batch.py --limit 3")

    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python -m agentchaos [list|help]")
        sys.exit(1)


if __name__ == "__main__":
    main()
