"""Configuration management for the application"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# === OpenAI ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4")
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))

# === Multi-cloud configuration ===
DEFAULT_PROVIDER = os.getenv("DEFAULT_PROVIDER", "aws")

# === MongoDB Configuration ===
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/terraform_agent")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "terraform_agent")

# === Google Gemini Configuration (Fallback) ===
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")

# === Langfuse Configuration ===
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
ENABLE_TRACING = bool(LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY)

# Validate required variables
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY is not set in environment variables")

if not GOOGLE_API_KEY:
    # Log warning instead of error since it's a fallback
    print("WARNING: GOOGLE_API_KEY not set. Fallback to Gemini will not work.")

valid_providers = ["aws", "gcp"]
if DEFAULT_PROVIDER not in valid_providers:
    raise ValueError(f"Invalid DEFAULT_PROVIDER: {DEFAULT_PROVIDER}. Must be one of {valid_providers}")

# === AWS ===
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_PROFILE = os.getenv("AWS_PROFILE")

# === GCP ===
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
GCP_REGION = os.getenv("GCP_REGION", "us-central1")
GCP_ZONE = os.getenv("GCP_ZONE", "us-central1-a")
GCP_CREDENTIALS_PATH = os.getenv("GCP_CREDENTIALS_PATH", "")

# === Server ===
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# === App Metadata ===
APP_NAME = "Multi-Cloud Terraform Agent"
APP_VERSION = "2.0.0"
APP_DESCRIPTION = "LLM-powered Terraform agent for AWS and GCP (Top 15 services)"

# === Directories ===
BASE_DIR = Path(__file__).parent.parent.parent
WORKSPACE_BASE_DIR = BASE_DIR / os.getenv("WORKSPACE_BASE_DIR", "runs")
LOGS_DIR = BASE_DIR / os.getenv("LOGS_DIR", "logs")

# === Terraform ===
TERRAFORM_TIMEOUT = int(os.getenv("TERRAFORM_TIMEOUT", "300"))

# === AWS MCP Configuration ===
AWS_MCP_SERVER = os.getenv("AWS_MCP_SERVER", "awslabs-core-mcp-server")
ENABLE_AWS_MCP = os.getenv("ENABLE_AWS_MCP", "False").lower() == "true"

# === Security ===
# Security validation is now handled in security_checker.py with provider-specific rules


