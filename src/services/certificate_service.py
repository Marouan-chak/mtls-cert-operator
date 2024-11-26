from kubernetes.client import V1Secret, V1ObjectMeta
from kubernetes.client.rest import ApiException
import base64
from config import Config
from utils.logging import setup_logger
from typing import Dict, Any, Optional

class CertificateService:
    def __init__(self, core_v1_api, custom_objects_api):
        self.core_v1_api = core_v1_api
        self.custom_objects_api = custom_objects_api
        self.logger = setup_logger('certificate-service')

    def create_certificate(self, name: str, namespace: str, **kwargs) -> Dict[str, Any]:
        """Create or update a cert-manager Certificate resource."""
        cert = self._build_certificate_spec(name, namespace, kwargs)
        return self._apply_certificate(cert, name, namespace)

    def create_issuer(self, name: str, namespace: str, secret_name: str) -> Dict[str, Any]:
        """Create or update a cert-manager Issuer resource."""
        issuer = self._build_issuer_spec(name, namespace, secret_name)
        return self._apply_issuer(issuer, name, namespace)

    def _build_certificate_spec(self, name: str, namespace: str, spec: Dict[str, Any]) -> Dict[str, Any]:
        """Build Certificate resource specification."""
        return {
            'apiVersion': f'{Config.api.CERT_MANAGER_GROUP}/{Config.api.CERT_MANAGER_VERSION}',
            'kind': 'Certificate',
            'metadata': {
                'name': name,
                'namespace': namespace
            },
            'spec': spec
        }

    def _build_issuer_spec(self, name: str, namespace: str, secret_name: str) -> Dict[str, Any]:
        """Build Issuer resource specification."""
        return {
            'apiVersion': f'{Config.api.CERT_MANAGER_GROUP}/{Config.api.CERT_MANAGER_VERSION}',
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

    def _apply_certificate(self, cert: Dict[str, Any], name: str, namespace: str) -> Dict[str, Any]:
        """Apply Certificate resource to the cluster."""
        try:
            self.custom_objects_api.get_namespaced_custom_object(
                Config.api.CERT_MANAGER_GROUP, Config.api.CERT_MANAGER_VERSION,
                namespace, 'certificates', name
            )
            return self.custom_objects_api.patch_namespaced_custom_object(
                Config.api.CERT_MANAGER_GROUP, Config.api.CERT_MANAGER_VERSION,
                namespace, 'certificates', name, cert
            )
        except ApiException as e:
            if e.status == 404:
                return self.custom_objects_api.create_namespaced_custom_object(
                    Config.api.CERT_MANAGER_GROUP, Config.api.CERT_MANAGER_VERSION,
                    namespace, 'certificates', cert
                )
            raise

    def _apply_issuer(self, issuer: Dict[str, Any], name: str, namespace: str) -> Dict[str, Any]:
        """Apply Issuer resource to the cluster."""
        try:
            self.custom_objects_api.get_namespaced_custom_object(
                Config.api.CERT_MANAGER_GROUP, Config.api.CERT_MANAGER_VERSION,
                namespace, 'issuers', name
            )
            return self.custom_objects_api.patch_namespaced_custom_object(
                Config.api.CERT_MANAGER_GROUP, Config.api.CERT_MANAGER_VERSION,
                namespace, 'issuers', name, issuer
            )
        except ApiException as e:
            if e.status == 404:
                return self.custom_objects_api.create_namespaced_custom_object(
                    Config.api.CERT_MANAGER_GROUP, Config.api.CERT_MANAGER_VERSION,
                    namespace, 'issuers', issuer
                )
            raise
