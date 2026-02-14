# Project Overview: Multi-Cloud Terraform Agent

## 🎯 **What is this project?**
The **Multi-Cloud Terraform Agent** is an intelligent conversational interface for designing and deploying cloud infrastructure. It acts as a "Senior DevOps Engineer" that guides users—regardless of their expertise—through the process of creating secure, production-ready Terraform code for **AWS**, **GCP**, **Azure**, and **DigitalOcean**.

## 🧩 **Problem Statement**
Infrastructure-as-Code (IaC) is powerful but complex. Writing correct Terraform requires deep knowledge of:
*   Cloud provider APIs and resource types (e.g., `aws_instance` vs `google_compute_instance`).
*   Security best practices (IAM roles, security groups).
*   State management and workspace isolation.

This creates a high barrier to entry and risk of misconfiguration. The agent solves this by abstracting the complexity behind a friendly chat interface that validates inputs and enforces security standards automatically.

## ✅ **What Has Been Done**
Key components and features implemented so far:

1.  **Core Architecture**:
    *   **Backend**: FastAPI server managing conversation state and Terraform execution.
    *   **Frontend**: Streamlit UI for chat interaction and infrastructure visualization.
    *   **Database**: MongoDB integration for storing session data.

2.  **Conversation Engine (`ConversationManager`)**:
    *   Implements a 6-stage guided flow to collect requirements (Workload → Size → Storage → Network → IAM → Monitoring).
    *   Uses LLMs (OpenAI/Gemini) to parse intent and extract structured parameters.
    *   Handles "warm" conversation with context-aware suggestions.

3.  **Terraform Generation & Execution**:
    *   **`LLMGenerator`**: Converts collected parameters into valid Terraform HCL.
    *   **`WorkflowEngine`**: Manages the async lifecycle (`init`, `plan`, `apply`, `destroy`).
    *   **`WorkspaceManager`**: Ensures isolation by creating unique directories for each run.
    *   **`SecurityChecker`**: Validates code against strict rules (e.g., no `0.0.0.0/0` SSH access, no hardcoded secrets).

4.  **Recent Improvements**:
    *   Refined the scope to focus on Compute resources (EC2, GCE, VMs).
    *   Implemented 10 standard IAM role patterns.
    *   Fixed conversation loops and improved error handling of the conversation flow.

## ✅ **Completed Work: Session Management & Persistence**
We have successfully implemented robust session management:

*   **Reliable State Recovery**: Users can seamlessly resume conversations after a server restart. The `ConversationManager` now automatically reconnects to MongoDB and restores session state.
*   **Session History**: The "List Sessions" endpoint now returns correctly formatted history with date suffixes (e.g., "Web Server - Feb 12").
*   **Concurrency Handling**: Fixed boolean evaluation bugs that caused connection issues.
*   **Automated Cleanup**: Implemented TTL indexes on the `sessions` collection to automatically expire sessions after 30 days.
*   **Verification**: Added comprehensive tests (`tests/test_persistence_lifecycle.py`) covering the full session lifecycle (create, save, load, update).
