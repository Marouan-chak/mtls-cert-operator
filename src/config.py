from kubernetes import client, config
import kubernetes

class Config:
    TENANT_GROUP = "mtls.invoisight.com"
    TENANT_VERSION = "v1"
    CERT_MANAGER_GROUP = "cert-manager.io"
    CERT_MANAGER_VERSION = "v1"
    
    @staticmethod
    def initialize_kubernetes():
        try:
            config.load_incluster_config()
        except kubernetes.config.config_exception.ConfigException:
            config.load_kube_config()
        
        return {
            'core_v1_api': client.CoreV1Api(),
            'custom_objects_api': client.CustomObjectsApi()
        }
