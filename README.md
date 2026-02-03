# Gravitino Federation Test

A local test environment demonstrating Apache Gravitino's catalog federation capabilities. This repo proves that Gravitino can act as a unified metadata layer, allowing a single Spark session to query and join data across multiple lakehouse formats (Iceberg + Hudi) without directly configuring each catalog.

## Goal

Validate that Gravitino can federate existing catalogs without replacing them:
- **Single connection point:** Spark configured with only Gravitino connector (no direct Iceberg/Hudi configs)
- **True federation:** Gravitino routes queries to the correct backend automatically
- **Cross-format queries:** Join Iceberg and Hudi tables in a single SQL query

## Architecture

```
Spark Session (Gravitino connector only)
           │
           ▼
    Gravitino Server :8090
           │
     ┌─────┴─────┐
     ▼           ▼
iceberg_catalog  hudi_catalog
     │           │
     ▼           ▼
Tabular REST    Hive Metastore
   :8181           :9083
     │               │
     ▼               ▼
  Iceberg          Hudi
  tables          tables
```

## Prerequisites

- **Docker** (for PostgreSQL, Hive Metastore, Iceberg REST catalog)
- **Java 11+** (required by Gravitino and Spark)
- **Apache Spark 3.5.x** (with `SPARK_HOME` set, or installed at `/Users/andywalner/Documents/spark-3.5.3-bin-hadoop3`)
- **Python 3** with PySpark

## Quick Start

### 1. Start Infrastructure

Launches PostgreSQL, Hive Metastore, Iceberg REST catalog, and Gravitino server:

```bash
chmod +x setup_infrastructure.sh
./setup_infrastructure.sh
```

This will:
- Create a Docker network for container communication
- Start PostgreSQL (HMS backend) on `:5432`
- Start Hive Metastore on `:9083`
- Start Tabular Iceberg REST catalog on `:8181`
- Start Gravitino server on `:8090`
- Configure two federated catalogs in Gravitino:
  - `iceberg_catalog` → Tabular REST
  - `hudi_catalog` → Hive Metastore

### 2. Create Sample Tables

Creates test tables with sample data in both catalogs:

```bash
chmod +x create_tables.sh
./create_tables.sh
```

This creates:
- `test_db.sales_iceberg` (Iceberg) - 5 rows of transaction data
- `test_db.customer_info_hudi` (Hudi CoW) - 5 rows of customer tier data

### 3. Run Federation Test

Execute the cross-format query test:

```bash
spark-submit \
  --packages org.apache.gravitino:gravitino-spark-connector-runtime-3.5_2.12:0.8.0-incubating,org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.7.1,org.apache.hudi:hudi-spark3.5-bundle_2.12:0.15.0 \
  test_federation.py
```

Expected output:
- Lists available Gravitino catalogs
- Queries Iceberg table via `iceberg_catalog.test_db.sales_iceberg`
- Queries Hudi table via `hudi_catalog.test_db.customer_info_hudi`
- Performs cross-format JOIN between Iceberg and Hudi
- Runs aggregations on the joined data

## Verification

Check services are running:

```bash
# Gravitino
curl http://localhost:8090/api/version

# Iceberg REST catalog
curl http://localhost:8181/v1/config

# Hive Metastore (check port)
nc -z localhost 9083 && echo "HMS running"

# List Gravitino catalogs
curl http://localhost:8090/api/metalakes/test_metalake/catalogs
```

## Cleanup

```bash
# Stop Gravitino
./gravitino-0.8.0-incubating-bin/bin/gravitino.sh stop

# Remove Docker containers
docker rm -f metastore-postgres iceberg-rest hive-metastore

# Remove Docker network
docker network rm gravitino-net

# Clean up warehouse data
rm -rf /tmp/iceberg-warehouse /tmp/hive-warehouse
```

## Files

| File | Description |
|------|-------------|
| `setup_infrastructure.sh` | Starts all services and configures Gravitino catalogs |
| `create_tables.sh` | Creates sample Iceberg and Hudi tables |
| `create_iceberg_table.py` | PySpark script to create Iceberg table in Tabular |
| `create_hudi_table.py` | PySpark script to create Hudi table in HMS |
| `test_federation.py` | Main federation test - queries both formats via Gravitino |
| `test_federation.ipynb` | Jupyter notebook version of the federation test |
