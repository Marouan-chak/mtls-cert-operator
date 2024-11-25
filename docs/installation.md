# Installation Guide

This guide provides detailed instructions for installing the mTLS Certificate Operator in your Kubernetes cluster.

## Prerequisites

Before installing the operator, ensure your environment meets the following requirements:

### Required Software

- Kubernetes cluster (v1.19+)
- kubectl (v1.19+)
- cert-manager (v1.5+)
- NGINX Ingress Controller

### Resource Requirements

The operator requires minimal resources:
- CPU: 250m (request), 500m (limit)
- Memory: 128Mi (request), 256Mi (limit)

## Installation Steps

### 1. Install cert-manager

First, install cert-manager in your cluster:

```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.5.0/cert-manager.yaml

# Wait for cert-manager to be ready
kubectl wait --for=condition=Ready pods -l app=cert-manager -n cert-manager
```

### 2. Deploy the Root CA

Deploy the root CA and cluster issuer:

```bash
kubectl apply -f config/dependencies/cert-manager/root-ca.yaml

# Wait for the root CA to be ready
kubectl wait --for=condition=Ready certificate root-ca-cert -n default
```

### 3. Create RBAC Resources

Deploy the necessary RBAC resources:

```bash
kubectl apply -f config/rbac/service_account.yaml
kubectl apply -f config/rbac/role.yaml
kubectl apply -f config/rbac/role_binding.yaml
```

### 4. Deploy the Operator

Deploy the operator:

```bash
kubectl apply -f config/samples/operator.yaml
```

Verify the operator is running:

```bash
kubectl get pods -l app=tenant-operator
```

## Configuration

### Operator Configuration

The operator supports the following configuration options through environment variables:

- `LOG_LEVEL`: Logging level (default: INFO)
- `WATCH_NAMESPACE`: Namespace to watch (default: all namespaces)
- `CERT_VALIDITY_DAYS`: Certificate validity period in days (default: 365)

### Docker Registry Credentials

If you're using a private registry:

1. Create a secret with your registry credentials:
   ```bash
   kubectl create secret docker-registry regcred \
     --docker-server=<your-registry-server> \
     --docker-username=<your-username> \
     --docker-password=<your-password> \
     --docker-email=<your-email>
   ```

2. Reference it in your operator deployment:
   ```yaml
   imagePullSecrets:
     - name: regcred
   ```

## Verifying the Installation

1. Check operator status:
   ```bash
   kubectl get pods -l app=tenant-operator
   ```

2. Check operator logs:
   ```bash
   kubectl logs -l app=tenant-operator
   ```

3. Create a test tenant:
   ```bash
   kubectl apply -f config/samples/mtls_v1_tenant.yaml
   ```

4. Verify tenant creation:
   ```bash
   kubectl get tenants
   ```

## Optional Components

### Test Server

To deploy the test server for verifying mTLS functionality:

```bash
kubectl apply -f config/samples/test-server/
```

## Upgrading

To upgrade the operator to a new version:

```bash
kubectl set image deployment/tenant-operator operator=marouandock/invoisight:operator3-new
```

## Uninstallation

To remove the operator and its resources:

```bash
# Remove tenants
kubectl delete tenants --all

# Remove operator
kubectl delete -f config/samples/operator.yaml

# Remove RBAC
kubectl delete -f config/rbac/
```

## Troubleshooting

### Common Issues

1. Operator pod not starting:
   - Check pod logs: `kubectl logs -l app=tenant-operator`
   - Verify RBAC: `kubectl auth can-i`
   - Check registry credentials

2. Certificate not being issued:
   - Check cert-manager logs
   - Verify root CA status
   - Check tenant status

### Getting Help

If you encounter any issues:
1. Check the operator logs
2. Review the troubleshooting guide in the usage documentation
3. Submit an issue on GitHub with relevant logs and details