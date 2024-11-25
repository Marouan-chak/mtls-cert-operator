# Usage Guide

This guide explains how to use the mTLS Certificate Operator to manage tenant certificates and implement mTLS authentication in your applications.

## Table of Contents

1. [Managing Tenants](#managing-tenants)
2. [Certificate Management](#certificate-management)
3. [Implementing mTLS Authentication](#implementing-mtls-authentication)
4. [Testing and Verification](#testing-and-verification)
5. [Troubleshooting](#troubleshooting)

## Managing Tenants

### Creating a Tenant

Create a tenant by applying a Tenant custom resource:

```yaml
apiVersion: mtls.invoisight.com/v1
kind: Tenant
metadata:
  name: example-tenant
spec:
  name: example-tenant
  revoked: false
```

This will automatically:
1. Generate an intermediate CA certificate
2. Create a client certificate
3. Update the CA chain

### Tenant Lifecycle Management

#### Revoking a Tenant

To revoke a tenant's certificates:

```bash
kubectl patch tenant example-tenant --type=merge -p '{"spec":{"revoked":true}}'
```

#### Unrevoking a Tenant

To unrevoke a previously revoked tenant:

```bash
kubectl patch tenant example-tenant --type=merge -p '{"spec":{"revoked":false}}'
```

#### Deleting a Tenant

```bash
kubectl delete tenant example-tenant
```

### Monitoring Tenant Status

View tenant status:
```bash
kubectl get tenants

# Detailed view
kubectl describe tenant example-tenant
```

Status fields:
- `state`: Current state (Creating, Active, Revoked, Failed)
- `isRevoked`: Revocation status
- `message`: Additional status information

## Certificate Management

### Certificate Locations

Certificates are stored in Kubernetes secrets:

- Intermediate CA: `<tenant-name>-intermediate-ca-secret`
- Client Certificate: `<tenant-name>-client-cert-secret`
- CA Chain: `ca-chain-secret`

### Extracting Certificates

Extract client certificates:

```bash
# Extract client certificate
kubectl get secret example-tenant-client-cert-secret -o jsonpath='{.data.tls\.crt}' | base64 -d > client.crt
kubectl get secret example-tenant-client-cert-secret -o jsonpath='{.data.tls\.key}' | base64 -d > client.key

# Extract CA chain
kubectl get secret ca-chain-secret -o jsonpath='{.data.ca\.crt}' | base64 -d > ca-chain.crt
```

### Certificate Validation

Verify a certificate against the CA chain:

```bash
openssl verify -CAfile ca-chain.crt client.crt
```

## Implementing mTLS Authentication

### NGINX Ingress Configuration

Example NGINX ingress configuration with mTLS:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  annotations:
    nginx.ingress.kubernetes.io/auth-tls-secret: "default/ca-chain-secret"
    nginx.ingress.kubernetes.io/auth-tls-verify-client: "on"
    nginx.ingress.kubernetes.io/auth-tls-verify-depth: "3"
    nginx.ingress.kubernetes.io/auth-tls-set-header: "True"
    nginx.ingress.kubernetes.io/configuration-snippet: |
      proxy_set_header X-Org-Id $ssl_client_s_dn_cn;
spec:
  # ... rest of ingress configuration
```

### Example Client Usage

Using curl:
```bash
curl --cert client.crt \
     --key client.key \
     --cacert ca-chain.crt \
     https://your-service.example.com
```

Using Python requests:
```python
import requests

response = requests.get(
    'https://your-service.example.com',
    cert=('client.crt', 'client.key'),
    verify='ca-chain.crt'
)
```

## Testing and Verification

### Using the Test Script

The repository includes a comprehensive test script:

```bash
./test/e2e/test-mtls.sh
```

Available commands:
```bash
./test/e2e/test-mtls.sh create    # Create test tenants
./test/e2e/test-mtls.sh extract   # Extract certificates
./test/e2e/test-mtls.sh test      # Test tenant access
./test/e2e/test-mtls.sh setup     # Full setup
```

### Manual Testing

1. Deploy the test server:
   ```bash
   kubectl apply -f config/samples/test-server/
   ```

2. Create a tenant and test:
   ```bash
   # Create tenant
   kubectl apply -f config/samples/mtls_v1_tenant.yaml

   # Extract certificates
   kubectl get secret tenant1-client-cert-secret -o jsonpath='{.data.tls\.crt}' | base64 -d > client.crt
   kubectl get secret tenant1-client-cert-secret -o jsonpath='{.data.tls\.key}' | base64 -d > client.key
   kubectl get secret ca-chain-secret -o jsonpath='{.data.ca\.crt}' | base64 -d > ca-chain.crt

   # Test
   curl --cert client.crt --key client.key --cacert ca-chain.crt https://myserver.invoisight.com
   ```

## Troubleshooting

### Common Issues

1. Certificate Not Being Issued
   - Check cert-manager logs
   - Verify root CA exists and is ready
   - Check tenant status

2. mTLS Authentication Failures
   - Verify CA chain is up to date
   - Check certificate revocation status
   - Verify ingress configuration

3. Client Connection Issues
   - Verify certificate paths
   - Check certificate permissions
   - Validate CA chain

### Debugging Steps

1. Check operator logs:
   ```bash
   kubectl logs -l app=tenant-operator
   ```

2. Check tenant status:
   ```bash
   kubectl describe tenant <tenant-name>
   ```

3. Verify certificate chain:
   ```bash
   openssl verify -CAfile ca-chain.crt client.crt
   ```

4. Check certificate details:
   ```bash
   openssl x509 -in client.crt -text -noout
   ```

### Getting Support

If you encounter issues:
1. Check this documentation for similar issues
2. Review operator logs
3. Submit an issue on GitHub with:
   - Description of the problem
   - Relevant logs
   - Steps to reproduce
   - Environment details