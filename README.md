# Gravitino Federation Test

A local test environment demonstrating Apache Gravitino's catalog federation capabilities. This repo proves that Gravitino can act as a unified metadata layer, allowing a single Spark session to query and join data across multiple lakehouse formats (Iceberg + Hudi) through a single connection point.

## Goal

Validate that Gravitino can federate existing catalogs without replacing them:
- **Single connection point:** Spark configured with Gravitino connector
- **True federation:** Gravitino routes queries to the correct backend automatically
- **Cross-format queries:** Join Iceberg and Hudi tables in a single SQL query

## Architecture

```
Spark Session (Gravitino connector)
           │
           ▼
    Gravitino Server :8090
           │
     ┌─────┴─────┐
     ▼           ▼
iceberg_catalog  hive_catalog
     │           │
     ▼           ▼
Tabular REST    Hive Metastore
   :8181           :9083
     │               │
     ▼               ▼
  Iceberg          Hudi
  tables          tables
```

## Key Finding

Gravitino 1.1.0's Spark connector supports:
- **Iceberg** via `lakehouse-iceberg` provider → fully supported
- **Hudi** via `hive` provider → works by reading Hudi tables registered in HMS

> Note: The `lakehouse-hudi` provider is not yet supported in the Spark connector. Use the `hive` catalog provider to access Hudi tables stored in Hive Metastore.

## Prerequisites

- **Docker** (for PostgreSQL, Hive Metastore, Iceberg REST catalog)
- **Java 11+** (required by Gravitino and Spark)
- **Apache Spark 3.5.x**
- **Python 3** with PySpark

## Quick Start

### 1. Start Infrastructure

```bash
chmod +x setup_infrastructure.sh
./setup_infrastructure.sh
```

This will:
- Create a Docker network for container communication
- Start PostgreSQL (HMS backend) on `:5432`
- Start Hive Metastore on `:9083`
- Start Tabular Iceberg REST catalog on `:8181`
- Download and start Gravitino 1.1.0 on `:8090`
- Configure federated catalogs in Gravitino:
  - `iceberg_catalog` → Tabular REST (lakehouse-iceberg)
  - `hive_catalog` → Hive Metastore (hive)

### 2. Create Sample Tables

```bash
chmod +x create_tables.sh
./create_tables.sh
```

Creates:
- `test_db.sales_iceberg` (Iceberg) - 5 rows of transaction data
- `test_db.customer_info_hudi` (Hudi CoW) - 5 rows of customer tier data

### 3. Run Federation Test

```bash
export JAVA_HOME=$(/usr/libexec/java_home -v 19)
export SPARK_HOME=~/Documents/spark-3.5.3-bin-hadoop3

spark-submit \
  --packages org.apache.gravitino:gravitino-spark-connector-runtime-3.5_2.12:1.1.0,org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.7.1,org.apache.hudi:hudi-spark3.5-bundle_2.12:0.15.0 \
  --conf spark.plugins=org.apache.gravitino.spark.connector.plugin.GravitinoSparkPlugin \
  --conf spark.sql.gravitino.uri=http://localhost:8090 \
  --conf spark.sql.gravitino.metalake=test_metalake \
  --conf spark.sql.gravitino.enableIcebergSupport=true \
  --conf spark.serializer=org.apache.spark.serializer.KryoSerializer \
  --conf spark.sql.catalogImplementation=hive \
  --conf spark.hadoop.hive.metastore.uris=thrift://localhost:9083 \
  --conf "spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions,org.apache.spark.sql.hudi.HoodieSparkSessionExtension" \
  test_catalogs.py
```

### 4. Run in Jupyter Notebook

```bash
jupyter notebook test_federation.ipynb
```

## Example Queries

```sql
-- Query Iceberg table via Gravitino
SELECT * FROM iceberg_catalog.test_db.sales_iceberg;

-- Query Hudi table via Gravitino
SELECT * FROM hive_catalog.test_db.customer_info_hudi;

-- Cross-format JOIN
SELECT
    i.transaction_id,
    i.customer_name,
    i.amount,
    h.customer_tier,
    h.discount,
    (i.amount - h.discount) as final_amount
FROM iceberg_catalog.test_db.sales_iceberg i
JOIN hive_catalog.test_db.customer_info_hudi h
ON i.transaction_id = h.transaction_id;
```

## Verification

```bash
# Gravitino
curl http://localhost:8090/api/version

# List catalogs
curl http://localhost:8090/api/metalakes/test_metalake/catalogs

# Iceberg REST catalog
curl http://localhost:8181/v1/config

# Hive Metastore
nc -z localhost 9083 && echo "HMS running"
```

## Cleanup

```bash
# Stop Gravitino
./gravitino-1.1.0-bin/bin/gravitino.sh stop

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
| `create_iceberg_table.py` | PySpark script to create Iceberg table |
| `create_hudi_table.py` | PySpark script to create Hudi table in HMS |
| `test_catalogs.py` | Quick test script for catalog access |
| `test_federation.py` | Full federation test with joins |
| `test_federation.ipynb` | Jupyter notebook version |

## Test Results

```
=== Cross-format JOIN via Gravitino ===
+--------------+-------------+------+-------------+--------+------------+
|transaction_id|customer_name|amount|customer_tier|discount|final_amount|
+--------------+-------------+------+-------------+--------+------------+
|             1|        Alice|   100|      Premium|      50|          50|
|             2|          Bob|   200|     Standard|      30|         170|
|             3|      Charlie|   150|      Premium|      40|         110|
|             4|        Diana|   300|         Gold|      60|         240|
|             5|          Eve|   250|     Standard|      35|         215|
+--------------+-------------+------+-------------+--------+------------+

=== Aggregation on federated data ===
+-------------+------------+------------+------------+
|customer_tier|transactions|total_amount|avg_discount|
+-------------+------------+------------+------------+
|     Standard|           2|         450|        32.5|
|         Gold|           1|         300|        60.0|
|      Premium|           2|         250|        45.0|
+-------------+------------+------------+------------+

=== SUCCESS: Queried Iceberg + Hudi through Gravitino! ===
```
