import requests
from typing import Dict, Any, Optional


class TerraformAPIClient:
    """Client for Terraform Agent FastAPI backend - README-Driven Mode"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        print("[CLIENT] HTTP session created")

    # ========================================================================
    # README-DRIVEN CONVERSATION ENDPOINTS
    # ========================================================================

    def create_conversation(self, github_url: str, provider: Optional[str] = None, github_token: str = "") -> Dict[str, Any]:
        """Create a new conversation session with GitHub URL and provider"""
        payload = {"github_url": github_url}
        if provider:
            payload["provider"] = provider
        if github_token:
            payload["github_token"] = github_token
        
        response = self.session.post(
            f"{self.base_url}/conversations",
            json=payload
        )
        response.raise_for_status()

        data = response.json()
        session_id = data.get("session_id")
        print(f"[CONVERSATION] Created session_id: {session_id}")
        return data

    def analyze_readme(self, session_id: str) -> Dict[str, Any]:
        """Analyze README for the session"""
        response = self.session.get(
            f"{self.base_url}/conversations/{session_id}/analyze",
            timeout=60  # 60 second timeout
        )
        response.raise_for_status()

        data = response.json()
        print(f"[CONVERSATION] README analyzed for session_id: {session_id}")
        return data

    def submit_form(self, session_id: str, form_data: Dict[str, Any]) -> Dict[str, Any]:
        """Submit form data to complete configuration"""
        response = self.session.post(
            f"{self.base_url}/conversations/{session_id}/form",
            json=form_data
        )
        response.raise_for_status()

        data = response.json()
        print(f"[CONVERSATION] Form submitted for session_id: {session_id}")
        return data

    def send_message(self, session_id: str, message: str) -> Dict[str, Any]:
        """Send a chat message and get bot response"""
        response = self.session.post(
            f"{self.base_url}/conversations/{session_id}/message",
            json={"message": message}
        )
        response.raise_for_status()

        data = response.json()
        print(f"[CONVERSATION] Message sent to session_id: {session_id}")
        return data

    def get_conversation(self, session_id: str) -> Dict[str, Any]:
        """Get conversation session details"""
        response = self.session.get(f"{self.base_url}/conversations/{session_id}")
        response.raise_for_status()

        data = response.json()
        print(f"[CONVERSATION] Fetched state for session_id: {session_id}")
        return data

    def generate_terraform(self, session_id: str) -> Dict[str, Any]:
        """Generate Terraform from completed conversation"""
        response = self.session.post(
            f"{self.base_url}/conversations/{session_id}/generate"
        )
        response.raise_for_status()

        data = response.json()
        run_id = data.get("run_id")
        print(f"[RUN] Created run_id: {run_id} (from session_id: {session_id})")
        return data

    def get_sessions(self, limit: int = 20):
        """List recent chat sessions"""
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
        """Delete a chat session"""
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
        """Get run status and details"""
        response = self.session.get(f"{self.base_url}/runs/{run_id}")
        response.raise_for_status()

        data = response.json()
        print(f"[RUN] Status fetched for run_id: {run_id}")
        return data

    def get_run_files(self, run_id: str) -> Dict[str, Any]:
        """Get generated Terraform files"""
        response = self.session.get(f"{self.base_url}/runs/{run_id}/files")
        response.raise_for_status()

        data = response.json()
        print(f"[RUN] Files fetched for run_id: {run_id}")
        return data

    def approve_run(self, run_id: str) -> Dict[str, Any]:
        """Approve and deploy Terraform"""
        response = self.session.post(f"{self.base_url}/runs/{run_id}/approve")
        response.raise_for_status()

        data = response.json()
        print(f"[RUN] Approved run_id: {run_id}")
        return data

    def reject_run(self, run_id: str) -> Dict[str, Any]:
        """Reject Terraform plan"""
        response = self.session.post(f"{self.base_url}/runs/{run_id}/reject")
        response.raise_for_status()

        data = response.json()
        print(f"[RUN] Rejected run_id: {run_id}")
        return data

    def destroy_run(self, run_id: str) -> Dict[str, Any]:
        """Destroy deployed infrastructure"""
        response = self.session.post(f"{self.base_url}/runs/{run_id}/destroy")
        response.raise_for_status()

        data = response.json()
        print(f"[RUN] Destroy requested for run_id: {run_id}")
        return data

    def edit_run_message(self, run_id: str, message: str) -> Dict[str, Any]:
        """Request changes to Terraform plan"""
        response = self.session.post(
            f"{self.base_url}/runs/{run_id}/edit",
            json={"message": message}
        )
        response.raise_for_status()

        data = response.json()
        print(f"[RUN] Edit requested for run_id: {run_id}")
        return data

    def chat_about_run(self, run_id: str, message: str) -> Dict[str, Any]:
        """Ask questions about the run"""
        response = self.session.post(
            f"{self.base_url}/runs/{run_id}/chat",
            json={"message": message}
        )
        response.raise_for_status()

        data = response.json()
        print(f"[RUN] Chat message sent for run_id: {run_id}")
        return data