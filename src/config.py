from kubernetes import client, config
import kubernetes
from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class APIConfig:
    TENANT_GROUP: str = "mtls.invoisight.com"
    TENANT_VERSION: str = "v1"
    CERT_MANAGER_GROUP: str = "cert-manager.io"
    CERT_MANAGER_VERSION: str = "v1"

class Config:
    api = APIConfig()
    
    @staticmethod
    def initialize_kubernetes() -> Dict[str, Any]:
        """Initialize Kubernetes client configuration."""
        try:
            config.load_incluster_config()
        except kubernetes.config.config_exception.ConfigException:
            config.load_kube_config()
        
        return {
            'core_v1_api': client.CoreV1Api(),
            'custom_objects_api': client.CustomObjectsApi()
        }
