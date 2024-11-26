import kopf
import logging
from config import Config
from controllers import tenant_controller
from services.certificate_service import CertificateService
from services.ca_chain_service import CAChainService
from utils.log_config import configure_logging
from typing import Dict, Any

class MTLSOperator:
    def __init__(self):
        self.logger = logging.getLogger('tenant-operator')
        self.clients = None
        self.cert_service = None
        self.ca_chain_service = None

    def initialize(self) -> None:
        """Initialize operator dependencies."""
        configure_logging()
        self.clients = Config.initialize_kubernetes()
        self._initialize_services()
        self._initialize_controller()

    def _initialize_services(self) -> None:
        """Initialize operator services."""
        self.cert_service = CertificateService(
            self.clients['core_v1_api'],
            self.clients['custom_objects_api']
        )
        self.ca_chain_service = CAChainService(
            self.clients['core_v1_api'],
            self.clients['custom_objects_api']
        )

    def _initialize_controller(self) -> None:
        """Initialize tenant controller with services."""
        tenant_controller.init_controller(
            self.clients['core_v1_api'],
            self.clients['custom_objects_api'],
            self.cert_service,
            self.ca_chain_service
        )

    def configure_settings(self, settings: kopf.OperatorSettings) -> None:
        """Configure operator settings."""
        settings.watching.server_timeout = 60
        settings.persistence.finalizer = 'mtls-operator/finalizer'
        settings.posting.level = logging.INFO
        settings.posting.enabled = True
        settings.posting.events = True
        settings.posting.success_events = True
        settings.posting.failure_events = True
        
        self._configure_logging_levels()

    def _configure_logging_levels(self) -> None:
        """Configure logging levels for different components."""
        logging_config = {
            'kopf.objects': logging.WARNING,
            'kopf.activities': logging.INFO,
            'kopf.activities.service': logging.WARNING,
            'kopf.activities.authenticator': logging.WARNING
        }
        
        for logger_name, level in logging_config.items():
            logging.getLogger(logger_name).setLevel(level)

@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    """Configure the operator on startup."""
    operator = MTLSOperator()
    operator.initialize()
    operator.configure_settings(settings)

if __name__ == "__main__":
    kopf.run()
