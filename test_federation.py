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
                "org.apache.gravitino:gravitino-spark-connector-runtime-3.5_2.12:0.8.0-incubating,"
                "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.7.1,"
                "org.apache.hudi:hudi-spark3.5-bundle_2.12:0.15.0") \
        .getOrCreate()

    print("Spark session created\n")

    # Verify only Gravitino connection configured
    print("2. Verifying catalog configuration...")
    print("Configured catalogs (should only show Gravitino):")
    spark.sql("SHOW CATALOGS").show()
    print()

    # Test 1: Query Iceberg table
    print("3. Querying Iceberg table from Tabular catalog...")

    iceberg_df = spark.sql("""
        SELECT * FROM iceberg_catalog.test_db.sales_iceberg
        ORDER BY transaction_id
    """)

    print("Iceberg table (sales_iceberg):")
    iceberg_df.show()
    print(f"Row count: {iceberg_df.count()}\n")

    # Test 2: Query Hudi table
    print("4. Querying Hudi table from HMS...")

    hudi_df = spark.sql("""
        SELECT transaction_id, customer_tier, discount
        FROM hudi_catalog.test_db.customer_info_hudi
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
    print("- Single Gravitino connection configured")
    print("- Queried Iceberg table from Tabular catalog")
    print("- Queried Hudi table from HMS")
    print("- Performed cross-format join successfully")
    print("- Executed aggregations on federated data")

    spark.stop()

if __name__ == "__main__":
    main()
