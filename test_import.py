import sys
import traceback

try:
    from app.models.schemas import AgentRequest, RunResponse
    print("SUCCESS: Schemas imported successfully!")
    print(f"AgentRequest fields: {AgentRequest.model_fields.keys()}")
    print(f"RunResponse fields: {RunResponse.model_fields.keys()}")
except Exception as e:
    print("ERROR importing schemas:")
    traceback.print_exc()
    sys.exit(1)
