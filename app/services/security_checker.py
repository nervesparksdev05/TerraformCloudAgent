import re
from typing import Tuple
from app.core.logger import get_logger
from app.models.schemas import TerraformBundle

logger = get_logger(__name__)

class SecurityChecker:
    """
    Validates Terraform configurations for high-risk security flaws manually introduced by users.
    Enforces fail-closed rules.
    """

    def __init__(self):
        # Open ingress patterns across clouds
        self.open_ingress_patterns = [
            re.compile(r'cidr_blocks\s*=\s*\[.*"0\.0\.0\.0/0".*\]'),
            re.compile(r'ipv6_cidr_blocks\s*=\s*\[.*"::/0".*\]'),
            re.compile(r'source_ranges\s*=\s*\[.*"0\.0\.0\.0/0".*\]'),
            re.compile(r'source_addresses\s*=\s*\[.*"0\.0\.0\.0/0",?.*\]')
        ]
        # Risky ports for open ingress
        self.risky_ports = [
            re.compile(r'from_port\s*=\s*22\b'),
            re.compile(r'to_port\s*=\s*22\b'),
            re.compile(r'ports\s*=\s*\[?"22"?\]?'),
            re.compile(r'port_range\s*=\s*"22"'),
            re.compile(r'from_port\s*=\s*3389\b'),
            re.compile(r'to_port\s*=\s*3389\b'),
            re.compile(r'ports\s*=\s*\[?"3389"?\]?'),
            re.compile(r'port_range\s*=\s*"3389"')
        ]
        
        # IAM wildcard (supports both inline JSON and HCL jsonencode)
        self.iam_wildcard_action = re.compile(r'("?)Action("?)\s*[:=]\s*\[?\s*"\*"\s*\]?')
        self.iam_wildcard_resource = re.compile(r'("?)Resource("?)\s*[:=]\s*\[?\s*"\*"\s*\]?')

        # Destructive resources
        self.destructive_resources = [
            re.compile(r'resource\s+"aws_default_vpc"'),
            re.compile(r'resource\s+"aws_default_subnet"'),
            re.compile(r'provisioner\s+"local-exec"')
        ]

    def validate(self, bundle: TerraformBundle, provider: str = "aws") -> Tuple[bool, str]:
        """
        Validates the terraform bundle against security rules.
        Returns (is_valid, error_message)
        """
        tf_code = f"{bundle.main_tf}\n{bundle.variables_tf}\n{bundle.outputs_tf}"
        
        # 1. Check for Destructive or Default Resources
        for pattern in self.destructive_resources:
            if pattern.search(tf_code):
                return False, f"Prohibited resource or provisioner detected: {pattern.pattern}"

        # 2. Check for Open Ingress on Risky Ports
        # Simplistic check: If code mentions an open CIDR and a risky port, flag it.
        has_open_ingress = any(p.search(tf_code) for p in self.open_ingress_patterns)
        has_risky_port = any(p.search(tf_code) for p in self.risky_ports)
        if has_open_ingress and has_risky_port:
            return False, "Open ingress (0.0.0.0/0 or ::/0) on a high-risk port (22 or 3389) detected."

        # 3. Check for Wildcard IAM Policies
        if self.iam_wildcard_action.search(tf_code) and self.iam_wildcard_resource.search(tf_code):
            return False, 'Highly permissive wildcard IAM policy detected ("Action": "*" and "Resource": "*").'

        return True, ""
