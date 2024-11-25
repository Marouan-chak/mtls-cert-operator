# controllers/tenant_controller.py
import kopf
from kubernetes.client.rest import ApiException
from utils.logging import setup_logger
from utils.kubernetes import wait_for_secret
from config import Config

logger = setup_logger('tenant-controller')

# Global service instances to be set by initialization
core_v1_api = None
custom_objects_api = None
cert_service = None
ca_chain_service = None

def init_controller(core_v1, custom_objects, cert_svc, ca_chain_svc):
    """Initialize the controller with required services."""
    global core_v1_api, custom_objects_api, cert_service, ca_chain_service
    core_v1_api = core_v1
    custom_objects_api = custom_objects
    cert_service = cert_svc
    ca_chain_service = ca_chain_svc

@kopf.on.create('mtls.invoisight.com', 'v1', 'tenants')
def create_tenant(spec, meta, patch, **kwargs):
    """Handle tenant creation."""
    try:
        tenant_name = spec['name']
        namespace = meta['namespace']
        logger.info(f"Creating tenant {tenant_name}")
        
        # Set initial state
        patch.status['state'] = 'Creating'
        initially_revoked = spec.get('revoked', False)
        
        # Create intermediate CA certificate
        intermediate_ca_name = f"{tenant_name}-intermediate-ca"
        cert_service.create_certificate(
            name=intermediate_ca_name,
            namespace=namespace,
            isCA=True,
            commonName=f"{tenant_name}-intermediate-ca",
            secretName=f"{intermediate_ca_name}-secret",
            privateKey={'algorithm': 'RSA', 'size': 4096},
            issuerRef={
                'name': 'root-ca-issuer',
                'kind': 'ClusterIssuer',
                'group': 'cert-manager.io'
            },
            usages=['digital signature', 'key encipherment', 'cert sign']
        )
        
        wait_for_secret(core_v1_api, f"{intermediate_ca_name}-secret", namespace)
        
        # Create issuer
        cert_service.create_issuer(
            name=intermediate_ca_name,
            namespace=namespace,
            secret_name=f"{intermediate_ca_name}-secret"
        )
        
        # Create client certificate
        client_cert_name = f"{tenant_name}-client-cert"
        cert_service.create_certificate(
            name=client_cert_name,
            namespace=namespace,
            commonName=tenant_name,
            secretName=f"{client_cert_name}-secret",
            privateKey={'algorithm': 'RSA', 'size': 2048},
            issuerRef={
                'name': intermediate_ca_name,
                'kind': 'Issuer',
                'group': 'cert-manager.io'
            },
            usages=['digital signature', 'key encipherment', 'client auth']
        )
        
        wait_for_secret(core_v1_api, f"{client_cert_name}-secret", namespace)
        
        # Update status
        patch.status.update({
            'intermediateCA': intermediate_ca_name,
            'clientCert': client_cert_name,
            'isRevoked': initially_revoked,
            'state': 'Revoked' if initially_revoked else 'Active'
        })
        
        # Ensure we wait for the intermediate CA secret before updating the chain
        wait_for_secret(core_v1_api, f"{intermediate_ca_name}-secret", namespace)
        
        # Update CA chain
        ca_chain_service.create_or_update_ca_chain(
            excluded_tenant=tenant_name if initially_revoked else None
        )
        
    except Exception as e:
        patch.status['state'] = 'Failed'
        patch.status['message'] = str(e)
        raise kopf.PermanentError(str(e))

@kopf.on.delete('mtls.invoisight.com', 'v1', 'tenants')
def delete_tenant(spec, meta, **kwargs):
    """Handle tenant deletion."""
    tenant_name = spec['name']
    namespace = meta['namespace']
    logger.info(f"Deleting tenant {tenant_name}")
    
    # Update CA chain
    ca_chain_service.create_or_update_ca_chain(excluded_tenant=tenant_name)
    
    # Delete resources
    resources = [
        ('certificates', f"{tenant_name}-intermediate-ca"),
        ('certificates', f"{tenant_name}-client-cert"),
        ('issuers', f"{tenant_name}-intermediate-ca"),
        ('secrets', f"{tenant_name}-intermediate-ca-secret"),
        ('secrets', f"{tenant_name}-client-cert-secret")
    ]
    
    for resource_type, name in resources:
        try:
            if resource_type == 'secrets':
                core_v1_api.delete_namespaced_secret(name, namespace)
            else:
                custom_objects_api.delete_namespaced_custom_object(
                    Config.CERT_MANAGER_GROUP, Config.CERT_MANAGER_VERSION,
                    namespace, resource_type, name
                )
        except ApiException as e:
            if e.status != 404:  # Ignore if already deleted
                logger.error(f"Failed to delete {resource_type} {name}: {e}")

@kopf.on.field('mtls.invoisight.com', 'v1', 'tenants', field='spec.revoked')
def handle_revocation_request(spec, status, old, new, patch, **kwargs):
    """Handle tenant revocation requests."""
    tenant_name = spec['name']
    
    if new and not old:  # Revoking
        logger.info(f"Revoking tenant {tenant_name}")
        ca_chain_service.create_or_update_ca_chain(excluded_tenant=tenant_name)
        patch.status.update({
            'isRevoked': True,
            'state': 'Revoked'
        })
    elif old and not new:  # Unrevoking
        if status.get('isRevoked', False):
            logger.info(f"Unrevoking tenant {tenant_name}")
            ca_chain_service.create_or_update_ca_chain(force_include=tenant_name)
            patch.status.update({
                'isRevoked': False,
                'state': 'Active'
            })

@kopf.on.timer('mtls.invoisight.com', 'v1', 'tenants', interval=60.0)
def reconcile_tenant(spec, meta, status, patch, **kwargs):
    """Reconcile failed tenants."""
    if status.get('state') != 'Failed':
        return
        
    tenant_name = spec['name']
    logger.info(f"Reconciling failed tenant {tenant_name}")
    
    try:
        # Check if resources already exist
        namespace = meta['namespace']
        intermediate_ca_name = f"{tenant_name}-intermediate-ca"
        client_cert_name = f"{tenant_name}-client-cert"
        
        # Create or update intermediate CA certificate
        cert_service.create_certificate(
            name=intermediate_ca_name,
            namespace=namespace,
            isCA=True,
            commonName=f"{tenant_name}-intermediate-ca",
            secretName=f"{intermediate_ca_name}-secret",
            privateKey={'algorithm': 'RSA', 'size': 4096},
            issuerRef={
                'name': 'root-ca-issuer',
                'kind': 'ClusterIssuer',
                'group': 'cert-manager.io'
            },
            usages=['digital signature', 'key encipherment', 'cert sign']
        )
        
        wait_for_secret(core_v1_api, f"{intermediate_ca_name}-secret", namespace)
        
        # Create or update issuer
        cert_service.create_issuer(
            name=intermediate_ca_name,
            namespace=namespace,
            secret_name=f"{intermediate_ca_name}-secret"
        )
        
        # Create or update client certificate
        cert_service.create_certificate(
            name=client_cert_name,
            namespace=namespace,
            commonName=tenant_name,
            secretName=f"{client_cert_name}-secret",
            privateKey={'algorithm': 'RSA', 'size': 2048},
            issuerRef={
                'name': intermediate_ca_name,
                'kind': 'Issuer',
                'group': 'cert-manager.io'
            },
            usages=['digital signature', 'key encipherment', 'client auth']
        )
        
        wait_for_secret(core_v1_api, f"{client_cert_name}-secret", namespace)
        
        # Update status
        patch.status.update({
            'intermediateCA': intermediate_ca_name,
            'clientCert': client_cert_name,
            'isRevoked': spec.get('revoked', False),
            'state': 'Active',
            'message': 'Reconciliation successful'
        })
        
    except Exception as e:
        logger.error(f"Reconciliation failed for {tenant_name}: {e}")
        patch.status['message'] = f"Reconciliation failed: {str(e)}"