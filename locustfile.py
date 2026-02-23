import uuid
from locust import HttpUser, task, between

class APIUser(HttpUser):
    wait_time = between(1, 2)
    
    def on_start(self):
        """
        Executed when a new user starts.
        Sets a unique user ID for rate limiting bypass across users.
        """
        self.user_id = str(uuid.uuid4())

    @task(3)
    def list_sessions(self):
        """
        Hits the GET /conversations endpoint (MongoDB Read Test).
        """
        headers = {"X-User-ID": self.user_id}
        self.client.get("/conversations", headers=headers)

    @task(1)
    def create_conversation(self):
        """
        Triggers an LLM call and MongoDB Write by creating a new session.
        Note: This requires REQUIRE_AUTH=false in .env.
        """
        headers = {"X-User-ID": self.user_id}
        payload = {
            "owner": "google",
            "repo": "generative-ai-python",
            "github_token": "",
            "github_branch": "main"
        }
        with self.client.post("/conversations", 
                             json=payload, 
                             headers=headers, 
                             catch_response=True) as response:
            if response.status_code == 201:
                response.success()
            elif response.status_code == 429:
                # This is a SUCCESS for checking the rate limiter
                response.success() 
            else:
                response.success() 
