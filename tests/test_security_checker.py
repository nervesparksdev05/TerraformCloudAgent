import pytest
from app.services.security_checker import SecurityChecker
from app.models.schemas import TerraformBundle

@pytest.fixture
def checker():
    return SecurityChecker()

def test_safe_bundle(checker):
    bundle = TerraformBundle(
        main_tf='''
resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}
resource "aws_security_group_rule" "safe" {
  type        = "ingress"
  from_port   = 443
  to_port     = 443
  protocol    = "tcp"
  cidr_blocks = ["0.0.0.0/0"]
}
''',
        variables_tf="",
        outputs_tf="",
    )
    is_valid, msg = checker.validate(bundle)
    assert is_valid is True

def test_open_ssh(checker):
    bundle = TerraformBundle(
        main_tf='''
resource "aws_security_group_rule" "unsafe" {
  type        = "ingress"
  from_port   = 22
  to_port     = 22
  protocol    = "tcp"
  cidr_blocks = ["0.0.0.0/0"]
}
''',
        variables_tf="",
        outputs_tf="",
    )
    is_valid, msg = checker.validate(bundle)
    assert is_valid is False
    assert "Open ingress" in msg

def test_open_rdp_ipv6(checker):
    bundle = TerraformBundle(
        main_tf='''
resource "aws_security_group_rule" "unsafe" {
  type             = "ingress"
  from_port        = 3389
  to_port          = 3389
  protocol         = "tcp"
  ipv6_cidr_blocks = ["::/0"]
}
''',
        variables_tf="",
        outputs_tf="",
    )
    is_valid, msg = checker.validate(bundle)
    assert is_valid is False
    assert "Open ingress" in msg

def test_gcp_open_ssh(checker):
    bundle = TerraformBundle(
        main_tf='''
resource "google_compute_firewall" "allow-ssh" {
  name    = "allow-ssh"
  network = "default"
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
  source_ranges = ["0.0.0.0/0"]
}
''',
        variables_tf="",
        outputs_tf="",
    )
    is_valid, msg = checker.validate(bundle)
    assert is_valid is False
    assert "Open ingress" in msg

def test_wildcard_iam(checker):
    bundle = TerraformBundle(
        main_tf='''
resource "aws_iam_policy" "unsafe" {
  policy = jsonencode({
    Statement = [{
      Action   = "*"
      Effect   = "Allow"
      Resource = "*"
    }]
  })
}
''',
        variables_tf="",
        outputs_tf="",
    )
    is_valid, msg = checker.validate(bundle)
    assert is_valid is False
    assert "permissive wildcard IAM policy" in msg

def test_default_vpc_manipulation(checker):
    bundle = TerraformBundle(
        main_tf='''
resource "aws_default_vpc" "default" {
  tags = {
    Name = "Default VPC"
  }
}
''',
        variables_tf="",
        outputs_tf="",
    )
    is_valid, msg = checker.validate(bundle)
    assert is_valid is False
    assert "aws_default_vpc" in msg

def test_local_exec_provisioner(checker):
    bundle = TerraformBundle(
        main_tf='''
resource "null_resource" "exec" {
  provisioner "local-exec" {
    command = "rm -rf /"
  }
}
''',
        variables_tf="",
        outputs_tf="",
    )
    is_valid, msg = checker.validate(bundle)
    assert is_valid is False
    assert "local-exec" in msg
