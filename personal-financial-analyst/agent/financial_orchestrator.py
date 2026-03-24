"""Financial Optimization Orchestrator Agent.

This agent demonstrates the orchestrator-workers pattern using Claude Agent SDK.
It fetches financial data from MCP servers and coordinates specialized sub-agents
to provide comprehensive financial optimization recommendations.
"""

import argparse
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AgentDefinition,
    AssistantMessage,
    ResultMessage,
    TextBlock,
    PermissionResultAllow,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)

logger = logging.getLogger(__name__)


DATA_DIR: Path = Path(__file__).parent.parent / "data"
RAW_DATA_DIR: Path = DATA_DIR / "raw_data"
AGENT_OUTPUTS_DIR: Path = DATA_DIR / "agent_outputs"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _load_prompt(filename: str) -> str:
    """Load prompt from prompts directory.

    Args:
        filename: Name of the prompt file inside the prompts/ directory.

    Returns:
        Prompt text content.
    """
    prompt_path = Path(__file__).parent / "prompts" / filename
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    return prompt_path.read_text()


async def _auto_approve_all(
    tool_name: str,
    input_data: dict,
    context
):
    """Auto-approve all tool calls without prompting.

    Args:
        tool_name: Name of the tool being invoked.
        input_data: Parameters passed to the tool.
        context: SDK-provided context object.

    Returns:
        PermissionResultAllow to approve the tool call.
    """
    logger.debug(f"Auto-approving tool: {tool_name}")
    return PermissionResultAllow()


def _ensure_directories():
    """Ensure all required directories exist."""
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    AGENT_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


def _save_json(
    data: dict,
    filename: str
):
    """Save data to JSON file.

    Args:
        data: Dictionary to persist.
        filename: Target filename inside RAW_DATA_DIR.
    """
    filepath = RAW_DATA_DIR / filename
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    logger.info(f"Saved data to {filepath}")


# ---------------------------------------------------------------------------
# Part 1 – Subscription detection
# ---------------------------------------------------------------------------

def _detect_subscriptions(
    bank_transactions: list[dict],
    credit_card_transactions: list[dict]
) -> list[dict]:
    """Detect subscription services from recurring transactions.

    Filters all transactions (bank + credit-card) for entries flagged as
    recurring, then extracts the service name, absolute amount, and frequency.

    Args:
        bank_transactions: List of bank transaction dicts.
        credit_card_transactions: List of credit card transaction dicts.

    Returns:
        List of subscription dictionaries with service name, amount, frequency.
    """
    subscriptions: list[dict] = []

    all_transactions = bank_transactions + credit_card_transactions

    for txn in all_transactions:
        if txn.get("recurring") is True:
            amount = txn.get("amount", 0)
            subscriptions.append({
                "service": txn.get("description", txn.get("name", "Unknown")),
                "amount": abs(amount),
                "frequency": txn.get("frequency", "monthly"),
            })

    total_monthly = sum(s["amount"] for s in subscriptions)
    logger.info(
        f"Detected {len(subscriptions)} subscriptions "
        f"totalling ${total_monthly:.2f}/month"
    )

    return subscriptions


# ---------------------------------------------------------------------------
# Part 2 – Fetch financial data from MCP servers
# ---------------------------------------------------------------------------

async def _fetch_financial_data(
    username: str,
    start_date: str,
    end_date: str
) -> tuple[dict, dict]:
    """Fetch data from Bank and Credit Card MCP servers.

    Connects to both MCP servers via HTTP, calls the respective transaction
    tools, and persists the raw JSON responses to disk.

    Args:
        username: Username for the account.
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).

    Returns:
        Tuple of (bank_data, credit_card_data) dictionaries.
    """
    logger.info(f"Fetching financial data for {username} from {start_date} to {end_date}")

    # MCP server configuration – keys MUST match the FastMCP server names
    mcp_servers = {
        "Bank Account Server": {
            "type": "http",
            "url": "http://127.0.0.1:5001/mcp",
        },
        "Credit Card Server": {
            "type": "http",
            "url": "http://127.0.0.1:5002/mcp",
        },
    }

    # Use a lightweight agent solely to call the two MCP tools
    options = ClaudeAgentOptions(
        model="haiku",
        system_prompt=(
            "You are a data-fetching assistant. Call the requested tools "
            "and return the raw JSON results. Do not add commentary."
        ),
        mcp_servers=mcp_servers,
        can_use_tool=_auto_approve_all,
        cwd=str(Path(__file__).parent.parent),
    )

    bank_data: dict = {}
    credit_card_data: dict = {}

    async with ClaudeSDKClient(options=options) as client:
        # Fetch bank transactions
        await client.query(
            f"Call the get_bank_transactions tool with "
            f'username="{username}", start_date="{start_date}", end_date="{end_date}". '
            f"Return only the raw JSON result."
        )
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        try:
                            bank_data = json.loads(block.text)
                        except json.JSONDecodeError:
                            bank_data = {"raw_response": block.text, "transactions": []}
            elif isinstance(message, ResultMessage):
                break

        # Fetch credit-card transactions
        await client.query(
            f"Call the get_credit_card_transactions tool with "
            f'username="{username}", start_date="{start_date}", end_date="{end_date}". '
            f"Return only the raw JSON result."
        )
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        try:
                            credit_card_data = json.loads(block.text)
                        except json.JSONDecodeError:
                            credit_card_data = {"raw_response": block.text, "transactions": []}
            elif isinstance(message, ResultMessage):
                break

    # Persist raw data
    _save_json(bank_data, "bank_transactions.json")
    _save_json(credit_card_data, "credit_card_transactions.json")

    return bank_data, credit_card_data


# ---------------------------------------------------------------------------
# Parts 3-5 – Orchestrator
# ---------------------------------------------------------------------------

async def _run_orchestrator(
    username: str,
    start_date: str,
    end_date: str,
    user_query: str
):
    """Main orchestrator agent logic.

    1. Fetches data from MCP servers.
    2. Detects subscriptions from the transactions.
    3. Defines three specialised sub-agents (research, negotiation, tax).
    4. Configures and runs the orchestrator agent (Sonnet).
    5. Streams results in real-time and writes a final report.

    Args:
        username: Username for the account.
        start_date: Start date for analysis.
        end_date: End date for analysis.
        user_query: User's financial question/request.
    """
    logger.info("Starting financial optimization orchestrator")
    logger.info(f"User query: {user_query}")

    _ensure_directories()

    # ------------------------------------------------------------------
    # Step 1: Fetch financial data from MCP servers
    # ------------------------------------------------------------------
    bank_data, credit_card_data = await _fetch_financial_data(
        username,
        start_date,
        end_date,
    )

    # ------------------------------------------------------------------
    # Step 2: Initial analysis – detect subscriptions
    # ------------------------------------------------------------------
    logger.info("Performing initial analysis...")

    bank_transactions = bank_data.get("transactions", [])
    credit_card_transactions = credit_card_data.get("transactions", [])

    subscriptions = _detect_subscriptions(
        bank_transactions,
        credit_card_transactions,
    )

    logger.info(f"Detected {len(subscriptions)} subscriptions")

    # ------------------------------------------------------------------
    # Step 3: Define sub-agents
    # ------------------------------------------------------------------
    research_agent = AgentDefinition(
        description="Research cheaper alternatives for subscriptions and services",
        prompt=_load_prompt("research_agent_prompt.txt"),
        tools=["write"],
        model="haiku",
    )

    negotiation_agent = AgentDefinition(
        description="Create negotiation strategies and scripts for bills and services",
        prompt=_load_prompt("negotiation_agent_prompt.txt"),
        tools=["write"],
        model="haiku",
    )

    tax_agent = AgentDefinition(
        description="Identify tax-deductible expenses and optimization opportunities",
        prompt=_load_prompt("tax_agent_prompt.txt"),
        tools=["write"],
        model="haiku",
    )

    agents = {
        "research_agent": research_agent,
        "negotiation_agent": negotiation_agent,
        "tax_agent": tax_agent,
    }

    # ------------------------------------------------------------------
    # Step 4: Configure orchestrator agent
    # ------------------------------------------------------------------
    mcp_servers = {
        "Bank Account Server": {
            "type": "http",
            "url": "http://127.0.0.1:5001/mcp",
        },
        "Credit Card Server": {
            "type": "http",
            "url": "http://127.0.0.1:5002/mcp",
        },
    }

    working_dir = Path(__file__).parent.parent  # personal-financial-analyst/

    options = ClaudeAgentOptions(
        model="sonnet",
        system_prompt=_load_prompt("orchestrator_system_prompt.txt"),
        mcp_servers=mcp_servers,
        agents=agents,
        can_use_tool=_auto_approve_all,
        cwd=str(working_dir),
    )

    # ------------------------------------------------------------------
    # Step 5: Execute orchestrator
    # ------------------------------------------------------------------
    prompt = f"""Analyze my financial data and {user_query}

I have:
- {len(bank_transactions)} bank transactions
- {len(credit_card_transactions)} credit card transactions
- {len(subscriptions)} identified subscriptions

Subscription details:
{json.dumps(subscriptions, indent=2)}

Please:
1. Identify opportunities for savings
2. Delegate research to the research agent for cheaper alternatives
3. Delegate negotiation strategies to the negotiation agent
4. Delegate tax analysis to the tax agent
5. Read their results and create a final report at data/final_report.md
"""

    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)

        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(block.text, end="", flush=True)
            elif isinstance(message, ResultMessage):
                print()  # trailing newline after streamed output
                logger.info(f"Duration: {message.duration_ms}ms")
                logger.info(f"Cost: ${message.total_cost_usd:.4f}")
                break

    # ------------------------------------------------------------------
    # Step 6: Done
    # ------------------------------------------------------------------
    logger.info("Orchestration complete. Check data/final_report.md for results.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Financial Optimization Orchestrator Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example usage:
    # Basic analysis
    uv run python financial_orchestrator.py \\
        --username john_doe \\
        --start-date 2026-01-01 \\
        --end-date 2026-01-31 \\
        --query "How can I save $500 per month?"

    # Subscription analysis
    uv run python financial_orchestrator.py \\
        --username jane_smith \\
        --start-date 2026-01-01 \\
        --end-date 2026-01-31 \\
        --query "Analyze my subscriptions and find better deals"
""",
    )

    parser.add_argument(
        "--username",
        type=str,
        required=True,
        help="Username for account (john_doe or jane_smith)",
    )

    parser.add_argument(
        "--start-date",
        type=str,
        required=True,
        help="Start date in YYYY-MM-DD format",
    )

    parser.add_argument(
        "--end-date",
        type=str,
        required=True,
        help="End date in YYYY-MM-DD format",
    )

    parser.add_argument(
        "--query",
        type=str,
        required=True,
        help="User's financial question or request",
    )

    return parser.parse_args()


async def main():
    """Main entry point."""
    args = _parse_args()

    await _run_orchestrator(
        username=args.username,
        start_date=args.start_date,
        end_date=args.end_date,
        user_query=args.query,
    )


if __name__ == "__main__":
    asyncio.run(main())