import requests
from typing import Dict, Any


class TerraformAPIClient:
    """Client for Terraform Agent FastAPI backend"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        print("[CLIENT] HTTP session created")

    # ========================================================================
    # CONVERSATION ENDPOINTS
    # ========================================================================

    def create_conversation(self, provider: str = "aws", github_url: str = "", github_token: str = "") -> Dict[str, Any]:
        params = {"provider": provider}
        if github_url:
            params["github_url"] = github_url
        if github_token:
            params["github_token"] = github_token
            
        response = self.session.post(
            f"{self.base_url}/conversations",
            params=params
        )
        response.raise_for_status()

        data = response.json()

        session_id = data.get("session_id")
        print(f"[CONVERSATION] Created session_id: {session_id}")
        

        return data

    def send_message(self, session_id: str, message: str) -> Dict[str, Any]:
        response = self.session.post(
            f"{self.base_url}/conversations/{session_id}/message",
            json={"message": message}
        )
        response.raise_for_status()

        data = response.json()
        print(f"[CONVERSATION] Message sent to session_id: {session_id}")
        return data

    def get_conversation(self, session_id: str) -> Dict[str, Any]:
        response = self.session.get(f"{self.base_url}/conversations/{session_id}")
        response.raise_for_status()

        data = response.json()
        print(f"[CONVERSATION] Fetched state for session_id: {session_id}")
        return data

    def generate_terraform(self, session_id: str) -> Dict[str, Any]:
        response = self.session.post(
            f"{self.base_url}/conversations/{session_id}/generate"
        )
        response.raise_for_status()

        data = response.json()

        run_id = data.get("run_id")
        print(f"[RUN] Created run_id: {run_id} (from session_id: {session_id})")
        return data

    def get_sessions(self, limit: int = 20):
        """List recent chat sessions."""
        try:
            response = self.session.get(
                f"{self.base_url}/sessions",
                params={"limit": limit}
            )
            if response.status_code == 200:
                return response.json()
            return []
        except Exception as e:
            print(f"[CLIENT] Failed to fetch sessions: {e}")
            return []

    def delete_session(self, session_id: str) -> bool:
        """Delete a chat session."""
        try:
            response = self.session.delete(f"{self.base_url}/sessions/{session_id}")
            response.raise_for_status()
            print(f"[CLIENT] Deleted session: {session_id}")
            return True
        except Exception as e:
            print(f"[CLIENT] Failed to delete session: {e}")
            return False

    # ========================================================================
    # RUN ENDPOINTS
    # ========================================================================

    def get_run(self, run_id: str) -> Dict[str, Any]:
        response = self.session.get(f"{self.base_url}/runs/{run_id}")
        response.raise_for_status()

        data = response.json()
        print(f"[RUN] Status fetched for run_id: {run_id}")
        return data

    def get_run_files(self, run_id: str) -> Dict[str, Any]:
        response = self.session.get(f"{self.base_url}/runs/{run_id}/files")
        response.raise_for_status()

        data = response.json()
        print(f"[RUN] Files fetched for run_id: {run_id}")
        return data

    def approve_run(self, run_id: str) -> Dict[str, Any]:
        response = self.session.post(f"{self.base_url}/runs/{run_id}/approve")
        response.raise_for_status()

        data = response.json()
        print(f"[RUN] Approved run_id: {run_id}")
        return data

    def reject_run(self, run_id: str) -> Dict[str, Any]:
        response = self.session.post(f"{self.base_url}/runs/{run_id}/reject")
        response.raise_for_status()

        data = response.json()
        print(f"[RUN] Rejected run_id: {run_id}")
        return data

    def destroy_run(self, run_id: str) -> Dict[str, Any]:
        response = self.session.post(f"{self.base_url}/runs/{run_id}/destroy")
        response.raise_for_status()

        data = response.json()
        print(f"[RUN] Destroy requested for run_id: {run_id}")
        return data

    def edit_run_message(self, run_id: str, message: str) -> Dict[str, Any]:
        response = self.session.post(
            f"{self.base_url}/runs/{run_id}/edit",
            json={"message": message}
        )
        response.raise_for_status()

        data = response.json()
        print(f"[RUN] Edit requested for run_id: {run_id}")
        return data

    def chat_about_run(self, run_id: str, message: str) -> Dict[str, Any]:
        response = self.session.post(
            f"{self.base_url}/runs/{run_id}/chat",
            json={"message": message}
        )
        response.raise_for_status()

        data = response.json()
        print(f"[RUN] Chat message sent for run_id: {run_id}")
        return data
