import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

from app.services.run_manager import RunManager
from app.services.workspace_manager import WorkspaceManager
from app.models.schemas import AgentRequest

def test_path_traversal():
    rm = RunManager()
    print("\n--- Testing Path Traversal ---")
    try:
        rm.get_run("some/../../dangerous_path")
        print("FAIL: Path traversal NOT blocked!")
    except ValueError as e:
        print(f"SUCCESS: Path traversal blocked: {e}")

def test_atomic_write():
    wm = WorkspaceManager()
    run_id, workspace_path = wm.create_run_workspace()
    print(f"\n--- Testing Atomic Write in {workspace_path.name} ---")
    
    from app.models.schemas import TerraformBundle
    bundle = TerraformBundle(
        main_tf="resource \"null_resource\" \"example\" {}",
        variables_tf="",
        outputs_tf=""
    )
    
    wm.write_terraform_files(workspace_path, bundle)
    
    # Check if files exist
    main_tf = workspace_path / "main.tf"
    if main_tf.exists():
        print("SUCCESS: main.tf written.")
        if (workspace_path / "main.tf.tmp").exists():
             print("FAIL: tmp file was not cleaned up.")
        else:
             print("SUCCESS: tmp file cleaned up.")
    else:
        print("FAIL: main.tf not found.")
        
    # Cleanup
    wm.cleanup_workspace(workspace_path)

if __name__ == "__main__":
    test_path_traversal()
    test_atomic_write()
