# main.py
import kopf
import logging
from config import Config
from controllers import tenant_controller
from services.certificate_service import CertificateService
from services.ca_chain_service import CAChainService
from utils.log_config import configure_logging

# Configure logging
configure_logging()
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
    settings.watching.server_timeout = 60
    settings.persistence.finalizer = 'mtls-operator/finalizer'
    
    # Reduce logging noise
    settings.posting.level = logging.INFO # Only log warnings and errors for events
    
    # Configure which handlers should log
    settings.watching.debug = False
    settings.posting.debug = False
    
    # Disable success logging for specific activities
    settings.persistence.progress_storage.success = False  # Don't store success progress
    settings.persistence.diffbase_storage.success = False  # Don't store success diffs
    
    # Configure logging levels for different components
    logging.getLogger('kopf.objects').setLevel(logging.WARNING)        # Suppress regular object handling logs
    logging.getLogger('kopf.activities').setLevel(logging.INFO)        # Keep important activity logs
    logging.getLogger('kopf.activities.service').setLevel(logging.WARNING)  # Suppress service logs
    logging.getLogger('kopf.activities.authenticator').setLevel(logging.WARNING)  # Suppress auth logs

if __name__ == "__main__":
    kopf.run()