# controllers/tenant_controller.py
import kopf
from kubernetes.client.rest import ApiException
from utils.logging import setup_logger
from utils.kubernetes import KubernetesUtils
from config import Config
from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class TenantResources:
    """Data class for tenant resource names."""
    intermediate_ca: str
    client_cert: str
    intermediate_ca_secret: str
    client_cert_secret: str
    
    @classmethod
    def from_tenant_name(cls, tenant_name: str) -> 'TenantResources':
        """Create resource names from tenant name."""
        intermediate_ca = f"{tenant_name}-intermediate-ca"
        return cls(
            intermediate_ca=intermediate_ca,
            client_cert=f"{tenant_name}-client-cert",
            intermediate_ca_secret=f"{intermediate_ca}-secret",
            client_cert_secret=f"{tenant_name}-client-cert-secret"
        )

class TenantController:
    def __init__(self, core_v1_api, custom_objects_api, cert_service, ca_chain_service):
        self.core_v1_api = core_v1_api
        self.custom_objects_api = custom_objects_api
        self.cert_service = cert_service
        self.ca_chain_service = ca_chain_service
        self.logger = setup_logger('tenant-controller')
        self.kube_utils = KubernetesUtils()

    def create_tenant(self, spec: Dict[str, Any], meta: Dict[str, Any], patch: Dict[str, Any], body: Dict[str, Any]) -> None:
        """Handle tenant creation."""
        tenant_name = spec['name']
        namespace = meta['namespace']
        self.logger.info(f"Creating tenant {tenant_name}")
        
        try:
            kopf.info(body, reason='Creating', message=f'Creating tenant {tenant_name}')
            patch.status['state'] = 'Creating'
            
            resources = TenantResources.from_tenant_name(tenant_name)
            initially_revoked = spec.get('revoked', False)
            
            self._create_tenant_certificates(namespace, resources, tenant_name)
            self._update_tenant_status(patch, resources, initially_revoked)
            self._update_ca_chain(namespace, tenant_name, initially_revoked)
            
            kopf.info(body, reason='Created', message=f'Successfully created tenant {tenant_name}')
            
        except Exception as e:
            self._handle_creation_failure(patch, body, tenant_name, str(e))
            raise kopf.PermanentError(str(e))

    def _create_tenant_certificates(self, namespace: str, resources: TenantResources, tenant_name: str) -> None:
        """Create intermediate CA and client certificates for tenant."""
        # Create intermediate CA certificate
        self.cert_service.create_certificate(
            name=resources.intermediate_ca,
            namespace=namespace,
            isCA=True,
            commonName=f"{tenant_name}-intermediate-ca",
            secretName=resources.intermediate_ca_secret,
            privateKey={'algorithm': 'RSA', 'size': 4096},
            issuerRef={
                'name': 'root-ca-issuer',
                'kind': 'ClusterIssuer',
                'group': 'cert-manager.io'
            },
            usages=['digital signature', 'key encipherment', 'cert sign']
        )
        
        self.kube_utils.wait_for_secret(self.core_v1_api, resources.intermediate_ca_secret, namespace)
        
        # Create issuer
        self.cert_service.create_issuer(
            name=resources.intermediate_ca,
            namespace=namespace,
            secret_name=resources.intermediate_ca_secret
        )
        
        # Create client certificate
        self.cert_service.create_certificate(
            name=resources.client_cert,
            namespace=namespace,
            commonName=tenant_name,
            secretName=resources.client_cert_secret,
            privateKey={'algorithm': 'RSA', 'size': 2048},
            issuerRef={
                'name': resources.intermediate_ca,
                'kind': 'Issuer',
                'group': 'cert-manager.io'
            },
            usages=['digital signature', 'key encipherment', 'client auth']
        )
        
        self.kube_utils.wait_for_secret(self.core_v1_api, resources.client_cert_secret, namespace)

    def _update_tenant_status(self, patch: Dict[str, Any], resources: TenantResources, initially_revoked: bool) -> None:
        """Update tenant status with certificate information."""
        patch.status.update({
            'intermediateCA': resources.intermediate_ca,
            'clientCert': resources.client_cert,
            'isRevoked': initially_revoked,
            'state': 'Revoked' if initially_revoked else 'Active'
        })

    def _update_ca_chain(self, namespace: str, tenant_name: str, is_revoked: bool) -> None:
        """Update CA chain considering tenant state."""
        self.ca_chain_service.create_or_update_ca_chain(
            namespace=namespace,
            excluded_tenant=tenant_name if is_revoked else None
        )

    def _handle_creation_failure(self, patch: Dict[str, Any], body: Dict[str, Any], tenant_name: str, error_msg: str) -> None:
        """Handle tenant creation failure."""
        patch.status['state'] = 'Failed'
        patch.status['message'] = error_msg
        kopf.warn(body, reason='Failed', message=f'Failed to create tenant: {error_msg}')

    def delete_tenant(self, spec: Dict[str, Any], meta: Dict[str, Any]) -> None:
        """Handle tenant deletion."""
        tenant_name = spec['name']
        namespace = meta['namespace']
        self.logger.info(f"Deleting tenant {tenant_name}")
        
        # Update CA chain first
        self.ca_chain_service.create_or_update_ca_chain(
            namespace=namespace,
            excluded_tenant=tenant_name
        )
        
        resources = TenantResources.from_tenant_name(tenant_name)
        self._cleanup_tenant_resources(namespace, resources)

    def _cleanup_tenant_resources(self, namespace: str, resources: TenantResources) -> None:
        """Clean up all resources associated with a tenant."""
        cleanup_items = [
            ('certificates', resources.intermediate_ca),
            ('certificates', resources.client_cert),
            ('issuers', resources.intermediate_ca),
            ('secrets', resources.intermediate_ca_secret),
            ('secrets', resources.client_cert_secret)
        ]
        
        for resource_type, name in cleanup_items:
            try:
                if resource_type == 'secrets':
                    self.core_v1_api.delete_namespaced_secret(name, namespace)
                else:
                    self.custom_objects_api.delete_namespaced_custom_object(
                        Config.api.CERT_MANAGER_GROUP,
                        Config.api.CERT_MANAGER_VERSION,
                        namespace,
                        resource_type,
                        name
                    )
            except ApiException as e:
                if e.status != 404:  # Ignore if already deleted
                    self.logger.error(f"Failed to delete {resource_type} {name}: {e}")

    def handle_revocation_request(
        self,
        spec: Dict[str, Any],
        status: Dict[str, Any],
        old: bool,
        new: bool,
        patch: Dict[str, Any],
        meta: Dict[str, Any],
        body: Dict[str, Any]
    ) -> None:
        """Handle tenant revocation state changes."""
        tenant_name = spec['name']
        namespace = meta['namespace']
        
        if new and not old:  # Revoking
            self._handle_revocation(tenant_name, namespace, patch, body)
        elif old and not new:  # Unrevoking
            self._handle_unrevocation(tenant_name, namespace, status, patch, body)

    def _handle_revocation(self, tenant_name: str, namespace: str, patch: Dict[str, Any], body: Dict[str, Any]) -> None:
        """Handle tenant revocation."""
        self.logger.info(f"Revoking tenant {tenant_name}")
        kopf.info(body, reason='Revoking', message=f'Revoking tenant {tenant_name}')
        
        self.ca_chain_service.create_or_update_ca_chain(
            namespace=namespace,
            excluded_tenant=tenant_name
        )
        
        patch.status.update({
            'isRevoked': True,
            'state': 'Revoked'
        })
        
        kopf.info(body, reason='Revoked', message=f'Successfully revoked tenant {tenant_name}')

    def _handle_unrevocation(
        self,
        tenant_name: str,
        namespace: str,
        status: Dict[str, Any],
        patch: Dict[str, Any],
        body: Dict[str, Any]
    ) -> None:
        """Handle tenant unrevocation."""
        if status.get('isRevoked', False):
            self.logger.info(f"Unrevoking tenant {tenant_name}")
            kopf.info(body, reason='Unrevoking', message=f'Unrevoking tenant {tenant_name}')
            
            self.ca_chain_service.create_or_update_ca_chain(
                namespace=namespace,
                force_include=tenant_name
            )
            
            patch.status.update({
                'isRevoked': False,
                'state': 'Active'
            })
            
            kopf.info(body, reason='Unrevoked', message=f'Successfully unrevoked tenant {tenant_name}')

    def reconcile_tenant(self, spec: Dict[str, Any], meta: Dict[str, Any], status: Dict[str, Any], patch: Dict[str, Any]) -> None:
        """Reconcile failed tenants."""
        if status.get('state') != 'Failed':
            return None
            
        tenant_name = spec['name']
        namespace = meta['namespace']
        self.logger.info(f"Reconciling failed tenant {tenant_name}")
        
        try:
            resources = TenantResources.from_tenant_name(tenant_name)
            self._create_tenant_certificates(namespace, resources, tenant_name)
            
            patch.status.update({
                'intermediateCA': resources.intermediate_ca,
                'clientCert': resources.client_cert,
                'isRevoked': spec.get('revoked', False),
                'state': 'Active',
                'message': 'Reconciliation successful'
            })
            
        except Exception as e:
            self.logger.error(f"Reconciliation failed for {tenant_name}: {e}")
            patch.status['message'] = f"Reconciliation failed: {str(e)}"

    def check_ca_chain_secret(self, meta: Dict[str, Any]) -> None:
        """Periodically check and recreate ca-chain-secret if missing."""
        try:
            namespace = meta['namespace']
            
            try:
                self.core_v1_api.read_namespaced_secret('ca-chain-secret', namespace)
                return None
            except ApiException as e:
                if e.status != 404:
                    return None
                
                self.logger.info(f"ca-chain-secret not found in namespace {namespace}, recreating...")
                self._recreate_ca_chain(namespace)
                
        except Exception as e:
            self.logger.error(f"Failed to check/recreate ca-chain-secret: {e}")

    def _recreate_ca_chain(self, namespace: str) -> None:
        """Recreate the CA chain secret."""
        try:
            tenants = self.custom_objects_api.list_namespaced_custom_object(
                'mtls.invoisight.com', 'v1', namespace, 'tenants'
            )
            
            revoked_tenants = [
                t['spec']['name'] for t in tenants['items']
                if t.get('status', {}).get('isRevoked', False)
            ]
            
            if revoked_tenants:
                self.logger.info(f"Excluding revoked tenants from chain: {revoked_tenants}")
                for tenant in revoked_tenants:
                    self.ca_chain_service.create_or_update_ca_chain(
                        namespace=namespace,
                        excluded_tenant=tenant
                    )
            else:
                self.ca_chain_service.create_or_update_ca_chain(namespace=namespace)
                
        except Exception as e:
            self.logger.error(f"Failed to recreate CA chain: {e}")
            raise

# Initialize controller instance
_controller = None

def init_controller(core_v1, custom_objects, cert_svc, ca_chain_svc):
    """Initialize the controller with required services."""
    global _controller
    _controller = TenantController(core_v1, custom_objects, cert_svc, ca_chain_svc)

# Kopf handlers that delegate to controller methods
# Kopf handlers
@kopf.on.create('mtls.invoisight.com', 'v1', 'tenants')
def create_tenant(spec: Dict[str, Any], meta: Dict[str, Any], patch: Dict[str, Any], body: Dict[str, Any], **_):
    """Handler for tenant creation."""
    if _controller is None:
        raise kopf.PermanentError("Controller not initialized")
    return _controller.create_tenant(spec, meta, patch, body)

@kopf.on.delete('mtls.invoisight.com', 'v1', 'tenants')
def delete_tenant(spec: Dict[str, Any], meta: Dict[str, Any], **_):
    """Handler for tenant deletion."""
    if _controller is None:
        raise kopf.PermanentError("Controller not initialized")
    return _controller.delete_tenant(spec, meta)

@kopf.on.field('mtls.invoisight.com', 'v1', 'tenants', field='spec.revoked')
def handle_revocation_request(spec: Dict[str, Any], status: Dict[str, Any], old: bool, new: bool,
                            patch: Dict[str, Any], meta: Dict[str, Any], body: Dict[str, Any], **_):
    """Handler for tenant revocation state changes."""
    if _controller is None:
        raise kopf.PermanentError("Controller not initialized")
    return _controller.handle_revocation_request(spec, status, old, new, patch, meta, body)

@kopf.on.timer('mtls.invoisight.com', 'v1', 'tenants', interval=60.0)
def reconcile_tenant(spec: Dict[str, Any], meta: Dict[str, Any], status: Dict[str, Any], patch: Dict[str, Any], **_):
    """Handler for reconciling failed tenants."""
    if _controller is None:
        raise kopf.PermanentError("Controller not initialized")
    return _controller.reconcile_tenant(spec, meta, status, patch)

@kopf.on.timer('mtls.invoisight.com', 'v1', 'tenants', interval=30.0, initial_delay=10.0)
def check_ca_chain_secret(meta: Dict[str, Any], **_):
    """Handler for periodic CA chain secret checks."""
    if _controller is None:
        raise kopf.PermanentError("Controller not initialized")
    return _controller.check_ca_chain_secret(meta)