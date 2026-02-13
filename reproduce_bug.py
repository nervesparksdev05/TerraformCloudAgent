import json
import ast
import sys

bad_json = """
{
    "workload_description": "This
    is a multiline string"
}
"""

print(f"Testing bad_json: {bad_json!r}", flush=True)

try:
    print("Attempting json.loads(bad_json)...", flush=True)
    json.loads(bad_json)
except Exception as e:
    print(f"json.loads failed: {e}", flush=True)

try:
    print("Attempting json.loads(bad_json, strict=False)...", flush=True)
    res = json.loads(bad_json, strict=False)
    print(f"json.loads(strict=False) success: {res}", flush=True)
except Exception as e:
    print(f"json.loads(strict=False) failed: {e}", flush=True)

try:
    print("Attempting ast.literal_eval(bad_json)...", flush=True)
    ast.literal_eval(bad_json)
except Exception as e:
    print(f"ast.literal_eval failed: {e}", flush=True)
