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
readonly SERVER_URL="myserver.invoisight.com"
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
    local tenant_count=${1:-3}
    
    log_info "Extracting certificates..."
    mkdir -p "$CERTS_DIR"
    
    # Extract CA chain for verification
    log_info "Extracting CA chain..."
    if ! kubectl get secret ca-chain-secret -n "$NAMESPACE" -o jsonpath='{.data.ca\.crt}' | \
         base64 -d > "$CERTS_DIR/ca-chain.crt"; then
        log_error "Failed to extract CA chain"
        return 1
    fi
    
    for i in $(seq 1 "$tenant_count"); do
        log_info "Extracting certificates for tenant${i}..."
        
        # Extract cert and key
        if ! kubectl get secret "tenant${i}-client-cert-secret" -n "$NAMESPACE" \
             -o jsonpath='{.data.tls\.crt}' | base64 -d > "$CERTS_DIR/tenant${i}.crt" || \
           ! kubectl get secret "tenant${i}-client-cert-secret" -n "$NAMESPACE" \
             -o jsonpath='{.data.tls\.key}' | base64 -d > "$CERTS_DIR/tenant${i}.key"; then
            log_error "Failed to extract certificates for tenant${i}"
            return 1
        fi
        
        # Set proper permissions
        chmod 600 "$CERTS_DIR/tenant${i}."{crt,key}
        log_success "Extracted certificates for tenant${i}"
    done
    
    log_success "All certificates extracted to ./$CERTS_DIR directory"
}

# Function to test tenants
test_tenants() {
    local tenant_count=${1:-3}  # Get the passed count or default to 3
    
    echo -e "\n${YELLOW}Testing tenant access...${NC}"
    
    for i in $(seq 1 "$tenant_count"); do
        echo -e "\n${YELLOW}Testing tenant${i}...${NC}"
        response=$(curl -s --cert "$CERTS_DIR/tenant${i}.crt" \
                        --key "$CERTS_DIR/tenant${i}.key" \
                        --cacert "$CERTS_DIR/ca-chain.crt" \
                        "https://$SERVER_URL") || true
        
        if [[ $response == *"X-Org-Id: tenant${i}"* ]]; then
            echo -e "${GREEN}✓ tenant${i} authentication successful${NC}"
        else
            echo -e "${RED}✗ tenant${i} authentication failed${NC}"
            echo "Response: $response"
        fi
    done
    
    # Don't return any error code to prevent script exit
    return 0
}

# Function to manage tenant state
manage_tenant_state() {
    local tenant_num=$1
    local action=$2
    local expected_state=$3
    
    # Validate tenant number
    if ! [[ $tenant_num =~ ^[1-9][0-9]*$ ]]; then
        log_error "Invalid tenant number: $tenant_num"
        return 1
    fi
    
    # Check if tenant exists
    if ! kubectl get tenant "tenant${tenant_num}" -n "$NAMESPACE" &>/dev/null; then
        log_error "Tenant${tenant_num} does not exist"
        return 1
    fi
    
    log_info "${action^}ing tenant${tenant_num}..."
    
    local patch_value
    if [[ $action == "revoke" ]]; then
        patch_value="true"
    else
        patch_value="false"
    fi
    
    if ! kubectl patch tenant "tenant${tenant_num}" -n "$NAMESPACE" \
         --type=merge -p "{\"spec\":{\"revoked\":$patch_value}}"; then
        log_error "Failed to $action tenant${tenant_num}"
        return 1
    fi
    
    # Wait for state change
    if ! wait_for_condition \
        "$action of tenant${tenant_num}" \
        "kubectl get tenant tenant${tenant_num} -n $NAMESPACE -o jsonpath='{.status.state}' | grep -q '$expected_state'"; then
        log_error "Failed to $action tenant${tenant_num}"
        return 1
    fi
    
    log_success "Tenant${tenant_num} successfully ${action}d"
}

# Wrapper functions for tenant management
revoke_tenant() { manage_tenant_state "$1" "revoke" "Revoked"; }
unrevoke_tenant() { manage_tenant_state "$1" "unrevoke" "Active"; }

# Function to delete a tenant
delete_tenant() {
    local tenant_num=$1
    
    # Validate tenant number
    if ! [[ $tenant_num =~ ^[1-9][0-9]*$ ]]; then
        log_error "Invalid tenant number: $tenant_num"
        return 1
    fi
    
    log_info "Deleting tenant${tenant_num}..."
    
    if ! kubectl delete tenant "tenant${tenant_num}" -n "$NAMESPACE" &>/dev/null; then
        log_error "Failed to delete tenant${tenant_num}"
        return 1
    fi
    
    # Wait for resources to be deleted
    if ! wait_for_condition \
        "tenant${tenant_num} deletion" \
        "! kubectl get secret tenant${tenant_num}-client-cert-secret -n $NAMESPACE &>/dev/null"; then
        log_error "Failed to delete tenant${tenant_num} resources"
        return 1
    fi
    
    log_success "Tenant${tenant_num} and associated resources deleted"
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
  extract   Extract certificates
  test      Test tenant access
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
        2) extract_certs ;;
        3) 
            # Get the actual number of tenants that exist
            tenant_count=$(kubectl get tenants -n "$NAMESPACE" --no-headers | wc -l)
            test_tenants "$tenant_count"
            ;;
        4) 
            read -r -p "Enter tenant number: " tenant_num
            revoke_tenant "$tenant_num"
            ;;
        5)
            read -r -p "Enter tenant number: " tenant_num
            unrevoke_tenant "$tenant_num"
            ;;
        6)
            read -r -p "Enter tenant number: " tenant_num
            delete_tenant "$tenant_num"
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