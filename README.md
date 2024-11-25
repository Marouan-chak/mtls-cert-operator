# mTLS Certificate Operator

A Kubernetes operator for managing mTLS certificates with automatic client certificate generation and revocation capabilities.

## Features

- Automatic client certificate generation for tenants
- Certificate chain management
- Certificate revocation support
- Integration with cert-manager
- Automatic CA chain updates
- Support for certificate rotation
- Built-in certificate validation

## Prerequisites

- Kubernetes cluster (v1.19+)
- [cert-manager](https://cert-manager.io/docs/installation/) (v1.5+)
- NGINX Ingress Controller with mTLS support
- `kubectl` configured to communicate with your cluster

## Quick Start

1. Install cert-manager:
   ```bash
   kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.5.0/cert-manager.yaml
   ```

2. Deploy the root CA:
   ```bash
   kubectl apply -f config/dependencies/cert-manager/root-ca.yaml
   ```

3. Deploy the operator:
   ```bash
   kubectl apply -f config/samples/operator.yaml
   ```

4. Create a tenant:
   ```bash
   kubectl apply -f config/samples/mtls_v1_tenant.yaml
   ```

## Usage

### Creating a Tenant

```yaml
apiVersion: mtls.invoisight.com/v1
kind: Tenant
metadata:
  name: example-tenant
spec:
  name: example-tenant
  revoked: false
```

### Revoking a Certificate

```bash
kubectl patch tenant example-tenant --type=merge -p '{"spec":{"revoked":true}}'
```

### Testing the Setup

The repository includes a test server and E2E testing script:

```bash
# Deploy test server
kubectl apply -f config/samples/test-server/

# Run E2E tests
./test/e2e/test-mtls.sh
```

## Documentation

- [Installation Guide](docs/installation.md)
- [Usage Guide](docs/usage.md)
- [Development Guide](docs/development.md)

## Architecture

The operator follows a controller pattern and integrates with cert-manager for certificate lifecycle management:

1. `TenantController`: Manages the tenant lifecycle
2. `CertificateService`: Handles certificate operations
3. `CAChainService`: Manages the CA chain
4. Integration with cert-manager for certificate issuance

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a new Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Troubleshooting

See the [usage guide](docs/usage.md) for common issues and solutions.

## Support

For bugs and feature requests, please create an issue on the GitHub repository.