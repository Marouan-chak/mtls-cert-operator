import kopf
from kubernetes.client.rest import ApiException
import time

def wait_for_secret(core_v1_api, name: str, namespace: str, timeout: int = 60):
    """Wait for a secret to be ready."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            secret = core_v1_api.read_namespaced_secret(name, namespace)
            if secret.data and 'tls.crt' in secret.data:
                return True
        except ApiException:
            pass
        time.sleep(2)
    raise kopf.PermanentError(f"Timeout waiting for secret {name}")
