"""test_digitalocean_support.py — Unit tests for DigitalOcean provider support."""

import asyncio
import json
from unittest.mock import MagicMock, AsyncMock, patch

from app.services.conversation_manager import (
    ConversationManager, _validate_completeness, _derive_traffic_params,
)
from app.services.llm_generator import LLMGenerator


# ── Helper ──────────────────────────────────────────────────────────────────

def _cm():
    with patch("app.services.conversation_manager.ConversationManager._init_mongo", return_value=MagicMock()):
        cm = ConversationManager()
    cm._save_session = MagicMock()
    return cm


def _base_do(env="dev"):
    return {
        "cloud_provider": "digitalocean",
        "environment": env,
    }


# ── Tests ────────────────────────────────────────────────────────────────────

def test_validate_completeness_missing_do_region():
    print("\n--- Test: _validate_completeness requires do_region for DO ---")
    p = _base_do(env="dev")
    # Only have cloud_provider + environment, no do_region
    missing = _validate_completeness(p)
    missing_names = " ".join(missing)
    assert "do_region" in missing_names, f"Expected do_region in missing, got: {missing}"
    print("[OK] do_region is correctly flagged as missing")


def test_validate_completeness_missing_ssh_key():
    print("\n--- Test: _validate_completeness requires ssh_key_name for DO ---")
    p = _base_do(env="dev")
    p["do_region"] = "nyc3"
    missing = _validate_completeness(p)
    missing_names = " ".join(missing)
    assert "ssh_key_name" in missing_names, f"Expected ssh_key_name in missing, got: {missing}"
    print("[OK] ssh_key_name is correctly flagged as missing")


def test_validate_completeness_missing_alert_email():
    print("\n--- Test: _validate_completeness requires alert_email for DO ---")
    p = _base_do(env="dev")
    p["do_region"] = "nyc3"
    p["ssh_key_name"] = "my-do-key"
    missing = _validate_completeness(p)
    missing_names = " ".join(missing)
    assert "alert_email" in missing_names, f"Expected alert_email in missing, got: {missing}"
    print("[OK] alert_email is correctly flagged as missing")


def test_validate_completeness_complete():
    print("\n--- Test: _validate_completeness passes when DO fields are full ---")
    p = _base_do(env="dev")
    p["do_region"] = "nyc3"
    p["ssh_key_name"] = "my-do-key"
    p["alert_email"] = "ops@example.com"
    p["database_type"] = "none"
    missing = _validate_completeness(p)
    # We only check none of the DO-required fields appear
    critical = [m for m in missing if any(x in m for x in ("do_region", "ssh_key_name", "alert_email"))]
    assert not critical, f"Unexpected DO fields missing: {critical}"
    print("[OK] DO session validated as complete")


def test_derive_traffic_params_low():
    print("\n--- Test: _derive_traffic_params sets s-1vcpu-2gb for <500 DAU ---")
    p = {"cloud_provider": "digitalocean", "daily_active_users": 100}
    _derive_traffic_params(p)
    assert p.get("droplet_size") == "s-1vcpu-2gb", f"Expected s-1vcpu-2gb, got: {p.get('droplet_size')}"
    assert p.get("traffic_tier") == "low"
    print(f"[OK] Low-traffic DO: {p['droplet_size']}, tier={p['traffic_tier']}")


def test_derive_traffic_params_medium():
    print("\n--- Test: _derive_traffic_params sets s-2vcpu-4gb for 500-2000 DAU ---")
    p = {"cloud_provider": "digitalocean", "daily_active_users": 1000}
    _derive_traffic_params(p)
    assert p.get("droplet_size") == "s-2vcpu-4gb", f"Expected s-2vcpu-4gb, got: {p.get('droplet_size')}"
    assert p.get("traffic_tier") == "medium"
    assert p.get("use_alb") is True
    print(f"[OK] Medium-traffic DO: {p['droplet_size']}, tier={p['traffic_tier']}")


def test_derive_traffic_params_high():
    print("\n--- Test: _derive_traffic_params sets s-4vcpu-8gb for 2000-10000 DAU ---")
    p = {"cloud_provider": "digitalocean", "daily_active_users": 5000}
    _derive_traffic_params(p)
    assert p.get("droplet_size") == "s-4vcpu-8gb", f"Expected s-4vcpu-8gb, got: {p.get('droplet_size')}"
    assert p.get("traffic_tier") == "high"
    print(f"[OK] High-traffic DO: {p['droplet_size']}, tier={p['traffic_tier']}")


def test_derive_traffic_params_extreme():
    print("\n--- Test: _derive_traffic_params sets c-8 for >10000 DAU ---")
    p = {"cloud_provider": "digitalocean", "daily_active_users": 50000}
    _derive_traffic_params(p)
    assert p.get("droplet_size") == "c-8", f"Expected c-8, got: {p.get('droplet_size')}"
    assert p.get("traffic_tier") == "extreme"
    print(f"[OK] Extreme-traffic DO: {p['droplet_size']}, tier={p['traffic_tier']}")


def test_calculate_cost_do():
    print("\n--- Test: _calculate_cost returns DO cost estimate ---")
    cm = _cm()
    p = {
        "cloud_provider": "digitalocean",
        "environment": "dev",
        "droplet_size": "s-1vcpu-1gb",
        "traffic_tier": "low",
        "has_database": False,
        "has_cache": False,
        "use_alb": False,
        "use_asg": False,
    }
    cost_str = cm._calculate_cost(p)
    assert "DIGITALOCEAN" in cost_str.upper(), f"Expected DIGITALOCEAN in cost output: {cost_str[:200]}"
    print("[OK] DO cost estimate contains DIGITALOCEAN label")
    print("     Sample: " + cost_str[:200].encode("ascii", "ignore").decode("ascii"))


def test_build_terraform_request_do():
    print("\n--- Test: build_terraform_request sets do_region and droplet_size ---")
    cm = _cm()
    # Create a fake session using MagicMock
    sess = MagicMock()
    sess.collected_parameters = {
        "cloud_provider": "digitalocean",
        "environment": "dev",
        "do_region": "fra1",
        "droplet_size": "s-1vcpu-2gb",
        "ssh_key_name": "my-key",
        "alert_email": "ops@example.com",
    }
    cm.get_session = MagicMock(return_value=sess)
    req = cm.build_terraform_request("test-do-sess")
    assert req["cloud_provider"] == "digitalocean"
    assert req["do_region"] == "fra1"
    assert req["aws_region"] is None
    assert req["gcp_region"] is None
    print(f"[OK] build_terraform_request: do_region={req['do_region']}, aws_region={req['aws_region']}")


def test_llm_generator_do_system_prompt():
    print("\n--- Test: LLMGenerator._DO_SYSTEM contains DO provider block ---")
    gen = LLMGenerator()
    assert "digitalocean/digitalocean" in gen._DO_SYSTEM
    assert "digitalocean_droplet" in gen._DO_SYSTEM
    assert "var.do_token" in gen._DO_SYSTEM
    assert "digitalocean_ssh_key" in gen._DO_SYSTEM
    print("[OK] _DO_SYSTEM contains required DigitalOcean Terraform rules")


def test_llm_generator_build_do_prompt():
    print("\n--- Test: LLMGenerator._build_prompt routes to DO prompt for digitalocean ---")
    gen = LLMGenerator()
    p = {
        "cloud_provider": "digitalocean",
        "environment": "dev",
        "do_region": "nyc3",
        "droplet_size": "s-1vcpu-2gb",
        "project_name": "my-app",
        "github_owner": "acme",
        "github_repo": "my-app",
    }
    prompt = gen._build_prompt(p)
    assert "PROVIDER: DigitalOcean" in prompt, "Expected PROVIDER: DigitalOcean in prompt"
    assert "nyc3" in prompt
    assert "s-1vcpu-2gb" in prompt
    print("[OK] _build_prompt correctly routes to DO prompt for digitalocean provider")


def test_llm_generator_aws_prompt_unaffected():
    print("\n--- Test: LLMGenerator._build_prompt still routes to AWS prompt for aws ---")
    gen = LLMGenerator()
    p = {
        "cloud_provider": "aws",
        "environment": "dev",
        "aws_region": "us-east-1",
        "instance_type": "t3.micro",
        "project_name": "my-app",
        "github_owner": "acme",
        "github_repo": "my-app",
    }
    prompt = gen._build_prompt(p)
    assert "PROVIDER: AWS" in prompt, "Expected PROVIDER: AWS in prompt"
    print("[OK] _build_prompt correctly routes to AWS prompt for aws provider")


if __name__ == "__main__":
    # Run all tests
    tests = [
        test_validate_completeness_missing_do_region,
        test_validate_completeness_missing_ssh_key,
        test_validate_completeness_missing_alert_email,
        test_validate_completeness_complete,
        test_derive_traffic_params_low,
        test_derive_traffic_params_medium,
        test_derive_traffic_params_high,
        test_derive_traffic_params_extreme,
        test_calculate_cost_do,
        test_build_terraform_request_do,
        test_llm_generator_do_system_prompt,
        test_llm_generator_build_do_prompt,
        test_llm_generator_aws_prompt_unaffected,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"FAIL [{t.__name__}]: {e}")
            failed += 1
        except Exception as e:
            import traceback
            print(f"ERROR [{t.__name__}]: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed:
        raise SystemExit(1)
