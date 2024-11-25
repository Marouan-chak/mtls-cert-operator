from kubernetes.client import V1Secret, V1ObjectMeta
from kubernetes.client.rest import ApiException
import base64
from config import Config
from utils.logging import setup_logger

logger = setup_logger('certificate-service')

class CertificateService:
    def __init__(self, core_v1_api, custom_objects_api):
        self.core_v1_api = core_v1_api
        self.custom_objects_api = custom_objects_api

    def create_certificate(self, name, namespace, **kwargs):
        """Create a cert-manager Certificate resource if it doesn't exist."""
        cert = {
            'apiVersion': f'{Config.CERT_MANAGER_GROUP}/{Config.CERT_MANAGER_VERSION}',
            'kind': 'Certificate',
            'metadata': {
                'name': name,
                'namespace': namespace
            },
            'spec': kwargs
        }
        try:
            # Try to get existing certificate
            self.custom_objects_api.get_namespaced_custom_object(
                Config.CERT_MANAGER_GROUP, Config.CERT_MANAGER_VERSION,
                namespace, 'certificates', name
            )
            # If it exists, update it
            return self.custom_objects_api.patch_namespaced_custom_object(
                Config.CERT_MANAGER_GROUP, Config.CERT_MANAGER_VERSION,
                namespace, 'certificates', name, cert
            )
        except ApiException as e:
            if e.status == 404:
                # If it doesn't exist, create it
                return self.custom_objects_api.create_namespaced_custom_object(
                    Config.CERT_MANAGER_GROUP, Config.CERT_MANAGER_VERSION,
                    namespace, 'certificates', cert
                )
            raise

    def create_issuer(self, name, namespace, secret_name):
        """Create a cert-manager Issuer resource if it doesn't exist."""
        issuer = {
            'apiVersion': f'{Config.CERT_MANAGER_GROUP}/{Config.CERT_MANAGER_VERSION}',
            'kind': 'Issuer',
            'metadata': {
                'name': name,
                'namespace': namespace
            },
            'spec': {
                'ca': {
                    'secretName': secret_name
                }
            }
        }
        try:
            # Try to get existing issuer
            self.custom_objects_api.get_namespaced_custom_object(
                Config.CERT_MANAGER_GROUP, Config.CERT_MANAGER_VERSION,
                namespace, 'issuers', name
            )
            # If it exists, update it
            return self.custom_objects_api.patch_namespaced_custom_object(
                Config.CERT_MANAGER_GROUP, Config.CERT_MANAGER_VERSION,
                namespace, 'issuers', name, issuer
            )
        except ApiException as e:
            if e.status == 404:
                # If it doesn't exist, create it
                return self.custom_objects_api.create_namespaced_custom_object(
                    Config.CERT_MANAGER_GROUP, Config.CERT_MANAGER_VERSION,
                    namespace, 'issuers', issuer
                )
            raise
