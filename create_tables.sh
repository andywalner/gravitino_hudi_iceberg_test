#!/bin/bash
set -e

# Use Java 11+ (required by Iceberg)
export JAVA_HOME=$(/usr/libexec/java_home -v 11 2>/dev/null || /usr/libexec/java_home -v 19)
export PATH="$JAVA_HOME/bin:$PATH"
echo "Using Java: $(java -version 2>&1 | head -1)"

# Use Spark 3.5
export SPARK_HOME="${SPARK_HOME:-/Users/andywalner/Documents/spark-3.5.3-bin-hadoop3}"
export PATH="$SPARK_HOME/bin:$PATH"
echo "Using Spark: $SPARK_HOME"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Creating sample tables ==="

# Create Iceberg table
echo ""
echo "--- Step 1: Creating Iceberg table ---"
spark-submit \
  --packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.7.1 \
  "$SCRIPT_DIR/create_iceberg_table.py"

# Create Hudi table
echo ""
echo "--- Step 2: Creating Hudi table ---"
spark-submit \
  --packages org.apache.hudi:hudi-spark3.5-bundle_2.12:0.15.0 \
  "$SCRIPT_DIR/create_hudi_table.py"

echo ""
echo "=== Table creation complete ==="
