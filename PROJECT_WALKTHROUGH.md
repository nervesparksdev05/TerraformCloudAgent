# Terraform Cloud Agent - Project Walkthrough

This document provides a complete, end-to-end explanation of the project's codebase and flow. It is designed to help you understand how the system works from the moment a user interacts with the UI to the actual infrastructure deployment.

## 🏗️ High-Level Architecture

The project follows a **Client-Server** architecture with an intelligent **Agentic Core**:

1.  **Frontend (React/Vite)**: Handles user interaction, input collection, and displays real-time status.
2.  **Backend (FastAPI)**: Orchestrates the entire workflow, manages state, and exposes a REST API.
3.  **Agent Core (LLM + Security)**: The "brain" that translates natural language into secure Terraform code.
4.  **Infrastructure Runner (Terraform CLI)**: The "hands" that actually execute the code against AWS or GCP.

---

## 📂 Key File Structure

### Backend (`app/`)
*   **`main.py`**: The entry point. It contains the FastAPI app definition and the core logic for handling API requests. This is where the "Run Manager" logic lives.
*   **`services/llm_generator.py`**: The AI integration. Handles communication with OpenAI (primary) and Gemini (fallback).
*   **`services/security_checker.py`**: The guardian. Scans generated code for prohibited patterns (e.g., `local-exec`) before execution.
*   **`services/terraform_runner.py`**: The executor. Wraps the Terraform CLI to run `init`, `plan`, and `apply` commands safely.
*   **`core/database.py`**: Managing data persistence with MongoDB.

### Frontend (`frontend/src/`)
*   **`App.tsx`**: The main router. It defines which page loads for which URL (e.g., `/create`, `/runs/:id`).
*   **`pages/create-run.tsx`**: The form where users input their natural language request.
*   **`pages/run-details.tsx`**: The dashboard for a specific run, showing logs, plan output, and approval buttons.
*   **`lib/queryClient.ts`**: The API client wrapper making `fetch` calls to the backend.

---

## 🔄 End-to-End Flow: "Creating a VM"

Let's trace a request to "Create an EC2 instance" through the system.

### 1. User Input (Frontend)
*   **File**: `frontend/client/src/pages/create-run.tsx`
*   **Action**: User types "Create a t3.micro EC2 instance" and clicks "Create Run".
*   **Code**: The `createMutation` function collects the input and calls `apiRequest("POST", "/api/runs", payload)`.

### 2. API Handling (Backend Entry)
*   **File**: `app/main.py`
*   **Function**: `create_run(request: AgentRequest)`
*   **Action**:
    1.  Receives the request.
    2.  Calls `workspace_manager.create_run_workspace()` to create a unique folder in `runs/`.
    3.  Sets initial status to `planning`.

### 3. AI Code Generation (The Brain)
*   **File**: `app/services/llm_generator.py`
*   **Function**: `generate_terraform(...)`
*   **Action**:
    1.  Constructs a prompt with the user's request + system prompt (AWS/GCP context).
    2.  Calls OpenAI (or falls back to Gemini).
    3.  Returns a `TerraformBundle` containing `main.tf`, `variables.tf`, and `outputs.tf`.

### 4. Security Validation (The Guard)
*   **File**: `app/services/security_checker.py`
*   **Function**: `check_terraform(...)`
*   **Action**:
    1.  Scans the generated HCL code.
    2.  Checks for prohibited resources (e.g., `provisioner "local-exec"`).
    3.  If valid, proceeds. If invalid, the run fails immediately.

### 5. Terraform Planning (The Simulation)
*   **File**: `app/services/terraform_runner.py`
*   **Function**: `run_pipeline("plan")`
*   **Action**:
    1.  Runs `terraform init` in the workspace folder.
    2.  Runs `terraform plan` to see what *would* happen.
    3.  Captures the output (e.g., "Plan: 1 to add, 0 to change").
    4.  Updates the run status to `planned`.

### 6. User Review (Frontend)
*   **File**: `frontend/client/src/pages/run-details.tsx`
*   **Action**: The UI polls the run status. When it sees `planned`, it displays the Terraform Plan output.
*   **Decision**: The user reviews the plan and clicks **"Approve"**.

### 7. Execution (The Action)
*   **File**: `app/main.py` -> `app/services/terraform_runner.py`
*   **Function**: `approve_run(...)` -> `_run_apply_pipeline(...)`
*   **Action**:
    1.  Status updates to `applying`.
    2.  `terraform apply -auto-approve` is executed.
    3.  Real infrastructure is provisioned on AWS/GCP.
    4.  Status updates to `completed`.

---

## ❓ Common Questions & Answers

**Q: Where is the state stored?**
A: State is dual-persisted. Primary is **MongoDB** (via `app/core/database.py`), but every run also has a local `state.json` file in its workspace folder (`runs/<run_id>/state.json`) as a fallback.

**Q: How does it handle errors?**
A: If the LLM generates bad code, `TerraformRunner` captures the `terraform validate` or `plan` error. This error is saved to the run state and displayed in the UI.

**Q: Can I manually edit the code?**
A: Yes. The files are standard `.tf` files in `runs/<run_id>/`. You can technically edit them on disk, though the UI flow currently focuses on Chat-based refinement.

**Q: What happens if OpenAI is down?**
A: The `_generate_bundle_with_fallback` function in `main.py` catches the error and automatically retries using Google's Gemini model.

**Q: How is the frontend talking to the backend?**
A: The frontend uses `vite` as a dev server which proxies requests to `http://localhost:8000` (configured in `vite.config.ts`). In production, Nginx would handle this routing.
