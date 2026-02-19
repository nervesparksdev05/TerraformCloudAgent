"""
Shared constants for the application.
"""

SUPPORTED_PROVIDERS = ["aws", "gcp", "azure", "digitalocean"]
UNKNOWN_PROVIDER = "unknown"

PROVIDER_ALIASES = {
    "aws": "aws",
    "amazon": "aws",
    "gcp": "gcp",
    "google": "gcp",
    "azure": "azure",
    "do": "digitalocean",
    "digitalocean": "digitalocean",
    "digital-ocean": "digitalocean",
    "unknown": "unknown",
}

PROVIDER_DISPLAY_NAMES = {
    "aws": "AWS",
    "gcp": "Google Cloud",
    "azure": "Microsoft Azure",
    "digitalocean": "DigitalOcean",
}

PROVIDER_DEFAULTS = {
    "aws": {
        "region_key": "aws_region",
        "default_region": "us-east-1",
        "default_instance": "t3.micro",
        "default_storage_type": "gp3",
        "default_os_image": "ubuntu-22.04",
    },
    "gcp": {
        "region_key": "gcp_region",
        "default_region": "us-central1",
        "default_instance": "e2-micro",
        "default_storage_type": "pd-balanced",
        "default_os_image": "projects/ubuntu-os-cloud/global/images/family/ubuntu-2204-lts",
    },
    "azure": {
        "region_key": "azure_location",
        "default_region": "eastus",
        "default_instance": "B1s",
        "default_storage_type": "StandardSSD_LRS",
        "default_os_image": "UbuntuLTS",
    },
    "digitalocean": {
        "region_key": "do_region",
        "default_region": "nyc1",
        "default_instance": "basic-1vcpu-1gb",
        "default_storage_type": "",
        "default_os_image": "ubuntu-22-04-x64",
    },
    # Fallback default (usually AWS)
    "default": {
        "region_key": "aws_region",
        "default_region": "us-east-1",
        "default_instance": "t3.micro",
        "default_storage_type": "gp3",
        "default_os_image": "ubuntu-22.04",
    }
}
