# main.py
import kopf
import logging
from config import Config
from controllers import tenant_controller
from services.certificate_service import CertificateService
from services.ca_chain_service import CAChainService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s [%(levelname)s] %(message)s',
)
logger = logging.getLogger('tenant-operator')

@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    """Configure the operator."""
    # Initialize Kubernetes clients
    clients = Config.initialize_kubernetes()
    
    # Initialize services
    cert_service = CertificateService(
        clients['core_v1_api'],
        clients['custom_objects_api']
    )
    ca_chain_service = CAChainService(
        clients['core_v1_api'],
        clients['custom_objects_api']
    )
    
    # Initialize controller with services
    tenant_controller.init_controller(
        clients['core_v1_api'],
        clients['custom_objects_api'],
        cert_service,
        ca_chain_service
    )
    
    # Configure operator settings
    settings.posting.enabled = True
    settings.watching.server_timeout = 60
    settings.persistence.finalizer = 'mtls-operator/finalizer'
    settings.watching.namespace = 'default'

if __name__ == "__main__":
    kopf.run()