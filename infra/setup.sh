#!/usr/bin/env bash
# infra/setup.sh
# ─────────────────────────────────────────────────────────────────────────────
# One-time Azure infrastructure setup for Manhattan Project.
# Run this ONCE to create all Azure resources before the first CI/CD deployment.
#
# Prerequisites:
#   - Azure CLI installed and logged in  (`az login`)
#   - jq installed
#   - A .env file in the repo root with your app secrets
#
# Usage:
#   chmod +x infra/setup.sh
#   ./infra/setup.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Configuration — edit these to match your desired names ───────────────────
RESOURCE_GROUP="manhattan-rg"
LOCATION="eastus"
ACR_NAME="manhattanacr"              # must be globally unique, lowercase, alphanumeric
CONTAINER_APP_ENV="manhattan-env"
POSTGRES_SERVER="manhattan-pg"
POSTGRES_ADMIN="pgadmin"
POSTGRES_DB="conference_db"
GITHUB_REPO="amruth6002/newproj"     # org/repo for the OIDC trust
# ─────────────────────────────────────────────────────────────────────────────

ACR_LOGIN_SERVER="${ACR_NAME}.azurecr.io"

echo "========================================================"
echo " Manhattan Project — Azure Infrastructure Setup"
echo "========================================================"
echo "Resource Group : $RESOURCE_GROUP"
echo "Location       : $LOCATION"
echo "ACR            : $ACR_LOGIN_SERVER"
echo "Container Env  : $CONTAINER_APP_ENV"
echo "PostgreSQL     : $POSTGRES_SERVER"
echo ""

# ── 1. Resource group ─────────────────────────────────────────────────────────
echo ">>> Creating resource group..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

# ── 2. Azure Container Registry ───────────────────────────────────────────────
echo ">>> Creating Azure Container Registry..."
az acr create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ACR_NAME" \
  --sku Basic \
  --admin-enabled false \
  --output none
echo "    ACR: $ACR_LOGIN_SERVER"

# ── 3. PostgreSQL Flexible Server with pgvector ───────────────────────────────
echo ">>> Creating PostgreSQL Flexible Server (this takes ~3 minutes)..."
POSTGRES_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)

az postgres flexible-server create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$POSTGRES_SERVER" \
  --location "$LOCATION" \
  --admin-user "$POSTGRES_ADMIN" \
  --admin-password "$POSTGRES_PASSWORD" \
  --database-name "$POSTGRES_DB" \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --storage-size 32 \
  --version 16 \
  --public-access "0.0.0.0" \
  --output none
# NOTE: --public-access "0.0.0.0" allows all Azure services to connect, which is
# needed for Container Apps. For production hardening, restrict to your
# Container Apps environment outbound IPs or use private VNet integration.

echo ">>> Enabling pgvector extension..."
az postgres flexible-server parameter set \
  --resource-group "$RESOURCE_GROUP" \
  --server-name "$POSTGRES_SERVER" \
  --name azure.extensions \
  --value vector \
  --output none

POSTGRES_HOST="${POSTGRES_SERVER}.postgres.database.azure.com"
DATABASE_URL="postgresql://${POSTGRES_ADMIN}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:5432/${POSTGRES_DB}?sslmode=require"
echo "    PostgreSQL host: $POSTGRES_HOST"

# ── 4. Container Apps Environment ────────────────────────────────────────────
echo ">>> Creating Container Apps Environment..."
az containerapp env create \
  --name "$CONTAINER_APP_ENV" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output none

# ── 5. Service principal + OIDC federated credentials for GitHub Actions ─────
echo ">>> Creating service principal for GitHub Actions..."
SUBSCRIPTION_ID=$(az account show --query id --output tsv)
SP_JSON=$(az ad sp create-for-rbac \
  --name "manhattan-github-actions" \
  --role Contributor \
  --scopes "/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}" \
  --output json)

CLIENT_ID=$(echo "$SP_JSON"     | jq -r '.appId')
CLIENT_SECRET=$(echo "$SP_JSON" | jq -r '.password')
TENANT_ID=$(echo "$SP_JSON"     | jq -r '.tenant')

echo ">>> Granting AcrPush role to service principal..."
ACR_ID=$(az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" --query id --output tsv)
az role assignment create \
  --assignee "$CLIENT_ID" \
  --role AcrPush \
  --scope "$ACR_ID" \
  --output none

echo ">>> Configuring OIDC federated credentials for GitHub Actions..."
# Federated credentials must be created on the App registration (not the SP).
# Use `az ad app show` to get the App object ID from the appId (CLIENT_ID).
APP_OBJECT_ID=$(az ad app show --id "$CLIENT_ID" --query id --output tsv)
az ad app federated-credential create \
  --id "$APP_OBJECT_ID" \
  --parameters "{
    \"name\": \"github-actions-main\",
    \"issuer\": \"https://token.actions.githubusercontent.com\",
    \"subject\": \"repo:${GITHUB_REPO}:ref:refs/heads/main\",
    \"audiences\": [\"api://AzureADTokenExchange\"]
  }" \
  --output none 2>/dev/null || true   # May fail if already exists

# ── 6. Create all Container Apps (initial empty deploy with placeholder) ──────
echo ">>> Creating Container Apps..."

SHARED_ENV_VARS=(
  "AZURE_OPENAI_ENDPOINT=placeholder"
  "AZURE_OPENAI_API_KEY=placeholder"
  "AZURE_OPENAI_API_VERSION=2024-02-15-preview"
  "AZURE_OPENAI_DEPLOYMENT=gpt-4o"
  "AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large"
  "DATABASE_URL=${DATABASE_URL}"
  "POSTGRES_PASSWORD=${POSTGRES_PASSWORD}"
  "POSTGRES_USER=${POSTGRES_ADMIN}"
  "POSTGRES_DB=${POSTGRES_DB}"
  "MCP_SERVER_URL=http://mcp-server/sse"
  "REGISTRY_URL=http://registry"
  "VENUE_URL=http://venue-agent"
  "PRICING_URL=http://pricing-agent"
  "SPONSOR_URL=http://sponsor-agent"
  "SPEAKER_URL=http://speaker-agent"
  "EXHIBITOR_URL=http://exhibitor-agent"
  "COMMUNITY_URL=http://community-agent"
  "EVENTOPS_URL=http://eventops-agent"
)

# Internal services (no external ingress)
INTERNAL_SERVICES=(
  "mcp-server:8080"
  "registry:9000"
  "venue-agent:8001"
  "pricing-agent:8002"
  "sponsor-agent:8003"
  "speaker-agent:8004"
  "exhibitor-agent:8005"
  "community-agent:8006"
)

for svc_port in "${INTERNAL_SERVICES[@]}"; do
  SVC="${svc_port%%:*}"
  PORT="${svc_port##*:}"
  echo "    Creating internal Container App: $SVC (port $PORT)..."
  az containerapp create \
    --name "$SVC" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$CONTAINER_APP_ENV" \
    --image "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest" \
    --target-port "$PORT" \
    --ingress internal \
    --min-replicas 0 \
    --max-replicas 3 \
    --env-vars "${SHARED_ENV_VARS[@]}" \
    --output none
done

# EventOps — external ingress
echo "    Creating external Container App: eventops-agent (port 8000)..."
az containerapp create \
  --name "eventops-agent" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$CONTAINER_APP_ENV" \
  --image "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest" \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 5 \
  --env-vars "${SHARED_ENV_VARS[@]}" \
  --output none

# Frontend — external ingress
echo "    Creating external Container App: frontend (port 80)..."
az containerapp create \
  --name "frontend" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$CONTAINER_APP_ENV" \
  --image "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest" \
  --target-port 80 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 5 \
  --output none

# ── 7. Run SQL schema migrations against Azure PostgreSQL ─────────────────────
echo ">>> Applying database schema migrations..."
echo "    (Requires psql to be installed locally)"

SCRIPTS=(
  "database/schema.sql"
  "database/002_working_memory.sql"
  "database/003_procedural_memory.sql"
  "database/005_reactive_checkpoint.sql"
  "database/006_registry.sql"
)

if command -v psql &>/dev/null; then
  for script in "${SCRIPTS[@]}"; do
    echo "    Running $script..."
    PGPASSWORD="$POSTGRES_PASSWORD" psql \
      "host=${POSTGRES_HOST} port=5432 dbname=${POSTGRES_DB} user=${POSTGRES_ADMIN} sslmode=require" \
      -f "$script" -q || true
  done
  echo "    Running seed data (database/004_seed_memory.sql)..."
  PGPASSWORD="$POSTGRES_PASSWORD" psql \
    "host=${POSTGRES_HOST} port=5432 dbname=${POSTGRES_DB} user=${POSTGRES_ADMIN} sslmode=require" \
    -f "database/004_seed_memory.sql" -q || true
else
  echo "    ⚠️  psql not found — skipping migrations."
  echo "    Run them manually once psql is available:"
  for script in "${SCRIPTS[@]}"; do
    echo "      psql \"host=${POSTGRES_HOST} port=5432 dbname=${POSTGRES_DB} user=${POSTGRES_ADMIN} sslmode=require\" -f $script"
  done
fi

# ── 8. Print GitHub Secrets summary ──────────────────────────────────────────
echo ""
echo "========================================================"
echo " Setup complete! Add these secrets to your GitHub repo:"
echo " (Settings → Secrets and variables → Actions → New secret)"
echo "========================================================"
echo ""
echo "  AZURE_CLIENT_ID           = $CLIENT_ID"
echo "  AZURE_TENANT_ID           = $TENANT_ID"
echo "  AZURE_SUBSCRIPTION_ID     = $SUBSCRIPTION_ID"
echo "  ACR_LOGIN_SERVER          = $ACR_LOGIN_SERVER"
echo ""
echo "  POSTGRES_USER             = $POSTGRES_ADMIN"
echo "  POSTGRES_PASSWORD         = $POSTGRES_PASSWORD"
echo "  POSTGRES_DB               = $POSTGRES_DB"
echo "  DATABASE_URL              = $DATABASE_URL"
echo ""
echo "  AZURE_OPENAI_ENDPOINT     = <your Azure OpenAI endpoint>"
echo "  AZURE_OPENAI_API_KEY      = <your Azure OpenAI API key>"
echo "  AZURE_OPENAI_DEPLOYMENT   = gpt-4o"
echo "  AZURE_OPENAI_EMBEDDING_DEPLOYMENT = text-embedding-3-large"
echo ""
echo "========================================================"
echo " Next step: push to main to trigger the first deployment."
echo "========================================================"
