"""Configuration management for the application"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

# === GitHub Configuration ===
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# === Multi-cloud configuration ===
DEFAULT_PROVIDER = os.getenv("DEFAULT_PROVIDER", "aws")

# === MongoDB Configuration ===
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/terraform_agent")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "terraform_agent")

# === Google Gemini Configuration (Primary LLM Provider) ===
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# === Langfuse Configuration ===
# LANGFUSE_MODE controls where to send traces.
# Options:
#   "docker"  — local Langfuse running in Docker (default for development)
#               Uses LANGFUSE_HOST or LANGFUSE_BASE_URL (e.g. http://localhost:3000)
#               When calling from inside Docker use http://host.docker.internal:3000
#   "cloud"   — Langfuse Cloud (https://cloud.langfuse.com)
#               Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY from your cloud project
LANGFUSE_MODE = os.getenv("LANGFUSE_MODE", "docker").lower().strip()

LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")

# Resolve the host based on mode
if LANGFUSE_MODE == "cloud":
    LANGFUSE_HOST = "https://cloud.langfuse.com"
else:
    # Docker mode: prefer explicit LANGFUSE_HOST, fallback to LANGFUSE_BASE_URL, then localhost
    LANGFUSE_HOST = (
        os.getenv("LANGFUSE_HOST")
        or os.getenv("LANGFUSE_BASE_URL")
        or "http://localhost:3000"
    )

ENABLE_TRACING = bool(LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY)

# === Firebase Authentication ===
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID")
FIREBASE_SERVICE_ACCOUNT_PATH = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "./firebase-service-account.json")
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY")
FIREBASE_AUTH_DOMAIN = os.getenv("FIREBASE_AUTH_DOMAIN")
REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "true").lower() == "true"

# === SMTP Email Configuration ===
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Terraform Cloud Agent")
SEND_EMAIL_ALERTS = os.getenv("SEND_EMAIL_ALERTS", "true").lower() == "true"

# Approval token settings
APPROVAL_TOKEN_SECRET = os.getenv("APPROVAL_TOKEN_SECRET", "change-this-secret-key")
if APPROVAL_TOKEN_SECRET == "change-this-secret-key":
    import warnings
    warnings.warn(
        "APPROVAL_TOKEN_SECRET is using the default insecure value. "
        "Set a strong secret in your .env file before deploying to production.",
        stacklevel=2,
    )
APPROVAL_TOKEN_EXPIRY_HOURS = int(os.getenv("APPROVAL_TOKEN_EXPIRY_HOURS", "24"))
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

# Validate required variables
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is required. Please set it in your .env file.")

if REQUIRE_AUTH and not FIREBASE_PROJECT_ID:
    raise ValueError("FIREBASE_PROJECT_ID is required when REQUIRE_AUTH=true. Please set it in your .env file.")


valid_providers = ["aws", "gcp", "digitalocean"]
if DEFAULT_PROVIDER not in valid_providers:
    raise ValueError(f"Invalid DEFAULT_PROVIDER: {DEFAULT_PROVIDER}. Must be one of {valid_providers}")

# === AWS (Primary Cloud Provider — Free Tier) ===
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_SESSION_TOKEN = os.getenv("AWS_SESSION_TOKEN")  # optional, for assumed roles / SSO
AWS_PROFILE = os.getenv("AWS_PROFILE")


# === GCP (Multi-Cloud Support) ===
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
GCP_REGION = os.getenv("GCP_REGION", "us-central1")
GCP_ZONE = os.getenv("GCP_ZONE", "us-central1-a")
GCP_CREDENTIALS_PATH = os.getenv("GCP_CREDENTIALS_PATH", "")

# === Server ===
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# === App Metadata ===
APP_NAME = "TerraBot — Multi-Cloud Infrastructure Expert"
APP_VERSION = "2.2.0"
APP_DESCRIPTION = (
    "LLM-powered Terraform agent for AWS, GCP, and DigitalOcean"
)

# === Directories ===
BASE_DIR = Path(__file__).parent.parent.parent
WORKSPACE_BASE_DIR = BASE_DIR / os.getenv("WORKSPACE_BASE_DIR", "runs")
LOGS_DIR = BASE_DIR / os.getenv("LOGS_DIR", "logs")

# === Terraform ===
TERRAFORM_TIMEOUT = int(os.getenv("TERRAFORM_TIMEOUT", "300"))

# === AWS MCP Configuration ===
# AWS MCP disabled — all AWS account access is done directly via boto3 (lighter, faster, no subprocess).
AWS_MCP_SERVER = ""
ENABLE_AWS_MCP = False

# === Terraform MCP Configuration ===
# The terraform-mcp-server binary runs via mcp-proxy which exposes it as an SSE HTTP endpoint.
# In Docker (production): the 'mcp' service is reachable at http://mcp:8080/sse (Docker network)
# On the host (development): use http://localhost:8080/sse (port 8080 is published)
TERRAFORM_MCP_SERVER = os.getenv("TERRAFORM_MCP_SERVER", "terraform-mcp-server")
ENABLE_TERRAFORM_MCP = os.getenv("ENABLE_TERRAFORM_MCP", "False").lower() == "true"

# === Deployment Configuration ===
DEPLOYMENT_MODE = os.getenv("DEPLOYMENT_MODE", "development").lower()  # development or production

# MCP SSE endpoint — configurable so you don't need to change code when switching environments.
# Override with MCP_SSE_URL in .env if your setup differs.
_default_mcp_sse = (
    "http://mcp:8080/sse"       # Docker network service name
    if DEPLOYMENT_MODE != "development"
    else "http://localhost:8080/sse"  # host machine, port published by docker-compose
)
MCP_SSE_URL = os.getenv("MCP_SSE_URL", _default_mcp_sse)

# === Security ===
# Security validation is now handled in security_checker.py with provider-specific rules


