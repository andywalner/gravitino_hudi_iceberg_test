from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, TimestampType
from datetime import datetime

print("Creating Iceberg table in Tabular catalog...")
spark = SparkSession.builder \
    .appName("Create Iceberg Table") \
    .config("spark.sql.catalog.tabular", "org.apache.iceberg.spark.SparkCatalog") \
    .config("spark.sql.catalog.tabular.type", "rest") \
    .config("spark.sql.catalog.tabular.uri", "http://localhost:8181") \
    .config("spark.sql.catalog.tabular.warehouse", "file:///tmp/iceberg-warehouse") \
    .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
    .getOrCreate()

spark.sql("CREATE NAMESPACE IF NOT EXISTS tabular.test_db")
spark.sql("""
    CREATE TABLE IF NOT EXISTS tabular.test_db.sales_iceberg (
        transaction_id INT,
        customer_name STRING,
        amount INT,
        transaction_date TIMESTAMP
    ) USING iceberg
""")

# Insert sample data
data = [
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

df = spark.createDataFrame(data, schema)
df.writeTo("tabular.test_db.sales_iceberg").append()

print("Iceberg table created with 5 rows")
spark.sql("SELECT * FROM tabular.test_db.sales_iceberg").show()
spark.stop()
