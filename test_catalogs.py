from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()

print("=== Cross-format JOIN via Gravitino ===")
joined = spark.sql("""
    SELECT
        i.transaction_id,
        i.customer_name,
        i.amount,
        h.customer_tier,
        h.discount,
        (i.amount - h.discount) as final_amount
    FROM iceberg_catalog.test_db.sales_iceberg i
    JOIN hive_catalog.test_db.customer_info_hudi h
    ON i.transaction_id = h.transaction_id
    ORDER BY i.transaction_id
""")
joined.show()

print("=== Aggregation on federated data ===")
agg = spark.sql("""
    SELECT
        h.customer_tier,
        COUNT(*) as transactions,
        SUM(i.amount) as total_amount,
        AVG(h.discount) as avg_discount
    FROM iceberg_catalog.test_db.sales_iceberg i
    JOIN hive_catalog.test_db.customer_info_hudi h
    ON i.transaction_id = h.transaction_id
    GROUP BY h.customer_tier
    ORDER BY total_amount DESC
""")
agg.show()

print("=== SUCCESS: Queried Iceberg + Hudi through Gravitino! ===")
spark.stop()
