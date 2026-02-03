#!/bin/bash
set -e

# Use Java 11+ (required by Gravitino/Iceberg)
export JAVA_HOME=$(/usr/libexec/java_home -v 11 2>/dev/null || /usr/libexec/java_home -v 19)
export PATH="$JAVA_HOME/bin:$PATH"
echo "Using Java: $(java -version 2>&1 | head -1)"

echo "=== Setting up Gravitino Federation Test Environment ==="

# Cleanup any existing containers
echo "Cleaning up existing containers..."
docker rm -f metastore-postgres iceberg-rest hive-metastore 2>/dev/null || true
docker network rm gravitino-net 2>/dev/null || true

# Create Docker network for containers to communicate
echo "Creating Docker network..."
docker network create gravitino-net

# Create shared directories
mkdir -p /tmp/iceberg-warehouse /tmp/hive-warehouse

# 1. Start PostgreSQL for HMS
echo "Starting PostgreSQL..."
docker run -d \
  --name metastore-postgres \
  --network gravitino-net \
  -p 5432:5432 \
  -e POSTGRES_DB=metastore_db \
  -e POSTGRES_USER=hive \
  -e POSTGRES_PASSWORD=hive \
  postgres:13

# Wait for postgres
echo "Waiting for PostgreSQL to be ready..."
sleep 5
until docker exec metastore-postgres pg_isready -U hive -d metastore_db > /dev/null 2>&1; do
  echo "  Waiting..."
  sleep 2
done
echo "PostgreSQL is ready"

# 2. Start Hive Metastore
echo "Starting Hive Metastore..."
docker run -d \
  --name hive-metastore \
  --network gravitino-net \
  -p 9083:9083 \
  -e SERVICE_NAME=metastore \
  -e DB_DRIVER=postgres \
  -e SERVICE_OPTS="-Djavax.jdo.option.ConnectionDriverName=org.postgresql.Driver -Djavax.jdo.option.ConnectionURL=jdbc:postgresql://metastore-postgres:5432/metastore_db -Djavax.jdo.option.ConnectionUserName=hive -Djavax.jdo.option.ConnectionPassword=hive" \
  -v /tmp/hive-warehouse:/user/hive/warehouse \
  apache/hive:3.1.3

# Wait for HMS to start
echo "Waiting for Hive Metastore to be ready (this takes a while)..."
sleep 20
until nc -z localhost 9083 2>/dev/null; do
  echo "  Waiting for port 9083..."
  sleep 5
done
echo "Hive Metastore is ready"

# 3. Start Tabular Iceberg REST Catalog
echo "Starting Tabular Iceberg REST Catalog..."
docker run -d \
  --name iceberg-rest \
  --network gravitino-net \
  -p 8181:8181 \
  -e CATALOG_WAREHOUSE=file:///tmp/iceberg-warehouse \
  -e CATALOG_IO__IMPL=org.apache.iceberg.io.ResolvingFileIO \
  -v /tmp/iceberg-warehouse:/tmp/iceberg-warehouse \
  tabulario/iceberg-rest:latest

# Wait for catalog
echo "Waiting for Iceberg REST catalog..."
sleep 10

# Verify Tabular is running
echo "Verifying Tabular catalog..."
curl -s http://localhost:8181/v1/config || echo "Warning: Tabular catalog not responding yet"

# 4. Download and start Gravitino
echo "Setting up Gravitino..."
cd /Users/andywalner/random-apps/gravitino_test

if [ ! -d "gravitino-1.1.0-bin" ]; then
  echo "Downloading Gravitino 1.1.0..."
  curl -L -O https://downloads.apache.org/gravitino/1.1.0/gravitino-1.1.0-bin.tar.gz
  tar -xzf gravitino-1.1.0-bin.tar.gz
fi

# Stop if already running
./gravitino-1.1.0-bin/bin/gravitino.sh stop 2>/dev/null || true
sleep 2

# Start Gravitino
./gravitino-1.1.0-bin/bin/gravitino.sh start

# Wait for Gravitino
echo "Waiting for Gravitino to start..."
sleep 10

# Verify Gravitino is running
until curl -s http://localhost:8090/api/version > /dev/null 2>&1; do
  echo "  Waiting for Gravitino..."
  sleep 3
done
echo "Gravitino is ready"

# 5. Create metalake
echo "Creating metalake..."
curl -s -X POST http://localhost:8090/api/metalakes \
  -H "Content-Type: application/json" \
  -d '{
    "name": "test_metalake",
    "comment": "Test federation",
    "properties": {}
  }' | head -c 200
echo ""

# 6. Create Iceberg catalog (federating Tabular)
echo "Creating Iceberg catalog in Gravitino..."
curl -s -X POST http://localhost:8090/api/metalakes/test_metalake/catalogs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "iceberg_catalog",
    "type": "RELATIONAL",
    "provider": "lakehouse-iceberg",
    "comment": "Federated Tabular REST catalog",
    "properties": {
      "catalog-backend": "rest",
      "uri": "http://localhost:8181",
      "warehouse": "file:///tmp/iceberg-warehouse"
    }
  }' | head -c 200
echo ""

# 7. Create Hive catalog (for Hudi tables in HMS)
echo "Creating Hive catalog in Gravitino..."
curl -s -X POST http://localhost:8090/api/metalakes/test_metalake/catalogs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "hive_catalog",
    "type": "RELATIONAL",
    "provider": "hive",
    "comment": "Hive Metastore (for Hudi tables)",
    "properties": {
      "metastore.uris": "thrift://localhost:9083"
    }
  }' | head -c 200
echo ""

# Verify catalogs
echo ""
echo "Verifying catalogs..."
curl -s http://localhost:8090/api/metalakes/test_metalake/catalogs | python3 -m json.tool 2>/dev/null || curl -s http://localhost:8090/api/metalakes/test_metalake/catalogs

echo ""
echo "=== Infrastructure setup complete ==="
echo "PostgreSQL:     localhost:5432"
echo "Hive Metastore: thrift://localhost:9083"
echo "Tabular REST:   http://localhost:8181"
echo "Gravitino:      http://localhost:8090"
echo ""
echo "Catalogs configured:"
echo "  - iceberg_catalog -> Tabular REST (lakehouse-iceberg)"
echo "  - hive_catalog    -> Hive Metastore (hive, for Hudi tables)"
