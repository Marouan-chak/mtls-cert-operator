# services/ca_chain_service.py
from kubernetes.client import V1Secret, V1ObjectMeta
from kubernetes.client.rest import ApiException
import base64
import kopf
from utils.logging import setup_logger
from typing import List, Optional, Dict, Any

class CAChainService:
    def __init__(self, core_v1_api, custom_objects_api):
        self.core_v1_api = core_v1_api
        self.custom_objects_api = custom_objects_api
        self.logger = setup_logger('ca-chain-service')

    def create_or_update_ca_chain(
        self,
        namespace: str,
        excluded_tenant: Optional[str] = None,
        force_include: Optional[str] = None
    ) -> None:
        """
        Update the CA chain secret.
        
        Args:
            namespace: Kubernetes namespace
            excluded_tenant: Tenant to exclude from the chain
            force_include: Tenant to force include even if revoked
        """
        try:
            self.logger.info(f"Updating CA chain (excluded: {excluded_tenant}, force include: {force_include})")
            
            root_ca = self._get_root_ca(namespace)
            chain = [root_ca]
            
            tenants = self._get_tenants(namespace)
            chain.extend(self._get_intermediate_cas(namespace, tenants, excluded_tenant, force_include))
            
            self._update_chain_secret(namespace, chain)
            
        except Exception as e:
            self.logger.error(f"Failed to update CA chain: {e}")
            raise kopf.PermanentError(f"Failed to update CA chain: {str(e)}")

    def _get_root_ca(self, namespace: str) -> bytes:
        """Retrieve root CA certificate."""
        try:
            root_ca_secret = self.core_v1_api.read_namespaced_secret('root-ca-secret', namespace)
            if not root_ca_secret.data or 'tls.crt' not in root_ca_secret.data:
                raise kopf.PermanentError(f"Root CA secret is missing or invalid in namespace {namespace}")
            
            self.logger.info("Successfully read root CA certificate")
            return base64.b64decode(root_ca_secret.data['tls.crt'])
            
        except ApiException as e:
            self.logger.error(f"Failed to read root CA secret: {e}")
            raise kopf.PermanentError(f"Failed to read root CA secret: {e}")

    def _get_tenants(self, namespace: str) -> List[Dict[str, Any]]:
        """Retrieve all tenants in the namespace."""
        try:
            tenants = self.custom_objects_api.list_namespaced_custom_object(
                'mtls.invoisight.com', 'v1', namespace, 'tenants'
            )
            self.logger.info(f"Found {len(tenants['items'])} tenants")
            return tenants['items']
            
        except ApiException as e:
            self.logger.error(f"Failed to list tenants: {e}")
            raise kopf.PermanentError(f"Failed to list tenants: {e}")

    def _get_intermediate_cas(
        self,
        namespace: str,
        tenants: List[Dict[str, Any]],
        excluded_tenant: Optional[str],
        force_include: Optional[str]
    ) -> List[bytes]:
        """Retrieve intermediate CA certificates for all valid tenants."""
        intermediate_cas = []
        
        for tenant in tenants:
            tenant_name = tenant['spec']['name']
            tenant_status = tenant.get('status', {})
            
            if self._should_skip_tenant(tenant_name, tenant_status, excluded_tenant, force_include):
                continue
                
            ca_cert = self._get_tenant_ca(namespace, tenant_name)
            if ca_cert:
                intermediate_cas.append(ca_cert)
                
        return intermediate_cas

    def _should_skip_tenant(
        self,
        tenant_name: str,
        tenant_status: Dict[str, Any],
        excluded_tenant: Optional[str],
        force_include: Optional[str]
    ) -> bool:
        """Determine if a tenant should be skipped in the CA chain."""
        if excluded_tenant and tenant_name == excluded_tenant:
            self.logger.info(f"Excluding tenant {tenant_name} from CA chain")
            return True
            
        if tenant_status.get('isRevoked', False) and tenant_name != force_include:
            self.logger.info(f"Skipping revoked tenant {tenant_name}")
            return True
            
        return False

    def _get_tenant_ca(self, namespace: str, tenant_name: str) -> Optional[bytes]:
        """Retrieve CA certificate for a specific tenant."""
        secret_name = f"{tenant_name}-intermediate-ca-secret"
        try:
            secret = self.core_v1_api.read_namespaced_secret(secret_name, namespace)
            if secret.data and 'tls.crt' in secret.data:
                self.logger.info(f"Added {tenant_name} intermediate CA to chain")
                return base64.b64decode(secret.data['tls.crt'])
            else:
                self.logger.warning(f"Secret {secret_name} exists but has no valid certificate")
                return None
        except ApiException as e:
            if e.status != 404:
                self.logger.error(f"Failed to get CA for {tenant_name}: {e}")
            else:
                self.logger.warning(f"Secret {secret_name} not found")
            return None

    def _update_chain_secret(self, namespace: str, chain: List[bytes]) -> None:
        """Update the CA chain secret with the new certificate chain."""
        combined_chain = b'\n'.join(filter(None, chain))
        secret = V1Secret(
            metadata=V1ObjectMeta(name='ca-chain-secret'),
            data={'ca.crt': base64.b64encode(combined_chain).decode('utf-8')}
        )
        
        try:
            self.core_v1_api.replace_namespaced_secret('ca-chain-secret', namespace, secret)
            self.logger.info("Successfully updated ca-chain-secret")
        except ApiException as e:
            if e.status == 404:
                self.core_v1_api.create_namespaced_secret(namespace, secret)
                self.logger.info("Successfully created ca-chain-secret")
            else:
                self.logger.error(f"Failed to update ca-chain-secret: {e}")
                raise