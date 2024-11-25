from kubernetes.client import V1Secret, V1ObjectMeta
from kubernetes.client.rest import ApiException
import base64
import kopf
from utils.logging import setup_logger

logger = setup_logger('ca-chain-service')

class CAChainService:
    def __init__(self, core_v1_api, custom_objects_api):
        self.core_v1_api = core_v1_api
        self.custom_objects_api = custom_objects_api

    def create_or_update_ca_chain(self, namespace, excluded_tenant=None, force_include=None):
        """Update the CA chain secret."""
        try:
            # Get root CA
            root_ca_secret = self.core_v1_api.read_namespaced_secret('root-ca-secret', namespace)
            if not root_ca_secret.data or 'tls.crt' not in root_ca_secret.data:
                raise kopf.PermanentError(f"Root CA secret is missing in namespace {namespace}")
            root_ca = base64.b64decode(root_ca_secret.data['tls.crt'])
            
            # Start chain with root CA
            chain = [root_ca]
            
            # List all tenants
            tenants = self.custom_objects_api.list_namespaced_custom_object(
                'mtls.invoisight.com', 'v1', namespace, 'tenants'
            )
            
            # Add intermediate CAs
            for tenant in tenants['items']:
                tenant_name = tenant['spec']['name']
                tenant_status = tenant.get('status', {})
                
                if excluded_tenant and tenant_name == excluded_tenant:
                    continue
                if tenant_status.get('isRevoked', False) and tenant_name != force_include:
                    continue
                    
                secret_name = f"{tenant_name}-intermediate-ca-secret"
                try:
                    secret = self.core_v1_api.read_namespaced_secret(secret_name, namespace)
                    if secret.data and 'tls.crt' in secret.data:
                        chain.append(base64.b64decode(secret.data['tls.crt']))
                except ApiException as e:
                    if e.status != 404:
                        logger.error(f"Failed to get CA for {tenant_name}: {e}")

            # Update chain secret
            combined_chain = b'\n'.join(filter(None, chain))
            secret = V1Secret(
                metadata=V1ObjectMeta(name='ca-chain-secret'),
                data={'ca.crt': base64.b64encode(combined_chain).decode('utf-8')}
            )
            
            try:
                self.core_v1_api.replace_namespaced_secret('ca-chain-secret', namespace, secret)
            except ApiException as e:
                if e.status == 404:
                    self.core_v1_api.create_namespaced_secret(namespace, secret)
                    
        except Exception as e:
            raise kopf.PermanentError(f"Failed to update CA chain: {str(e)}")
