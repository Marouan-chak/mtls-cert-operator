#!/bin/bash

set -euo pipefail  # Exit on error, undefined vars, and pipe failures

# Colors for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# Configuration
readonly NAMESPACE="monitoring"
readonly SERVER_URL="loki.gitops-test-ch-3.test.instadeep.net"
readonly CERTS_DIR="certs"
readonly MAX_RETRIES=30
readonly RETRY_INTERVAL=2

# Logging functions
log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $*" >&2; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# Check if required tools are installed
check_prerequisites() {
    local missing_tools=()
    
    for tool in kubectl curl openssl base64; do
        if ! command -v "$tool" &> /dev/null; then
            missing_tools+=("$tool")
        fi
    done
    
    if [[ ${#missing_tools[@]} -ne 0 ]]; then
        log_error "Missing required tools: ${missing_tools[*]}"
        log_error "Please install these tools and try again"
        exit 1
    fi

    # Check if kubectl can connect to the cluster
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster. Please check your kubeconfig"
        exit 1
    fi
}

# Wait for a condition with timeout
wait_for_condition() {
    local description=$1
    local condition=$2
    local retries=0
    
    log_info "Waiting for $description..."
    while ! eval "$condition" && [[ $retries -lt $MAX_RETRIES ]]; do
        echo -n "."
        sleep $RETRY_INTERVAL
        ((retries++))
    done
    echo
    
    if [[ $retries -eq $MAX_RETRIES ]]; then
        log_error "Timeout waiting for $description"
        return 1
    fi
    
    return 0
}

# Function to create tenants
create_tenants() {
    local tenant_count=${1:-3}  # Default to 3 tenants if not specified
    
    log_info "Creating $tenant_count tenants..."
    for i in $(seq 1 "$tenant_count"); do
        log_info "Creating tenant${i}..."
        kubectl apply -f - <<EOF
apiVersion: mtls.invoisight.com/v1
kind: Tenant
metadata:
  name: tenant$i
  namespace: $NAMESPACE
spec:
  name: tenant$i
  revoked: false
EOF
        
        # Wait for cert secret
        if ! wait_for_condition \
            "tenant${i} certificates" \
            "kubectl get secret tenant${i}-client-cert-secret -n $NAMESPACE &>/dev/null"; then
            log_error "Failed to create tenant${i}"
            return 1
        fi
        log_success "tenant${i} created successfully"
    done
}

# Function to extract certificates
extract_certs() {
    local tenant_name="$1"
    
    log_info "Extracting certificates..."
    mkdir -p "$CERTS_DIR"
    
    # Extract CA chain for verification
    log_info "Extracting CA chain..."
    if ! kubectl get secret ca-chain-secret -n "$NAMESPACE" -o jsonpath='{.data.ca\.crt}' | \
         base64 -d > "$CERTS_DIR/ca-chain.crt"; then
        log_error "Failed to extract CA chain"
        return 1
    fi
    
    if [[ -n "$tenant_name" ]]; then
        # Extract specific tenant
        log_info "Extracting certificates for ${tenant_name}..."
        
        # Extract cert and key
        if ! kubectl get secret "${tenant_name}-client-cert-secret" -n "$NAMESPACE" \
             -o jsonpath='{.data.tls\.crt}' | base64 -d > "$CERTS_DIR/${tenant_name}.crt" || \
           ! kubectl get secret "${tenant_name}-client-cert-secret" -n "$NAMESPACE" \
             -o jsonpath='{.data.tls\.key}' | base64 -d > "$CERTS_DIR/${tenant_name}.key"; then
            log_error "Failed to extract certificates for ${tenant_name}"
            return 1
        fi
        
        # Set proper permissions
        chmod 600 "$CERTS_DIR/${tenant_name}."{crt,key}
        log_success "Extracted certificates for ${tenant_name}"
    else
        # Extract all tenants
        tenant_list=$(kubectl get tenants -n "$NAMESPACE" --no-headers -o custom-columns=NAME:.spec.name)
        
        for tenant in $tenant_list; do
            log_info "Extracting certificates for ${tenant}..."
            
            # Extract cert and key
            if ! kubectl get secret "${tenant}-client-cert-secret" -n "$NAMESPACE" \
                 -o jsonpath='{.data.tls\.crt}' | base64 -d > "$CERTS_DIR/${tenant}.crt" || \
               ! kubectl get secret "${tenant}-client-cert-secret" -n "$NAMESPACE" \
                 -o jsonpath='{.data.tls\.key}' | base64 -d > "$CERTS_DIR/${tenant}.key"; then
                log_error "Failed to extract certificates for ${tenant}"
                return 1
            fi
            
            # Set proper permissions
            chmod 600 "$CERTS_DIR/${tenant}."{crt,key}
            log_success "Extracted certificates for ${tenant}"
        done
    fi
    
    log_success "All certificates extracted to ./$CERTS_DIR directory"
}

# Function to test tenants
test_tenants() {
    local tenant_name="$1"  # Optional specific tenant name
    
    echo -e "\n${YELLOW}Testing tenant access...${NC}"
    
    if [[ -n "$tenant_name" ]]; then
        # Test specific tenant
        echo -e "\n${YELLOW}Testing ${tenant_name}...${NC}"
        if [[ ! -f "$CERTS_DIR/${tenant_name}.crt" ]]; then
            log_error "Certificates for ${tenant_name} not found. Run extract first."
            return 1
        fi
        
        response=$(curl -s -w "\n%{http_code}" --cert "$CERTS_DIR/${tenant_name}.crt" \
                        --key "$CERTS_DIR/${tenant_name}.key" \
                        --cacert "$CERTS_DIR/ca-chain.crt" \
                        "https://$SERVER_URL") || true
        
        # Get status code (last line) and response body (everything else)
        status_code=$(echo "$response" | tail -n1)
        response_body=$(echo "$response" | sed '$d')
        
        if [[ "$status_code" =~ ^2[0-9][0-9]$ ]]; then
            echo -e "${GREEN}✓ ${tenant_name} authentication successful${NC}"
        else
            echo -e "${RED}✗ ${tenant_name} authentication failed${NC}"
            echo "Status code: $status_code"
            echo "Response: $response_body"
        fi
    else
        # Test all tenants
        tenant_list=$(kubectl get tenants -n "$NAMESPACE" --no-headers -o custom-columns=NAME:.spec.name)
        
        for tenant in $tenant_list; do
            echo -e "\n${YELLOW}Testing ${tenant}...${NC}"
            if [[ ! -f "$CERTS_DIR/${tenant}.crt" ]]; then
                log_warning "Certificates for ${tenant} not found. Skipping."
                continue
            fi
            
            response=$(curl -s -w "\n%{http_code}" --cert "$CERTS_DIR/${tenant}.crt" \
                            --key "$CERTS_DIR/${tenant}.key" \
                            --cacert "$CERTS_DIR/ca-chain.crt" \
                            "https://$SERVER_URL") || true
            
            # Get status code (last line) and response body (everything else)
            status_code=$(echo "$response" | tail -n1)
            response_body=$(echo "$response" | sed '$d')
            
            if [[ "$status_code" =~ ^2[0-9][0-9]$ ]]; then
                echo -e "${GREEN}✓ ${tenant} authentication successful${NC}"
            else
                echo -e "${RED}✗ ${tenant} authentication failed${NC}"
                echo "Status code: $status_code"
                echo "Response: $response_body"
            fi
        done
    fi
    
    # Don't return any error code to prevent script exit
    return 0
}

# Function to manage tenant state
manage_tenant_state() {
    local tenant_name=$1
    local action=$2
    local expected_state=$3
    
    # Validate tenant name
    if [[ -z "$tenant_name" ]]; then
        log_error "Tenant name cannot be empty"
        return 1
    fi
    
    # Check if tenant exists
    if ! kubectl get tenant "$tenant_name" -n "$NAMESPACE" &>/dev/null; then
        log_error "Tenant $tenant_name does not exist"
        return 1
    fi
    
    log_info "${action^}ing $tenant_name..."
    
    local patch_value
    if [[ $action == "revoke" ]]; then
        patch_value="true"
    else
        patch_value="false"
    fi
    
    if ! kubectl patch tenant "$tenant_name" -n "$NAMESPACE" \
         --type=merge -p "{\"spec\":{\"revoked\":$patch_value}}"; then
        log_error "Failed to $action $tenant_name"
        return 1
    fi
    
    # Wait for state change
    if ! wait_for_condition \
        "$action of $tenant_name" \
        "kubectl get tenant $tenant_name -n $NAMESPACE -o jsonpath='{.status.state}' | grep -q '$expected_state'"; then
        log_error "Failed to $action $tenant_name"
        return 1
    fi
    
    log_success "$tenant_name successfully ${action}d"
}

# Wrapper functions for tenant management
revoke_tenant() { manage_tenant_state "$1" "revoke" "Revoked"; }
unrevoke_tenant() { manage_tenant_state "$1" "unrevoke" "Active"; }

# Function to delete a tenant
delete_tenant() {
    local tenant_name=$1
    
    # Validate tenant name
    if [[ -z "$tenant_name" ]]; then
        log_error "Tenant name cannot be empty"
        return 1
    fi
    
    log_info "Deleting $tenant_name..."
    
    if ! kubectl delete tenant "$tenant_name" -n "$NAMESPACE" &>/dev/null; then
        log_error "Failed to delete $tenant_name"
        return 1
    fi
    
    # Wait for resources to be deleted
    if ! wait_for_condition \
        "$tenant_name deletion" \
        "! kubectl get secret ${tenant_name}-client-cert-secret -n $NAMESPACE &>/dev/null"; then
        log_error "Failed to delete $tenant_name resources"
        return 1
    fi
    
    log_success "$tenant_name and associated resources deleted"
}

# Function to show tenant status
show_status() {
    log_info "Current tenant status:"
    kubectl get tenants -n "$NAMESPACE" \
        -o custom-columns=NAME:.metadata.name,STATE:.status.state,REVOKED:.status.isRevoked,MESSAGE:.status.message
}

# Function to check CA chain
check_ca_chain() {
    log_info "Checking CA chain:"
    if ! kubectl get secret ca-chain-secret -n "$NAMESPACE" -o jsonpath='{.data.ca\.crt}' | \
         base64 -d | openssl crl2pkcs7 -nocrl -certfile /dev/stdin | \
         openssl pkcs7 -print_certs -noout; then
        log_error "Failed to check CA chain"
        return 1
    fi
}

# Function to cleanup
cleanup() {
    log_info "Cleaning up resources..."
    rm -rf "$CERTS_DIR"
    log_success "Cleanup complete"
}

# Show help
show_help() {
    cat << EOF
mTLS Tenant Management Tool

Usage:
  $0 [command]

Available Commands:
  create    Create test tenants
  extract   Extract certificates (usage: extract [tenant_name])
  test      Test tenant access (usage: test [tenant_name])
  revoke    Revoke a tenant
  unrevoke  Unrevoke a tenant
  delete    Delete a tenant
  status    Show tenant status
  ca-chain  Check CA chain
  setup     Full setup (create, extract, test)
  cleanup   Clean up resources
  help      Show this help message

Use "$0 help" for more information about a command.
EOF
}

# Main menu
show_menu() {
    echo -e "\n${YELLOW}mTLS Tenant Management${NC}"
    echo "1. Create all tenants"
    echo "2. Extract certificates"
    echo "3. Test all tenants"
    echo "4. Revoke a tenant"
    echo "5. Unrevoke a tenant"
    echo "6. Delete a tenant"
    echo "7. Show tenant status"
    echo "8. Check CA chain"
    echo "9. Full setup (create, extract, test)"
    echo "0. Cleanup"
    echo "q. Quit"
}

# Command line interface
if [[ $# -gt 0 ]]; then
    case "$1" in
        create) shift; create_tenants "$@" ;;
        extract) shift; extract_certs "$@" ;;
        test) shift; test_tenants "$@" ;;
        revoke) shift; revoke_tenant "$@" ;;
        unrevoke) shift; unrevoke_tenant "$@" ;;
        delete) shift; delete_tenant "$@" ;;
        status) show_status ;;
        ca-chain) check_ca_chain ;;
        setup)
            create_tenants && \
            extract_certs && \
            test_tenants
            ;;
        cleanup) cleanup ;;
        help) show_help ;;
        *) log_error "Unknown command: $1"; show_help; exit 1 ;;
    esac
    exit $?
fi

# Interactive menu
# Remove the cleanup trap
# trap cleanup EXIT  <- Remove this line

# Main loop
while true; do
    show_menu
    read -r -p "Choose an option: " choice
    
    case $choice in
        1) create_tenants ;;
        2)
            read -r -p "Enter tenant name (leave empty for all tenants): " tenant_name
            extract_certs "$tenant_name"
            ;;
        3)
            read -r -p "Enter tenant name (leave empty for all tenants): " tenant_name
            test_tenants "$tenant_name"
            ;;
        4) 
            show_status  # Show available tenants first
            read -r -p "Enter tenant name to revoke: " tenant_name
            revoke_tenant "$tenant_name"
            ;;
        5)
            show_status  # Show available tenants first
            read -r -p "Enter tenant name to unrevoke: " tenant_name
            unrevoke_tenant "$tenant_name"
            ;;
        6)
            show_status  # Show available tenants first
            read -r -p "Enter tenant name to delete: " tenant_name
            delete_tenant "$tenant_name"
            ;;
        7) show_status ;;
        8) check_ca_chain ;;
        9)
            create_tenants && \
            extract_certs && \
            test_tenants
            ;;
        0) cleanup; break ;;
        q) break ;;
        *) log_error "Invalid option" ;;
    esac
done

# Move cleanup trap here, just before exit
trap cleanup EXIT
exit 0