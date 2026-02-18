import asyncio
import json
import os
import sys
from pathlib import Path

# Add the project root to sys.path
sys.path.append(os.getcwd())

from app.services.llm_generator import LLMGenerator
from app.core import config

async def test_generation(run_id: str):
    run_dir = Path("runs") / run_id
    request_file = run_dir / "request.json"
    
    if not request_file.exists():
        print(f"Error: {request_file} not found")
        return

    with open(request_file, "r") as f:
        req_data = json.load(f)
    
    params = req_data["request"]
    provider = req_data.get("provider", "aws")
    
    print(f"--- Testing generation for Run: {run_id} ---")
    print(f"Provider: {provider}")
    print(f"Workload: {params.get('workload_description')[:100]}...")
    
    generator = LLMGenerator()
    
    # We want to see the bundle results
    try:
        bundle = generator.generate_terraform(params, provider)
        
        print("\n--- RESULTS ---")
        print(f"Main.tf length: {len(bundle.main_tf)} chars")
        print(f"Variables.tf length: {len(bundle.variables_tf)} chars")
        print(f"Outputs.tf length: {len(bundle.outputs_tf)} chars")
        
        if len(bundle.main_tf) == 0:
            print("\nFAILURE: main.tf is EMPTY!")
        else:
            print("\nSUCCESS: main.tf has content.")
            
    except Exception as e:
        print(f"\nEXCEPTION during generation: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_generation.py <run_id>")
        sys.exit(1)
    
    run_id = sys.argv[1]
    asyncio.run(test_generation(run_id))
