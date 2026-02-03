from pyspark.sql import SparkSession

print("Creating Hudi table in HMS...")
spark = SparkSession.builder \
    .appName("Create Hudi Table") \
    .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer") \
    .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.hudi.catalog.HoodieCatalog") \
    .config("spark.sql.extensions", "org.apache.spark.sql.hudi.HoodieSparkSessionExtension") \
    .config("spark.hadoop.hive.metastore.uris", "thrift://localhost:9083") \
    .config("spark.sql.warehouse.dir", "file:///tmp/hive-warehouse") \
    .config("spark.hadoop.hive.metastore.warehouse.dir", "file:///tmp/hive-warehouse") \
    .enableHiveSupport() \
    .getOrCreate()

spark.sql("CREATE DATABASE IF NOT EXISTS test_db")

# Insert Hudi table with CoW
data = [
    (1, "Premium", 50),
    (2, "Standard", 30),
    (3, "Premium", 40),
    (4, "Gold", 60),
    (5, "Standard", 35)
]

df = spark.createDataFrame(data, ["transaction_id", "customer_tier", "discount"])

hudi_options = {
    'hoodie.table.name': 'customer_info_hudi',
    'hoodie.datasource.write.recordkey.field': 'transaction_id',
    'hoodie.datasource.write.table.name': 'customer_info_hudi',
    'hoodie.datasource.write.operation': 'insert',
    'hoodie.datasource.write.precombine.field': 'transaction_id',
    'hoodie.table.type': 'COPY_ON_WRITE',
    # Hive sync configuration - point to remote HMS
    'hoodie.datasource.hive_sync.enable': 'true',
    'hoodie.datasource.hive_sync.mode': 'hms',
    'hoodie.datasource.hive_sync.metastore.uris': 'thrift://localhost:9083',
    'hoodie.datasource.hive_sync.database': 'test_db',
    'hoodie.datasource.hive_sync.table': 'customer_info_hudi',
    'hoodie.datasource.hive_sync.partition_extractor_class': 'org.apache.hudi.hive.NonPartitionedExtractor',
    'hoodie.datasource.write.hive_style_partitioning': 'true',
}

df.write.format("hudi") \
    .options(**hudi_options) \
    .mode("overwrite") \
    .save("file:///tmp/hive-warehouse/test_db.db/customer_info_hudi")

print("Hudi table created with 5 rows")
spark.sql("SELECT * FROM test_db.customer_info_hudi").show()
spark.stop()
