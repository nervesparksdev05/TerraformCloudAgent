"""
Service Detection Module - Analyzes README to detect required cloud services.

Supports:
- 15 AWS services: EC2, S3, RDS, Lambda, VPC, IAM, CloudFront, EBS, CloudWatch,
                   ELB, DynamoDB, ECS/EKS, SNS/SQS, Route 53, CloudFormation
- 15 GCP services: Compute Engine, Cloud Storage, Cloud SQL, Cloud Functions, VPC,
                   IAM, Cloud CDN, Persistent Disk, Cloud Monitoring, Load Balancing,
                   Firestore/Bigtable, GKE, Pub/Sub, Cloud DNS, Deployment Manager
"""
from typing import List, Dict, Set, Tuple
import re
from app.core.logger import get_logger

logger = get_logger(__name__)


class ServiceDetector:
    """Detects required cloud services from README content."""

    # AWS Service Detection Patterns
    AWS_SERVICE_PATTERNS = {
        "ec2": {
            "keywords": ["server", "instance", "vm", "compute", "ec2", "virtual machine"],
            "priority": 1,
            "category": "compute"
        },
        "s3": {
            "keywords": ["storage", "bucket", "file upload", "static assets", "s3", "object storage", "cdn assets"],
            "priority": 2,
            "category": "storage"
        },
        "rds": {
            "keywords": ["database", "postgres", "mysql", "mariadb", "rds", "relational database", "sql"],
            "priority": 1,
            "category": "database"
        },
        "lambda": {
            "keywords": ["serverless", "function", "event-driven", "lambda", "faas", "aws lambda"],
            "priority": 1,
            "category": "compute"
        },
        "vpc": {
            "keywords": ["network", "subnet", "vpc", "private network", "virtual private cloud"],
            "priority": 3,
            "category": "networking"
        },
        "iam": {
            "keywords": ["permissions", "roles", "access control", "iam", "identity", "authentication"],
            "priority": 3,
            "category": "security"
        },
        "cloudfront": {
            "keywords": ["cdn", "content delivery", "cloudfront", "edge", "global distribution"],
            "priority": 2,
            "category": "networking"
        },
        "ebs": {
            "keywords": ["volume", "disk", "block storage", "ebs", "persistent storage"],
            "priority": 2,
            "category": "storage"
        },
        "cloudwatch": {
            "keywords": ["monitoring", "logs", "metrics", "cloudwatch", "observability", "alerting"],
            "priority": 2,
            "category": "monitoring"
        },
        "elb": {
            "keywords": ["load balancer", "alb", "nlb", "elb", "load balancing", "traffic distribution"],
            "priority": 2,
            "category": "networking"
        },
        "dynamodb": {
            "keywords": ["nosql", "dynamodb", "key-value", "document database", "non-relational"],
            "priority": 1,
            "category": "database"
        },
        "ecs": {
            "keywords": ["container", "docker", "ecs", "fargate", "container orchestration"],
            "priority": 1,
            "category": "compute"
        },
        "eks": {
            "keywords": ["kubernetes", "k8s", "eks", "container orchestration"],
            "priority": 1,
            "category": "compute"
        },
        "sns": {
            "keywords": ["notification", "pub/sub", "messaging", "sns", "push notification"],
            "priority": 2,
            "category": "messaging"
        },
        "sqs": {
            "keywords": ["queue", "message queue", "sqs", "async processing"],
            "priority": 2,
            "category": "messaging"
        },
        "route53": {
            "keywords": ["dns", "domain", "route53", "domain name"],
            "priority": 2,
            "category": "networking"
        },
        "cloudformation": {
            "keywords": ["infrastructure as code", "iac", "cloudformation", "terraform alternative"],
            "priority": 3,
            "category": "iac"
        }
    }

    # GCP Service Detection Patterns
    GCP_SERVICE_PATTERNS = {
        "compute_engine": {
            "keywords": ["server", "instance", "vm", "compute engine", "virtual machine", "gce"],
            "priority": 1,
            "category": "compute"
        },
        "cloud_storage": {
            "keywords": ["storage", "bucket", "file upload", "cloud storage", "gcs", "object storage"],
            "priority": 2,
            "category": "storage"
        },
        "cloud_sql": {
            "keywords": ["database", "postgres", "mysql", "cloud sql", "relational database", "sql"],
            "priority": 1,
            "category": "database"
        },
        "cloud_functions": {
            "keywords": ["serverless", "function", "cloud functions", "gcf", "event-driven"],
            "priority": 1,
            "category": "compute"
        },
        "vpc": {
            "keywords": ["network", "subnet", "vpc", "private network", "virtual private cloud"],
            "priority": 3,
            "category": "networking"
        },
        "iam": {
            "keywords": ["permissions", "roles", "access control", "iam", "service account"],
            "priority": 3,
            "category": "security"
        },
        "cloud_cdn": {
            "keywords": ["cdn", "content delivery", "cloud cdn", "edge", "global distribution"],
            "priority": 2,
            "category": "networking"
        },
        "persistent_disk": {
            "keywords": ["volume", "disk", "persistent disk", "block storage"],
            "priority": 2,
            "category": "storage"
        },
        "cloud_monitoring": {
            "keywords": ["monitoring", "logs", "metrics", "stackdriver", "cloud monitoring", "observability"],
            "priority": 2,
            "category": "monitoring"
        },
        "cloud_load_balancing": {
            "keywords": ["load balancer", "load balancing", "traffic distribution"],
            "priority": 2,
            "category": "networking"
        },
        "firestore": {
            "keywords": ["nosql", "firestore", "document database", "realtime database"],
            "priority": 1,
            "category": "database"
        },
        "bigtable": {
            "keywords": ["bigtable", "wide-column", "nosql", "time-series"],
            "priority": 1,
            "category": "database"
        },
        "gke": {
            "keywords": ["kubernetes", "k8s", "gke", "container orchestration"],
            "priority": 1,
            "category": "compute"
        },
        "pubsub": {
            "keywords": ["pub/sub", "messaging", "pubsub", "event streaming"],
            "priority": 2,
            "category": "messaging"
        },
        "cloud_dns": {
            "keywords": ["dns", "domain", "cloud dns"],
            "priority": 2,
            "category": "networking"
        },
        "deployment_manager": {
            "keywords": ["infrastructure as code", "iac", "deployment manager"],
            "priority": 3,
            "category": "iac"
        }
    }

    # Service Dependencies
    SERVICE_DEPENDENCIES = {
        "ec2": ["vpc", "iam"],
        "rds": ["vpc", "ec2"],
        "lambda": ["iam", "cloudwatch"],
        "ecs": ["vpc", "iam", "cloudwatch"],
        "eks": ["vpc", "iam", "cloudwatch"],
        "elb": ["vpc", "ec2"],
        "cloudfront": ["s3"],
        "compute_engine": ["vpc", "iam"],
        "cloud_sql": ["vpc", "compute_engine"],
        "cloud_functions": ["iam", "cloud_monitoring"],
        "gke": ["vpc", "iam", "cloud_monitoring"],
        "cloud_load_balancing": ["vpc", "compute_engine"]
    }

    def __init__(self):
        logger.info("ServiceDetector initialized")

    def detect_services(self, readme: str, provider: str = "aws") -> Dict[str, any]:
        """
        Detect required cloud services from README content.

        Args:
            readme: README content to analyze
            provider: Cloud provider ("aws" or "gcp")

        Returns:
            Dict with detected services, priorities, and categories
        """
        readme_lower = readme.lower()
        patterns = self.AWS_SERVICE_PATTERNS if provider == "aws" else self.GCP_SERVICE_PATTERNS

        detected = {}
        for service_name, config in patterns.items():
            score = self._calculate_service_score(readme_lower, config["keywords"])
            if score > 0:
                detected[service_name] = {
                    "score": score,
                    "priority": config["priority"],
                    "category": config["category"]
                }

        logger.info(f"Detected {len(detected)} services for {provider}: {list(detected.keys())}")
        return detected

    def _calculate_service_score(self, text: str, keywords: List[str]) -> int:
        """Calculate relevance score based on keyword matches."""
        score = 0
        for keyword in keywords:
            # Exact match
            if keyword in text:
                score += 2
            # Word boundary match (more precise)
            if re.search(rf'\b{re.escape(keyword)}\b', text):
                score += 3

        return score

    def prioritize_services(self, detected_services: Dict[str, any]) -> List[str]:
        """
        Sort services by priority and score.

        Returns:
            List of service names in order of importance
        """
        sorted_services = sorted(
            detected_services.items(),
            key=lambda x: (x[1]["priority"], -x[1]["score"])
        )
        return [service for service, _ in sorted_services]

    def get_service_dependencies(self, services: List[str]) -> Dict[str, List[str]]:
        """
        Get dependencies for detected services.

        Args:
            services: List of detected service names

        Returns:
            Dict mapping each service to its dependencies
        """
        dependencies = {}
        for service in services:
            deps = self.SERVICE_DEPENDENCIES.get(service, [])
            # Only include dependencies that are relevant
            dependencies[service] = [d for d in deps if d not in services]

        return dependencies

    def get_service_categories(self, services: List[str], provider: str = "aws") -> Dict[str, List[str]]:
        """
        Group services by category.

        Returns:
            Dict mapping category to list of services
        """
        patterns = self.AWS_SERVICE_PATTERNS if provider == "aws" else self.GCP_SERVICE_PATTERNS
        categories = {}

        for service in services:
            if service in patterns:
                category = patterns[service]["category"]
                if category not in categories:
                    categories[category] = []
                categories[category].append(service)

        return categories

    def suggest_additional_services(
        self,
        detected_services: List[str],
        environment: str = "production"
    ) -> List[Tuple[str, str]]:
        """
        Suggest additional services based on detected services and environment.

        Args:
            detected_services: List of already detected services
            environment: "development" or "production"

        Returns:
            List of (service_name, reason) tuples
        """
        suggestions = []

        # If compute detected, suggest monitoring
        if any(s in detected_services for s in ["ec2", "lambda", "ecs", "compute_engine", "cloud_functions"]):
            if "cloudwatch" not in detected_services and "cloud_monitoring" not in detected_services:
                suggestions.append(("cloudwatch", "Monitoring is essential for production workloads"))

        # If database detected, suggest backups
        if any(s in detected_services for s in ["rds", "dynamodb", "cloud_sql", "firestore"]):
            if environment == "production":
                suggestions.append(("backup", "Automated backups recommended for production databases"))

        # If public-facing app, suggest CDN
        if any(s in detected_services for s in ["ec2", "elb", "compute_engine"]):
            if "cloudfront" not in detected_services and "cloud_cdn" not in detected_services:
                suggestions.append(("cloudfront", "CDN can improve global performance"))

        # If containers detected, suggest orchestration
        if "docker" in str(detected_services).lower():
            if "ecs" not in detected_services and "eks" not in detected_services and "gke" not in detected_services:
                suggestions.append(("ecs", "Container orchestration recommended for Docker workloads"))

        return suggestions
