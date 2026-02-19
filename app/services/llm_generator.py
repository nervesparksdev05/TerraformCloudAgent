"""LLM Terraform Generator — Uses rich conversation params for production infrastructure code."""
from __future__ import annotations

import json
from typing import Any, Dict

import subprocess
import tempfile
import os
from pathlib import Path

from app.services.llm_service import LLMService
from app.core.logger import get_logger
from app.models.schemas import TerraformBundle

logger = get_logger(__name__)


class LLMGenerator:
    """
    Generate production-grade Terraform code from structured conversation parameters.

    Supports: AWS EC2, GCP Compute Engine, Azure Virtual Machines, DigitalOcean Droplets.
    """

    # -----------------------------
    # Shared output contract
    # -----------------------------
    BASE_SYSTEM_PROMPT = """\
You are a **Principal Cloud Architect** and **Terraform Expert**.
Your goal is to generate **World-Class, Production-Grade** Terraform code.

### 🎯 STANDARDS OF EXCELLENCE:
1.  **Strict Variable Usage**: NEVER hardcode values (CIDRs, instance types, regions, AMIs). define them in `variables.tf`.
2.  **Professional Naming**: Use clean, consistent naming conventions.
3.  **Security First**: No open security groups for SSH (never 0.0.0.0/0). Enforce encryption where applicable.
4.  **Complete Solutions**: Generate FULL working infrastructure, not skeleton code.
5.  **Smart Defaults**: Use cost-effective defaults if values are missing.

### 🛠️ SPECIFIC REQUIREMENTS:
-   **Structure**:
    -   `main.tf`: Core infrastructure (VPC, Instances, SGs).
    -   `variables.tf`: Clear definitions with descriptions and defaults.
    -   `outputs.tf`: Useful outputs (IPs, connection strings).
-   **User Data**: Include user_data/startup scripts INLINE using heredoc. The script must clone the GitHub repo, install dependencies, and start the app.
-   **Minimal Comments**: Include concise, essential comments explaining technical choices. DO NOT include long instructional text or deployment guides.
"""

    README_BRIDGE_PROMPT = """\
### 🚨 MANDATORY CONSTRAINTS:
- Use the README as your primary source of truth for workloads, languages, and ports.
- Ensure the output is a COMPLETE, WORKING deployment.
- NO instructional comments. Keep comments technical and brief.
- RETURN ONLY A JSON OBJECT with keys: "main_tf", "variables_tf", "outputs_tf".
"""

    # -----------------------------
    # Provider-specific templates
    # -----------------------------
    AWS_TEMPLATE = """\
PROVIDER TARGET: AWS

REQUIRED IN main.tf (IN THIS ORDER):
1) terraform + required_providers (aws,tls)
2) provider "aws" using var.aws_region and default_tags block:
   default_tags {
     tags = {
       Environment = var.environment
       Project     = var.project_name
       ManagedBy   = "Terraform"
       CostCenter  = var.project_name
     }
   }
3) data sources:
   - data "aws_ami" "selected" (NO hardcoded AMI IDs)
   - data "aws_availability_zones" "available"
   - data "aws_iam_policy_document" "instance_assume_role"
   - data "aws_iam_policy_document" "instance_policy" (CloudWatch + SSM always, plus user's iam_services)
4) tls_private_key + aws_key_pair
5) VPC + public subnets + IGW + route table + associations (use var.vpc_cidr, var.subnet_count)
   - Enable VPC flow logs (optional, comment out by default)
6) security group:
   - ingress for app ports from ports param (HTTP/HTTPS default if none)
   - ingress SSH only from var.ssh_allowed_cidrs (never 0.0.0.0/0)
   - Add descriptive names to each rule
7) IAM role + inline policy + instance profile
8) aws_instance "main" with:
   - root_block_device (encrypted=true, size/type vars)
   - metadata_options (IMDSv2 required)
   - monitoring = true (enable detailed monitoring)
   - tags with Name, Environment, Project
9) CloudWatch alarms (PRODUCTION ONLY):
   - CPU utilization > 80%
   - Status check failed
   - (Optional) Memory and disk alarms via CloudWatch agent
10) Optional load balancer if var.load_balancer_type != "none"
11) Backend configuration (as comments):
    # terraform {
    #   backend "s3" {
    #     bucket         = "terraform-state-ACCOUNT_ID"
    #     key            = "PROJECT_NAME/terraform.tfstate"
    #     region         = "us-east-1"
    #     encrypt        = true
    #     dynamodb_table = "terraform-state-lock"
    #   }
    # }

VARIABLES.TF MUST INCLUDE:
- aws_region, environment, project_name
- instance_type, instance_count
- storage_size_gb, storage_type
- vpc_cidr, subnet_count
- ssh_allowed_cidrs (list(string))
- ports (list(object({port=number, protocol=string, source_cidr=string, description=string})))
- load_balancer_type (string)
- enable_monitoring (bool, default=true for prod)

OUTPUTS.TF MUST INCLUDE:
- instance_ids, public_ips, private_ips
- ssh_private_key (sensitive)
- vpc_id, security_group_id, iam_role_arn
- connection_string (how to SSH to instances)
"""

    GCP_TEMPLATE = """\
PROVIDER TARGET: GCP

REQUIRED IN main.tf (IN THIS ORDER):
1) terraform + required_providers (google,tls)
2) provider "google" with var.gcp_project_id and var.gcp_region
3) data sources:
   - data "google_compute_zones" "available" for var.gcp_region
4) tls_private_key (for SSH key material)
5) VPC networking:
   - google_compute_network (custom mode)
   - google_compute_subnetwork (use var.vpc_cidr as ip_cidr_range, region=var.gcp_region)
   - firewall rules:
     - allow app ports from ports param (default 80/443)
     - allow SSH ONLY from var.ssh_allowed_cidrs (never 0.0.0.0/0)
6) compute instances:
   - google_compute_instance "main" (count=var.instance_count)
   - machine_type = var.instance_type (e2-micro default if missing)
   - boot_disk initialize_params { image = var.os_image ; size = var.storage_size_gb ; type = var.storage_type }
     (storage_type should map to pd-balanced/pd-ssd; default pd-balanced)
   - network_interface using subnetwork + access_config if var.enable_public_ip == true
   - metadata includes ssh-keys entry built from var.ssh_username + tls public key

VARIABLES.TF MUST INCLUDE:
- gcp_project_id, gcp_region
- environment, project_name
- instance_type, instance_count
- os_image (e.g. "projects/ubuntu-os-cloud/global/images/family/ubuntu-2204-lts")
- storage_size_gb, storage_type (pd-balanced|pd-ssd)
- vpc_cidr
- enable_public_ip (bool)
- ssh_username (string)
- ssh_allowed_cidrs (list(string))
- ports (list(object({port=number, protocol=string, source_cidr=string, description=string})))

OUTPUTS.TF MUST INCLUDE:
- instance_ids (self_link or id), public_ips, private_ips
- ssh_private_key (sensitive)
- network_name, subnetwork_name, firewall_names
"""

    AZURE_TEMPLATE = """\
PROVIDER TARGET: AZURE

REQUIRED IN main.tf (IN THIS ORDER):
1) terraform + required_providers (azurerm,tls)
2) provider "azurerm" { features {} }
3) tls_private_key
4) resource group + vnet + subnet:
   - azurerm_resource_group
   - azurerm_virtual_network (address_space from var.vpc_cidr)
   - azurerm_subnet
5) network security group rules:
   - allow app ports from ports param (default 80/443) from their source_cidr
   - allow SSH ONLY from var.ssh_allowed_cidrs (never 0.0.0.0/0)
6) public IP + NIC:
   - create azurerm_public_ip if var.enable_public_ip == true
   - azurerm_network_interface with ip_configuration
7) azurerm_linux_virtual_machine "main" (count)
   - size = var.instance_type (B1s default)
   - admin_username = var.ssh_username
   - admin_ssh_key uses tls public key
   - os_disk encrypted settings where supported
   - source_image_reference OR source_image_id derived from var.os_image

VARIABLES.TF MUST INCLUDE:
- azure_location, environment, project_name
- instance_type, instance_count
- os_image (either "UbuntuLTS" style alias you map to source_image_reference OR explicit image reference object)
- storage_size_gb, storage_type (StandardSSD_LRS default)
- vpc_cidr
- enable_public_ip (bool)
- ssh_username
- ssh_allowed_cidrs (list(string))
- ports list(object)

OUTPUTS.TF MUST INCLUDE:
- vm_ids, public_ips, private_ips
- ssh_private_key (sensitive)
- resource_group_name, vnet_id, subnet_id, nsg_id
"""

    DO_TEMPLATE = """\
PROVIDER TARGET: DIGITALOCEAN

REQUIRED IN main.tf (IN THIS ORDER):
1) terraform + required_providers (digitalocean,tls)
2) provider "digitalocean" (NO hardcoded token; token must come from environment)
3) tls_private_key + digitalocean_ssh_key
4) digitalocean_firewall:
   - inbound rules for app ports from ports param (default 80/443)
   - inbound SSH only from var.ssh_allowed_cidrs (never 0.0.0.0/0)
5) digitalocean_droplet "main" (count)
   - region = var.do_region
   - size = var.instance_type (basic-1vcpu-1gb default)
   - image = var.os_image (e.g. "ubuntu-22-04-x64")
   - ssh_keys includes digitalocean_ssh_key id

VARIABLES.TF MUST INCLUDE:
- do_region, environment, project_name
- instance_type, instance_count
- os_image
- ssh_allowed_cidrs (list(string))
- ports list(object)

OUTPUTS.TF MUST INCLUDE:
- droplet_ids, public_ips, private_ips
- ssh_private_key (sensitive)
- firewall_id
"""

    CI_CD_TEMPLATE = """
Generate a valid `.github/workflows/deploy.yml` for {provider}.
Triggers: PR/Push to main.
Steps: Checkout, Setup Terraform, Init, Validate, Plan (PR), Apply (Push, auto-approve).
Use secrets: AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY or GCP_SA_KEY or AZURE_CREDENTIALS or DO_TOKEN.
Output ONLY raw YAML. No markdown.
"""

    def __init__(self) -> None:
        self.llm_service = LLMService()
        logger.info("LLMGenerator initialized with LLMService")

    # -----------------------------
    # Public API
    # -----------------------------
    def generate_terraform(
        self, 
        params: Dict[str, Any], 
        provider: str = "aws",
        session_id: str = None  # Added session_id
    ) -> TerraformBundle:
        prompt = self._build_prompt(params, provider)
        system_prompt = self._build_system_prompt(params, provider)
        
        # Pass session_id to _call
        bundle = self._call(prompt, system_prompt, session_id=session_id)
        
        # Generate CI/CD workflow (pass session_id)
        workflow_yaml = self._generate_workflow(params, provider, session_id=session_id)
        bundle.github_workflow_yaml = workflow_yaml
        
        return self._post_process_code(bundle)

    def _generate_workflow(self, params: Dict[str, Any], provider: str, session_id: str = None) -> str:
        prompt = self.CI_CD_TEMPLATE.format(provider=provider.upper())
        try:
            # Create Langfuse trace with prompt as input
            from app.services import langfuse_service
            trace = langfuse_service.create_trace(
                name="cicd-gen",
                session_id=session_id,
                metadata={"provider": provider},
                input=prompt,
            )

            raw = self.llm_service.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=4000,
                timeout=20,
                _trace=trace,
            )
            # Cleanup potential markdown fences
            clean = raw.replace("```yaml", "").replace("```", "").strip()
            
            if trace:
                trace.update(output=clean)
                langfuse_service.flush()
                
            return clean
        except Exception as e:
            logger.error("Failed to generate CI/CD workflow: %s", e)
            return "# Error generating workflow file."

    def _post_process_code(self, bundle: TerraformBundle) -> TerraformBundle:
        """
        Run terraform fmt, validate, and security checks on the generated code.
        If tools are missing or validation fails, return original bundle with logs.
        """
        # Check if terraform is installed
        try:
            subprocess.run(["terraform", "--version"], check=True, capture_output=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            logger.warning("Terraform CLI not found. Skipping fmt/validate.")
            return bundle

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            
            # Write files
            (tmp_path / "main.tf").write_text(bundle.main_tf, encoding="utf-8")
            (tmp_path / "variables.tf").write_text(bundle.variables_tf, encoding="utf-8")
            (tmp_path / "outputs.tf").write_text(bundle.outputs_tf, encoding="utf-8")

            # 1. Run terraform fmt
            try:
                subprocess.run(
                    ["terraform", "fmt"], 
                    cwd=tmpdir, 
                    check=True, 
                    capture_output=True
                )
                # Read back formatted code
                bundle.main_tf = (tmp_path / "main.tf").read_text(encoding="utf-8")
                bundle.variables_tf = (tmp_path / "variables.tf").read_text(encoding="utf-8")
                bundle.outputs_tf = (tmp_path / "outputs.tf").read_text(encoding="utf-8")
                logger.info("Terraform code formatted successfully.")
            except subprocess.CalledProcessError as e:
                logger.warning("terraform fmt failed: %s", e.stderr.decode())

            # 2. Run terraform init (backend=false) + validate
            try:
                subprocess.run(
                    ["terraform", "init", "-backend=false"], 
                    cwd=tmpdir, 
                    check=True, 
                    capture_output=True
                )
                subprocess.run(
                    ["terraform", "validate"], 
                    cwd=tmpdir, 
                    check=True, 
                    capture_output=True
                )
                logger.info("Terraform code validated successfully.")
            except subprocess.CalledProcessError as e:
                # Decode with error handling to prevent UnicodeEncodeError from terraform's Unicode box chars
                error_msg = e.stderr.decode('utf-8', errors='replace') if e.stderr else "Unknown error"
                logger.error("terraform validate failed: %s", error_msg)
                # We still return the bundle, but logs will show the error.
                # In a future iteration, we could retry generation.

        return bundle

    def refine_terraform(
        self,
        base_request: str,
        current_code: Dict[str, Any],
        feedback: str,
        provider: str = "aws",
        session_id: str = None,  # Added session_id
    ) -> TerraformBundle:
        prompt = (
            f"Original request: {base_request}\n"
            f"User feedback: {feedback}\n"
            f"Current code:\n{json.dumps(current_code, indent=2)}\n\n"
            "Apply the feedback and return updated JSON with main_tf, variables_tf, outputs_tf."
        )
        system_prompt = self._build_system_prompt({}, provider)
        return self._call(prompt, system_prompt, session_id=session_id)

    # -----------------------------
    # Internals
    # -----------------------------
    def _build_system_prompt(self, params: Dict[str, Any], provider: str) -> str:
        provider_norm = (params.get("cloud_provider") or provider or "aws").lower()

        provider_block = {
            "aws": self.AWS_TEMPLATE,
            "gcp": self.GCP_TEMPLATE,
            "azure": self.AZURE_TEMPLATE,
            "digitalocean": self.DO_TEMPLATE,
        }.get(provider_norm, self.AWS_TEMPLATE)

        # Add service-specific templates based on detected services
        service_templates_block = self._build_service_templates_block(params, provider_norm)

        return (
            self.BASE_SYSTEM_PROMPT + "\n\n" + 
            provider_block + "\n\n" + 
            service_templates_block + "\n\n" + 
            self.README_BRIDGE_PROMPT
        )

    def _build_service_templates_block(self, params: Dict[str, Any], provider: str) -> str:
        """Build service-specific template guidance based on detected services."""
        from app.services.service_templates import get_all_service_templates
        
        detected_services = params.get("detected_services", {})
        provider_services = detected_services.get(provider, [])
        
        if not provider_services:
            return ""
        
        # Get combined templates for all detected services
        templates = get_all_service_templates(provider, provider_services)
        
        if not templates:
            return ""
        
        return (
            "### 🎯 DETECTED SERVICES - ADDITIONAL REQUIREMENTS ###\n\n"
            f"Based on README analysis, the following services were detected: {', '.join(provider_services)}\n\n"
            "You MUST include Terraform resources for these services in addition to compute instances:\n\n"
            f"{templates}\n\n"
            "CRITICAL: Integrate these services with the main compute infrastructure. "
            "For example, if RDS is detected, configure security groups to allow EC2 -> RDS traffic. "
            "If S3 is detected, add IAM permissions for EC2 to access S3.\n"
        )

    def _provider_defaults(self, provider_norm: str) -> Dict[str, Any]:
        provider_norm = (provider_norm or "aws").lower()
        from app.core.constants import PROVIDER_DEFAULTS
        return PROVIDER_DEFAULTS.get(provider_norm, PROVIDER_DEFAULTS["default"])

    def _build_prompt(self, params: Dict[str, Any], provider: str) -> str:
        p = params
        provider_norm = (p.get("cloud_provider") or provider or "aws").lower()

        provider_display = {
            "aws": "AWS EC2",
            "gcp": "GCP Compute Engine",
            "azure": "Azure Virtual Machines",
            "digitalocean": "DigitalOcean Droplets",
        }.get(provider_norm, "AWS EC2")

        d = self._provider_defaults(provider_norm)

        # Region resolution:
        # - accept old "region" if present
        # - accept provider-native key (aws_region/gcp_region/azure_location/do_region)
        # - fallback to default
        region_value = (
            p.get(d["region_key"])
            or p.get("region")
            or d["default_region"]
        )

        instance_type = p.get("instance_type") or d["default_instance"]
        instance_count = int(p.get("instance_count", 1) or 1)

        # OS image default differs per provider
        os_image = p.get("os_image") or p.get("ami_os") or d["default_os_image"]

        # Storage type differs per provider; DO often ignores disk type in droplet
        storage_size_gb = p.get("storage_size_gb", p.get("storage_size", 20)) or 20
        storage_type = p.get("storage_type") or d["default_storage_type"]

        # ports formatted
        ports_desc = ""
        for port_entry in p.get("ports", []):
            if isinstance(port_entry, dict):
                ports_desc += (
                    f"  - Port {port_entry.get('port')}/{port_entry.get('protocol', 'tcp')} "
                    f"from {port_entry.get('source_cidr', '0.0.0.0/0')} "
                    f"({port_entry.get('description', '')})\n"
                )

        default_ports = (
            "  - Port 80/tcp from 0.0.0.0/0 (HTTP)\n"
            "  - Port 443/tcp from 0.0.0.0/0 (HTTPS)\n"
        )
        ports_section = ports_desc if ports_desc else default_ports

        dependencies = p.get("dependencies", [])
        if isinstance(dependencies, list):
            readme_dependencies = ", ".join(str(dep) for dep in dependencies if dep) or "Not explicitly listed"
        else:
            readme_dependencies = str(dependencies or "Not explicitly listed")

        implied_resources = p.get("implied_resources", [])
        if isinstance(implied_resources, list):
            implied_str = ", ".join(implied_resources)
        else:
            implied_str = str(implied_resources)

        readme_language = str(p.get("language", "Not specified"))

        # security: ensure we pass ssh cidrs in prompt
        ssh_cidrs = ", ".join(p.get("ssh_allowed_cidrs", [])) or "MISSING (must be collected; never 0.0.0.0/0)"

        # provider-specific required vars (must exist as vars if missing)
        gcp_project_id = p.get("gcp_project_id", "")
        azure_location = p.get("azure_location", "")
        do_region = p.get("do_region", "")
        gcp_region = p.get("gcp_region", "")
        aws_region = p.get("aws_region", "")
        ssh_username = p.get("ssh_username", "")

        provider_missing_notes = []
        if provider_norm == "gcp" and not gcp_project_id:
            provider_missing_notes.append("MISSING: gcp_project_id (must be a variable)")
        if provider_norm == "gcp" and not (gcp_region or p.get("region")):
            provider_missing_notes.append("MISSING: gcp_region (must be a variable)")
        if provider_norm == "azure" and not (azure_location or p.get("region")):
            provider_missing_notes.append("MISSING: azure_location (must be a variable)")
        if provider_norm == "digitalocean" and not (do_region or p.get("region")):
            provider_missing_notes.append("MISSING: do_region (must be a variable)")
        if provider_norm in ("gcp", "azure") and not ssh_username:
            provider_missing_notes.append("MISSING: ssh_username (must be a variable)")

        missing_block = ""
        if provider_missing_notes:
            missing_block = "PROVIDER MISSING NOTES:\n  - " + "\n  - ".join(provider_missing_notes) + "\n"

        # README context for intelligent deployment
        readme_context = p.get("readme_context", "")
        github_owner = p.get("github_owner", "")
        github_repo = p.get("github_repo", "")
        project_name = p.get("project_name") or github_repo or "app"
        has_docker = p.get("has_docker", False)
        database_type = p.get("database_type", "none")

        prompt = f"""### 🧩 INPUT CONTEXT:
Generate the BEST POSSIBLE production-grade Terraform configuration for {provider_display}.
This Terraform should FULLY deploy the project from GitHub repo: {github_owner}/{github_repo}

WORKLOAD: {p.get('workload_description', p.get('service_type', 'web server'))}
PROJECT NAME: {project_name}
ENVIRONMENT: {p.get('environment', 'dev')}

README CONTEXT (USE THIS TO MAKE INTELLIGENT DECISIONS):
{p.get('readme_context', p.get('project_context', ''))[:3000]}

README SIGNALS:
  Primary language/framework: {readme_language}
  Declared dependencies/services: {readme_dependencies}
  Implied Resources (Auto-Detected): {implied_str}
  Database: {database_type}
  Docker detected: {has_docker}
  GitHub Repo: {github_owner}/{github_repo}

CORE PARAMS:
  {d["region_key"]}: {region_value}
  Instance type: {instance_type}
  Instance count: {instance_count}
  OS image: {os_image}
  Storage: {int(storage_size_gb)}GB {storage_type or "(provider default)"}
  VPC CIDR: {p.get('vpc_cidr', '10.0.0.0/16')}
  Subnet count: {p.get('subnet_count', 2)}
  Public IP: {p.get('enable_public_ip', True)}

SECURITY GROUP / FIREWALL PORTS:
{ports_section}  SSH allowed CIDRs: {ssh_cidrs}

{missing_block}PROVIDER-SPECIFIC REQUIRED VARS (fill from params or create variables):
  AWS: aws_region={aws_region or "<var.aws_region>"}
  GCP: gcp_project_id={gcp_project_id or "<var.gcp_project_id>"} ; gcp_region={gcp_region or "<var.gcp_region>"}
  Azure: azure_location={azure_location or "<var.azure_location>"}
  DigitalOcean: do_region={do_region or "<var.do_region>"}
  SSH username (GCP/Azure): ssh_username={ssh_username or "<var.ssh_username>"}

CRITICAL REQUIREMENTS:
- Follow the provider template rules from system prompt exactly.
- Define every variable referenced.
- Define every output referenced.
- Never allow SSH from 0.0.0.0/0.
- Include a user_data/startup script that clones https://github.com/{github_owner}/{github_repo}, installs dependencies, and starts the app.
- If Docker is detected, use Docker-based deployment in user_data.
- If a database is needed ({database_type}), provision appropriate storage or managed service.
- Return ONLY the JSON object with main_tf, variables_tf, outputs_tf.
"""
        return prompt

    def _call(self, user_prompt: str, system_prompt: str, session_id: str = None) -> TerraformBundle:
        logger.debug("Calling Gemini for Terraform generation")
        try:
            # Create Langfuse trace with full input
            from app.services import langfuse_service
            full_input = f"System Prompt:\n{system_prompt}\n\nUser Prompt:\n{user_prompt}"
            trace = langfuse_service.create_trace(
                name="terraform-gen",
                session_id=session_id,
                metadata={"length": len(user_prompt)},
                input=full_input,
            )

            raw = self.llm_service.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=8192,
                response_format={"type": "json_object"},
                timeout=60,
                _trace=trace,
            )
            data = json.loads(raw)
            logger.info("Gemini response parsed successfully. Keys found: %s", list(data.keys()))
            
            # Check for empty content
            for key in ("main_tf", "variables_tf", "outputs_tf"):
                if not data.get(key):
                    logger.warning("Gemini returned empty content for %s", key)

            if trace:
                try:
                    trace.update(output=data)
                    # Ensure events are sent
                    langfuse_service.flush()
                except Exception as e:
                    logger.error(f"Failed to update Langfuse trace: {e}")

            for key in ("main_tf", "variables_tf", "outputs_tf"):
                val = data.get(key, "")
                if isinstance(val, dict):
                    data[key] = json.dumps(val, indent=2)
                else:
                    data[key] = str(val) if val else ""

            return TerraformBundle(**data)
        except Exception as e:
            logger.error("Failed to generate Terraform via Gemini: %s", e, exc_info=True)
            # Return empty bundle rather than crashing background task
            return TerraformBundle(main_tf="", variables_tf="", outputs_tf="")
