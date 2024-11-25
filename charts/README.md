# mTLS Certificate Operator Helm Chart

This Helm chart installs the mTLS Certificate Operator in your Kubernetes cluster.

## Prerequisites

- Kubernetes 1.19+
- Helm 3.0+
- cert-manager v1.5+

## Installing the Chart

1. Add the Helm repository:
   ```bash
   helm repo add mtls-cert-operator https://yourusername.github.io/mtls-cert-operator
   helm repo update
   ```

2. Install the chart:
   ```bash
   helm install mtls-cert-operator mtls-cert-operator/mtls-cert-operator
   ```

## Configuration

The following table lists the configurable parameters of the chart and their default values:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `image.repository` | Operator image repository | `marouandock/invoisight` |
| `image.tag` | Operator image tag | `operator3` |
| `image.pullPolicy` | Image pull policy | `Always` |
| `imagePullSecrets` | Image pull secrets | `[{name: regcred}]` |
| `replicaCount` | Number of operator replicas | `1` |
| `resources` | CPU/Memory resource requests/limits | See `values.yaml` |
| `nodeSelector` | Node selector labels | `{}` |
| `tolerations` | Node tolerations | `[]` |
| `affinity` | Node affinity | `{}` |
| `serviceAccount.create` | Create service account | `true` |
| `serviceAccount.name` | Service account name | `tenant-operator` |
| `rbac.create` | Create RBAC resources | `true` |
| `rootCA.create` | Create root CA | `true` |
| `rootCA.commonName` | Root CA common name | `root-ca` |
| `operator.logLevel` | Operator log level | `INFO` |
| `testServer.enabled` | Deploy test server | `false` |

## Examples

### Basic Installation
```bash
helm install mtls-cert-operator mtls-cert-operator/mtls-cert-operator
```

### Custom Configuration
```bash
helm install mtls-cert-operator mtls-cert-operator/mtls-cert-operator \
  --set image.tag=latest \
  --set resources.requests.memory=256Mi \
  --set operator.logLevel=DEBUG
```

### With Test Server
```bash
helm install mtls-cert-operator mtls-cert-operator/mtls-cert-operator \
  --set testServer.enabled=true \
  --set testServer.ingress.hostname=myserver.example.com
```

## Testing

Run the helm test:
```bash
helm test mtls-cert-operator
```

## Uninstalling

```bash
helm uninstall mtls-cert-operator
```

## Development

1. Clone the repository
2. Make changes to the templates
3. Package the chart:
   ```bash
   helm package .
   ```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request