"""Allow ``python -m agenteval`` to invoke the AgentEval Forge CLI."""

from agenteval.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
