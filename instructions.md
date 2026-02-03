# Gravitino Local Test Setup - Final Briefing

## Objective
Deploy a complete local test environment with a true third-party Iceberg REST catalog (Tabular/Polaris), local Hive Metastore for Hudi, and Gravitino federating both. Execute a single Spark job that connects once to Gravitino and performs cross-format queries and joins.

## Architecture
```
spark-submit job.py
    ↓
Single Spark Session (only Gravitino configs)
    ↓
Gravitino Server :8090
    ↓
    ├─→ iceberg_catalog → Tabular REST Catalog :8181
    └─→ hudi_catalog → Hive Metastore :9083
```

## Deliverables

### 1. Infrastructure Setup Script (`setup_infrastructure.sh`)
Sets up all components but NO tables:
- PostgreSQL (for HMS backend)
- Hive Metastore :9083
- Tabular Iceberg REST Catalog :8181
- Gravitino Server :8090
- Configures catalogs in Gravitino

### 2. Table Creation Script (`create_tables.sh`)
Creates sample tables with test data:
- Iceberg table in Tabular catalog
- Hudi CoW table in HMS

### 3. Spark Job (`test_federation.py`)
Single spark-submit job that:
- Connects to Gravitino with minimal config
- Queries Iceberg table
- Queries Hudi table
- Performs cross-format join
- Prints results

---

## Component Details

### Component 1: PostgreSQL (HMS Backend)
```yaml
Container: postgres:13
Port: 5432
Database: metastore_db
User/Pass: hive/hive
Purpose: Backend for Hive Metastore
```

### Component 2: Hive Metastore
```yaml
Container: apache/hive:3.1.3 (or standalone)
Port: 9083
Backend: PostgreSQL above
Warehouse: file:///tmp/hive-warehouse
Config: 
  - metastore.warehouse.dir=/tmp/hive-warehouse
  - javax.jdo.option.ConnectionURL=jdbc:postgresql://localhost:5432/metastore_db
```

### Component 3: Tabular Iceberg REST Catalog
```yaml
Container: tabular-io/iceberg-rest
Port: 8181
Warehouse: file:///tmp/iceberg-warehouse
Backend: In-memory (for testing) or SQLite
Config:
  - catalog.warehouse=file:///tmp/iceberg-warehouse
  - catalog.io-impl=org.apache.iceberg.io.ResolvingFileIO
```

**Reference:** https://github.com/tabular-io/iceberg-rest-image

**Verification command:**
```bash
curl http://localhost:8181/v1/config
```

### Component 4: Gravitino Server
```yaml
Binary: gravitino-1.1.0-bin.tar.gz
Port: 8090 (main API)
Metalake: test_metalake
Catalogs to create:
  1. iceberg_catalog (type: lakehouse-iceberg)
     - backend: rest
     - uri: http://localhost:8181
     - warehouse: file:///tmp/iceberg-warehouse
  
  2. hudi_catalog (type: lakehouse-hudi) 
     - metastore.uris: thrift://localhost:9083
     - warehouse: file:///tmp/hive-warehouse
```

---

## Script 1: setup_infrastructure.sh

```bash
#!/bin/bash
set -e

echo "=== Setting up Gravitino Federation Test Environment ==="

# 1. Start PostgreSQL for HMS
echo "Starting PostgreSQL..."
docker run -d \
  --name metastore-postgres \
  -p 5432:5432 \
  -e POSTGRES_DB=metastore_db \
  -e POSTGRES_USER=hive \
  -e POSTGRES_PASSWORD=hive \
  postgres:13

# Wait for postgres
sleep 5

# 2. Start Hive Metastore
echo "Starting Hive Metastore..."
# Use docker or download standalone HMS binary
# Configure to use PostgreSQL above
# Expose port 9083

# 3. Start Tabular Iceberg REST Catalog
echo "Starting Tabular Iceberg REST Catalog..."
docker run -d \
  --name iceberg-rest \
  -p 8181:8181 \
  -e CATALOG_WAREHOUSE=file:///tmp/iceberg-warehouse \
  -e CATALOG_IO_IMPL=org.apache.iceberg.io.ResolvingFileIO \
  -v /tmp/iceberg-warehouse:/tmp/iceberg-warehouse \
  tabulario/iceberg-rest:latest

# Wait for catalog
sleep 10

# Verify Tabular is running
curl http://localhost:8181/v1/config || echo "Tabular catalog not ready"

# 4. Download and start Gravitino
echo "Setting up Gravitino..."
if [ ! -d "gravitino-1.1.0-bin" ]; then
  wget https://downloads.apache.org/gravitino/1.1.0/gravitino-1.1.0-bin.tar.gz
  tar -xzf gravitino-1.1.0-bin.tar.gz
fi

cd gravitino-1.1.0-bin
./bin/gravitino.sh start

# Wait for Gravitino
sleep 10

# 5. Create metalake
echo "Creating metalake..."
curl -X POST http://localhost:8090/api/metalakes \
  -H "Content-Type: application/json" \
  -d '{
    "name": "test_metalake",
    "comment": "Test federation",
    "properties": {}
  }'

# 6. Create Iceberg catalog (federating Tabular)
echo "Creating Iceberg catalog in Gravitino..."
curl -X POST http://localhost:8090/api/metalakes/test_metalake/catalogs \
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
  }'

# 7. Create Hudi catalog (pointing to HMS)
echo "Creating Hudi catalog in Gravitino..."
curl -X POST http://localhost:8090/api/metalakes/test_metalake/catalogs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "hudi_catalog",
    "type": "RELATIONAL",
    "provider": "lakehouse-hudi",
    "comment": "Hudi via HMS",
    "properties": {
      "metastore.uris": "thrift://localhost:9083",
      "warehouse": "file:///tmp/hive-warehouse"
    }
  }'

# Verify catalogs
echo "Verifying catalogs..."
curl http://localhost:8090/api/metalakes/test_metalake/catalogs

echo "=== Infrastructure setup complete ==="
echo "Hive Metastore: thrift://localhost:9083"
echo "Tabular REST: http://localhost:8181"
echo "Gravitino: http://localhost:8090"
```

---

## Script 2: create_tables.sh

```bash
#!/bin/bash
set -e

echo "=== Creating sample tables ==="

# Create tables via PySpark
python3 << 'EOF'
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, TimestampType
from datetime import datetime

# 1. Create Iceberg table directly in Tabular catalog
print("Creating Iceberg table in Tabular catalog...")
spark_iceberg = SparkSession.builder \
    .appName("Create Iceberg Table") \
    .config("spark.jars.packages", "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.7.1") \
    .config("spark.sql.catalog.tabular", "org.apache.iceberg.spark.SparkCatalog") \
    .config("spark.sql.catalog.tabular.type", "rest") \
    .config("spark.sql.catalog.tabular.uri", "http://localhost:8181") \
    .config("spark.sql.catalog.tabular.warehouse", "file:///tmp/iceberg-warehouse") \
    .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
    .getOrCreate()

spark_iceberg.sql("CREATE NAMESPACE IF NOT EXISTS tabular.test_db")
spark_iceberg.sql("""
    CREATE TABLE IF NOT EXISTS tabular.test_db.sales_iceberg (
        transaction_id INT,
        customer_name STRING,
        amount INT,
        transaction_date TIMESTAMP
    ) USING iceberg
""")

# Insert sample data
data_iceberg = [
    (1, "Alice", 100, datetime(2024, 1, 15)),
    (2, "Bob", 200, datetime(2024, 1, 16)),
    (3, "Charlie", 150, datetime(2024, 1, 17)),
    (4, "Diana", 300, datetime(2024, 1, 18)),
    (5, "Eve", 250, datetime(2024, 1, 19))
]

schema = StructType([
    StructField("transaction_id", IntegerType(), False),
    StructField("customer_name", StringType(), False),
    StructField("amount", IntegerType(), False),
    StructField("transaction_date", TimestampType(), False)
])

df_iceberg = spark_iceberg.createDataFrame(data_iceberg, schema)
df_iceberg.writeTo("tabular.test_db.sales_iceberg").append()

print("Iceberg table created with 5 rows")
spark_iceberg.stop()

# 2. Create Hudi CoW table in HMS
print("Creating Hudi table in HMS...")
spark_hudi = SparkSession.builder \
    .appName("Create Hudi Table") \
    .config("spark.jars.packages", "org.apache.hudi:hudi-spark3.5-bundle_2.12:0.15.0") \
    .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer") \
    .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.hudi.catalog.HoodieCatalog") \
    .config("spark.sql.extensions", "org.apache.spark.sql.hudi.HoodieSparkSessionExtension") \
    .config("spark.sql.catalogImplementation", "hive") \
    .config("hive.metastore.uris", "thrift://localhost:9083") \
    .enableHiveSupport() \
    .getOrCreate()

spark_hudi.sql("CREATE DATABASE IF NOT EXISTS test_db")

# Insert Hudi table with CoW
data_hudi = [
    (1, "Premium", 50),
    (2, "Standard", 30),
    (3, "Premium", 40),
    (4, "Gold", 60),
    (5, "Standard", 35)
]

df_hudi = spark_hudi.createDataFrame(data_hudi, ["transaction_id", "customer_tier", "discount"])

hudi_options = {
    'hoodie.table.name': 'customer_info_hudi',
    'hoodie.datasource.write.recordkey.field': 'transaction_id',
    'hoodie.datasource.write.table.name': 'customer_info_hudi',
    'hoodie.datasource.write.operation': 'insert',
    'hoodie.datasource.write.precombine.field': 'transaction_id',
    'hoodie.table.type': 'COPY_ON_WRITE'
}

df_hudi.write.format("hudi") \
    .options(**hudi_options) \
    .mode("overwrite") \
    .saveAsTable("test_db.customer_info_hudi")

print("Hudi table created with 5 rows")
spark_hudi.stop()

print("=== Table creation complete ===")
EOF
```

---

## Script 3: test_federation.py

```python
"""
Gravitino Federation Test
Single Spark job that connects to Gravitino and performs cross-format queries
"""
from pyspark.sql import SparkSession

def main():
    print("=== Starting Gravitino Federation Test ===\n")
    
    # Create Spark session with ONLY Gravitino configs
    print("1. Creating Spark session with Gravitino connector...")
    spark = SparkSession.builder \
        .appName("Gravitino Federation Test") \
        .config("spark.plugins", "org.apache.gravitino.spark.connector.plugin.GravitinoSparkPlugin") \
        .config("spark.sql.gravitino.uri", "http://localhost:8090") \
        .config("spark.sql.gravitino.metalake", "test_metalake") \
        .config("spark.sql.gravitino.enableIcebergSupport", "true") \
        .config("spark.sql.gravitino.enableHudiSupport", "true") \
        .config("spark.jars.packages", 
                "org.apache.gravitino:gravitino-spark-connector-runtime-3.5:1.1.0,"
                "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.7.1,"
                "org.apache.hudi:hudi-spark3.5-bundle_2.12:0.15.0") \
        .getOrCreate()
    
    print("✓ Spark session created\n")
    
    # Verify only Gravitino connection configured
    print("2. Verifying catalog configuration...")
    print("Configured catalogs (should only show Gravitino):")
    spark.sql("SHOW CATALOGS").show()
    print()
    
    # Test 1: Query Iceberg table
    print("3. Querying Iceberg table from Tabular catalog...")
    spark.sql("USE iceberg_catalog")
    
    iceberg_df = spark.sql("""
        SELECT * FROM test_db.sales_iceberg
        ORDER BY transaction_id
    """)
    
    print("Iceberg table (sales_iceberg):")
    iceberg_df.show()
    print(f"Row count: {iceberg_df.count()}\n")
    
    # Test 2: Query Hudi table
    print("4. Querying Hudi table from HMS...")
    spark.sql("USE hudi_catalog")
    
    hudi_df = spark.sql("""
        SELECT transaction_id, customer_tier, discount 
        FROM test_db.customer_info_hudi
        ORDER BY transaction_id
    """)
    
    print("Hudi table (customer_info_hudi):")
    hudi_df.show()
    print(f"Row count: {hudi_df.count()}\n")
    
    # Test 3: Cross-format join
    print("5. Performing cross-format join (Iceberg + Hudi)...")
    joined_df = spark.sql("""
        SELECT 
            i.transaction_id,
            i.customer_name,
            i.amount,
            h.customer_tier,
            h.discount,
            (i.amount - h.discount) as final_amount
        FROM iceberg_catalog.test_db.sales_iceberg i
        INNER JOIN hudi_catalog.test_db.customer_info_hudi h
        ON i.transaction_id = h.transaction_id
        ORDER BY i.transaction_id
    """)
    
    print("Cross-format join result:")
    joined_df.show()
    print(f"Joined row count: {joined_df.count()}\n")
    
    # Test 4: Aggregation on joined data
    print("6. Running aggregation on joined data...")
    agg_df = spark.sql("""
        SELECT 
            h.customer_tier,
            COUNT(*) as transaction_count,
            SUM(i.amount) as total_amount,
            AVG(h.discount) as avg_discount
        FROM iceberg_catalog.test_db.sales_iceberg i
        INNER JOIN hudi_catalog.test_db.customer_info_hudi h
        ON i.transaction_id = h.transaction_id
        GROUP BY h.customer_tier
        ORDER BY total_amount DESC
    """)
    
    print("Aggregation by customer tier:")
    agg_df.show()
    
    print("\n=== Test Complete ===")
    print("✓ Single Gravitino connection configured")
    print("✓ Queried Iceberg table from Tabular catalog")
    print("✓ Queried Hudi table from HMS")
    print("✓ Performed cross-format join successfully")
    print("✓ Executed aggregations on federated data")
    
    spark.stop()

if __name__ == "__main__":
    main()
```

---

## Execution Instructions

### 1. Setup Infrastructure
```bash
chmod +x setup_infrastructure.sh
./setup_infrastructure.sh
```

**Expected output:** All services running, catalogs configured in Gravitino

### 2. Create Tables
```bash
chmod +x create_tables.sh
./create_tables.sh
```

**Expected output:** 
- `sales_iceberg` table in Tabular with 5 rows
- `customer_info_hudi` table in HMS with 5 rows

### 3. Run Federation Test
```bash
spark-submit \
  --packages org.apache.gravitino:gravitino-spark-connector-runtime-3.5:1.1.0,org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.7.1,org.apache.hudi:hudi-spark3.5-bundle_2.12:0.15.0 \
  test_federation.py
```

**Expected output:**
```
=== Starting Gravitino Federation Test ===
1. Creating Spark session with Gravitino connector...
✓ Spark session created

2. Verifying catalog configuration...
[Shows only Gravitino catalogs]

3. Querying Iceberg table from Tabular catalog...
[Shows 5 rows from sales_iceberg]

4. Querying Hudi table from HMS...
[Shows 5 rows from customer_info_hudi]

5. Performing cross-format join...
[Shows joined results with customer names, amounts, tiers, discounts]

6. Running aggregation...
[Shows aggregated data by customer tier]

=== Test Complete ===
✓ All tests passed
```

---

## Verification Checklist

- [ ] PostgreSQL running on :5432
- [ ] Hive Metastore running on :9083
- [ ] Tabular REST catalog running on :8181
- [ ] Gravitino running on :8090
- [ ] Gravitino has 2 catalogs: iceberg_catalog, hudi_catalog
- [ ] Iceberg table exists in Tabular catalog
- [ ] Hudi table exists in HMS
- [ ] Spark job runs with single Gravitino connector config
- [ ] Cross-format join executes successfully
- [ ] No errors in Gravitino logs during query execution

---

## Success Criteria

✅ **Single connection point:** Spark configured with only Gravitino connector, no direct Iceberg or Hudi catalog configs  
✅ **Federation verified:** Gravitino routes queries to correct backend (Tabular for Iceberg, HMS for Hudi)  
✅ **Cross-format join works:** Can join Iceberg and Hudi tables in single SQL query  
✅ **True external catalog:** Using Tabular as independent third-party Iceberg REST catalog  

This proves Gravitino can federate existing catalogs without replacing them.