"""
API Client for Terraform Agent Backend

This module provides a Python client for interacting with the FastAPI backend.
"""
import requests
from typing import Dict, Any, Optional, List


class TerraformAPIClient:
    """Client for Terraform Agent FastAPI backend"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        """
        Initialize API client.
        
        Args:
            base_url: Base URL of the FastAPI backend
        """
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
    
    # ========================================================================
    # CONVERSATION ENDPOINTS
    # ========================================================================
    
    def create_conversation(self, provider: str = "aws") -> Dict[str, Any]:
        """
        Create a new conversation session.
        
        Args:
            provider: Cloud provider ("aws" or "gcp")
            
        Returns:
            Response with session_id and bot_response
        """
        response = self.session.post(
            f"{self.base_url}/conversations",
            params={"provider": provider}
        )
        response.raise_for_status()
        return response.json()
    
    def send_message(self, session_id: str, message: str) -> Dict[str, Any]:
        """
        Send a message in a conversation.
        
        Args:
            session_id: Active conversation session ID
            message: User's message
            
        Returns:
            Bot response with extracted parameters
        """
        response = self.session.post(
            f"{self.base_url}/conversations/{session_id}/message",
            json={"message": message}
        )
        response.raise_for_status()
        return response.json()
    
    def get_conversation(self, session_id: str) -> Dict[str, Any]:
        """
        Get conversation state.
        
        Args:
            session_id: Conversation session ID
            
        Returns:
            Full conversation state
        """
        response = self.session.get(
            f"{self.base_url}/conversations/{session_id}"
        )
        response.raise_for_status()
        return response.json()
    
    def generate_terraform(self, session_id: str) -> Dict[str, Any]:
        """
        Generate Terraform from completed conversation.
        
        Args:
            session_id: Completed conversation session ID
            
        Returns:
            Run response with run_id
        """
        response = self.session.post(
            f"{self.base_url}/conversations/{session_id}/generate"
        )
        response.raise_for_status()
        return response.json()
    
    # ========================================================================
    # RUN ENDPOINTS
    # ========================================================================
    
    def get_run(self, run_id: str) -> Dict[str, Any]:
        """
        Get run status.
        
        Args:
            run_id: Run identifier
            
        Returns:
            Run state
        """
        response = self.session.get(f"{self.base_url}/runs/{run_id}")
        response.raise_for_status()
        return response.json()
    
    def get_run_files(self, run_id: str) -> Dict[str, Any]:
        """
        Get generated Terraform files.
        
        Args:
            run_id: Run identifier
            
        Returns:
            Terraform files (main_tf, variables_tf, outputs_tf)
        """
        response = self.session.get(f"{self.base_url}/runs/{run_id}/files")
        response.raise_for_status()
        return response.json()
    
    def approve_run(self, run_id: str) -> Dict[str, Any]:
        """
        Approve and deploy run.
        
        Args:
            run_id: Run identifier
            
        Returns:
            Updated run state
        """
        response = self.session.post(f"{self.base_url}/runs/{run_id}/approve")
        response.raise_for_status()
        return response.json()
    
    def reject_run(self, run_id: str) -> Dict[str, Any]:
        """
        Reject/cancel run.
        
        Args:
            run_id: Run identifier
            
        Returns:
            Updated run state
        """
        response = self.session.post(f"{self.base_url}/runs/{run_id}/reject")
        response.raise_for_status()
        return response.json()
    
    def destroy_run(self, run_id: str) -> Dict[str, Any]:
        """
        Destroy infrastructure.
        
        Args:
            run_id: Run identifier
            
        Returns:
            Updated run state
        """
        response = self.session.post(f"{self.base_url}/runs/{run_id}/destroy")
        response.raise_for_status()
        return response.json()
    
    def edit_run_message(self, run_id: str, message: str) -> Dict[str, Any]:
        """
        Request changes to run via natural language.
        
        Args:
            run_id: Run identifier
            message: Requested changes
            
        Returns:
            Updated run state
        """
        response = self.session.post(
            f"{self.base_url}/runs/{run_id}/edit",
            json={"message": message}
        )
        response.raise_for_status()
        return response.json()
    
    def chat_about_run(self, run_id: str, message: str) -> Dict[str, Any]:
        """
        Ask questions about the Terraform plan.
        
        Args:
            run_id: Run identifier
            message: Question
            
        Returns:
            Bot response
        """
        response = self.session.post(
            f"{self.base_url}/runs/{run_id}/chat",
            json={"message": message}
        )
        response.raise_for_status()
        return response.json()
