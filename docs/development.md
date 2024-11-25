# Development Guide

This guide provides information for developers who want to contribute to or modify the mTLS Certificate Operator.

## Development Environment Setup

### Prerequisites

1. Python 3.9+
2. Docker
3. Kubernetes cluster (minikube, kind, or similar)
4. kubectl
5. cert-manager

### Local Development Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd mtls-cert-operator
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # or `venv\Scripts\activate` on Windows
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Project Structure

```
mtls-cert-operator/
├── config/                         # Kubernetes manifests
│   ├── crd/                       # Custom Resource Definitions
│   ├── dependencies/              # External dependencies
│   ├── manager/                   # Operator deployment
│   ├── rbac/                     # RBAC configurations
│   └── samples/                  # Example resources
├── docs/                         # Documentation
├── src/                         # Source code
│   ├── controllers/             # Kubernetes controllers
│   ├── services/               # Business logic services
│   └── utils/                  # Utility functions
└── test/                       # Tests
    └── e2e/                   # End-to-end tests
```

## Code Organization

### Core Components

1. **Controllers (`src/controllers/`)**
   - Handle Kubernetes resource events
   - Implement reconciliation logic
   - Manage tenant lifecycle

2. **Services (`src/services/`)**
   - `certificate_service.py`: Certificate management
   - `ca_chain_service.py`: CA chain management
   - Pure business logic, no Kubernetes dependencies

3. **Utilities (`src/utils/`)**
   - `kubernetes.py`: Kubernetes helper functions
   - `logging.py`: Logging configuration

## Development Workflow

### Running Locally

1. Start your local Kubernetes cluster:
   ```bash
   minikube start
   ```

2. Install cert-manager:
   ```bash
   kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.5.0/cert-manager.yaml
   ```

3. Apply CRDs:
   ```bash
   kubectl apply -f config/crd/mtls.example.com_tenants.yaml
   ```

4. Run the operator locally:
   ```bash
   kopf run src/main.py --verbose
   ```

### Building and Testing

1. Build the Docker image:
   ```bash
   docker build -t mtls-cert-operator:dev .
   ```

2. Run tests:
   ```bash
   # Run E2E tests
   ./test/e2e/test-mtls.sh

   # Run specific test
   ./test/e2e/test-mtls.sh test
   ```

### Making Changes

1. Create a new branch:
   ```bash
   git checkout -b feature/your-feature
   ```

2. Make your changes
3. Update documentation if needed
4. Test your changes
5. Submit a pull request

## Extending the Operator

### Adding New Features

1. **New CRD Fields**
   - Update `config/crd/mtls.example.com_tenants.yaml`
   - Add corresponding logic in controller

2. **New Controller Functions**
   ```python
   @kopf.on.<event>('mtls.example.com', 'v1', 'tenants')
   def handle_event(spec, meta, status, **kwargs):
       # Your logic here
       pass
   ```

3. **New Services**
   ```python
   class NewService:
       def __init__(self, core_v1_api, custom_objects_api):
           self.core_v1_api = core_v1_api
           self.custom_objects_api = custom_objects_api

       def new_function(self):
           # Your logic here
           pass
   ```

### Best Practices

1. **Error Handling**
   - Use `kopf.PermanentError` for non-recoverable errors
   - Implement proper cleanup in error cases
   - Update status with error information

   ```python
   try:
       # Your logic
   except Exception as e:
       patch.status['state'] = 'Failed'
       patch.status['message'] = str(e)
       raise kopf.PermanentError(str(e))
   ```

2. **Logging**
   - Use the provided logger
   - Include relevant context
   ```python
   logger.info(f"Processing tenant {tenant_name}")
   logger.error(f"Failed to create certificate: {e}")
   ```

3. **Resource Management**
   - Implement proper cleanup
   - Use finalizers when needed
   - Handle resource dependencies

4. **Testing**
   - Add test cases for new features
   - Update E2E tests if needed
   - Test error conditions

## Building and Publishing

### Building the Image

```bash
# Build
docker build -t mtls-cert-operator:latest .

# Tag
docker tag mtls-cert-operator:latest your-registry/mtls-cert-operator:version

# Push
docker push your-registry/mtls-cert-operator:version
```

### Release Process

1. Update version numbers
2. Update CHANGELOG.md
3. Create release tags
4. Build and push Docker image
5. Update deployment manifests

## Debugging

### Common Development Issues

1. **Certificate Issues**
   - Check cert-manager logs
   - Verify CRDs are installed
   - Check certificate status

2. **RBAC Issues**
   - Verify role permissions
   - Check service account
   - Test with cluster-admin role

3. **Controller Issues**
   - Run with `--verbose` flag
   - Check resource status
   - Verify webhook configurations

### Development Tools

1. **Useful kubectl commands**
   ```bash
   # Watch resources
   kubectl get tenants -w

   # Check operator logs
   kubectl logs -l app=tenant-operator -f

   # Describe resources
   kubectl describe tenant example-tenant
   ```

2. **Debugging Tools**
   - `kubectl debug`
   - Python debugger
   - Kopf development mode

## Contributing

1. Fork the repository
2. Create your feature branch
3. Make your changes
4. Add tests for your changes
5. Update documentation
6. Submit a pull request

### Pull Request Process

1. Update README.md with details of changes
2. Update relevant documentation
3. Add tests for new features
4. Ensure all tests pass
5. Get review from maintainers

## Support

For development questions:
1. Check existing issues
2. Create detailed bug reports
3. Include relevant logs and configurations
4. Provide steps to reproduce