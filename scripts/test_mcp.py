"""
test_mcp.py — Standalone test for the Terraform MCP Registry integration.

Usage:
    python scripts/test_mcp.py
    python scripts/test_mcp.py "I need a GCP Cloud SQL SQL Server instance with private IP"

Requirements:
    - Docker must be running
    - GEMINI_API_KEY must be set in .env
    - pip install mcp
"""
import asyncio
import sys
import time
from pathlib import Path

# Allow importing from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core import config
from app.services.llm_generator import LLMGenerator

SEPARATOR = "=" * 70
LINE     = "-" * 70


def print_header(title: str):
    print(f"\n{SEPARATOR}")
    print(f"  {title}")
    print(SEPARATOR)


def print_section(title: str, content: str):
    print(f"\n{LINE}")
    print(f"  {title}")
    print(LINE)
    print(content.strip())
    print(LINE)


async def run_test(infrastructure_description: str):
    gen = LLMGenerator()

    # Build a minimal prompt similar to what LLMGenerator._build_prompt produces
    prompt = f"""
PROVIDER: AWS
PROJECT: mcp-test-project
ENVIRONMENT: DEV

README CONTEXT:
{infrastructure_description}

Please build the required infrastructure.
"""

    print_header("Terraform MCP Registry Integration Test")
    print(f"  Infrastructure Request:")
    print(f"  {infrastructure_description.strip()}")
    print(SEPARATOR)

    print("\n[1/2] Querying Terraform Registry via MCP...")
    print("       (Docker is spinning up hashicorp/terraform-mcp-server)")
    t0 = time.time()

    context = await gen._gather_mcp_context_async(prompt, session_id="test-mcp")
    elapsed = time.time() - t0

    if context:
        print(f"\n  ✅ MCP context gathered in {elapsed:.1f}s\n")
        print_section("Gathered Registry Context (fed to Gemini Code Generator)", context)
    else:
        print(f"\n  ❌ MCP context gathering failed after {elapsed:.1f}s")
        print("     Check that Docker is running and the image is available:")
        print("       docker pull hashicorp/terraform-mcp-server:latest")
        sys.exit(1)

    print("\n\n[2/2] Generating Terraform code using gathered context...")
    final_prompt = prompt + f"\n\n--- MCP REGISTRY CONTEXT ---\n{context}\n----------------------------"
    bundle = gen._call(final_prompt, session_id="test-mcp")

    print_section("main.tf", bundle.main_tf or "(empty)")
    print_section("variables.tf", bundle.variables_tf or "(empty)")
    print_section("outputs.tf", bundle.outputs_tf or "(empty)")
    print_header("✅ Test Complete")


if __name__ == "__main__":
    description = (
        " ".join(sys.argv[1:])
        or "I need a Google Cloud SQL PostgreSQL 14 instance with a private IP and a GCS bucket for backups."
    )
    asyncio.run(run_test(description))
