import kopf
from kubernetes.client.rest import ApiException
import time
from typing import Optional

class KubernetesUtils:
    @staticmethod
    def wait_for_secret(
        core_v1_api,
        name: str,
        namespace: str,
        timeout: int = 60,
        check_interval: int = 2
    ) -> bool:
        """Wait for a secret to be ready with the specified certificate."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                secret = core_v1_api.read_namespaced_secret(name, namespace)
                if secret.data and 'tls.crt' in secret.data:
                    return True
            except ApiException:
                pass
            time.sleep(check_interval)
        raise kopf.PermanentError(f"Timeout waiting for secret {name}")
