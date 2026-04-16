from pyspark.sql import SparkSession

spark = SparkSession.builder.appName("StreamingProcessor").getOrCreate()

df = spark.readStream.format("kafka") \
    .option("kafka.bootstrap.servers", "kafka:9092") \
    .option("subscribe", "truck-gps-dev") \
    .option("startingOffsets","latest") \
    .option("failOnDataLoss", "false") \
    .load()
    
# print(df.show())  # for debugging only — remove in production

df_string = df.selectExpr("CAST(key AS STRING)", "CAST(value AS STRING)")

query = df_string.writeStream \
    .format("console") \
    .outputMode("append") \
    .option("truncate", "false") \
    .trigger(processingTime="1 second") \
    .start()

query.awaitTermination()


# /opt/spark/bin/spark-submit \
#   --master spark://spark-master:7077 \
#   --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1 \
#   --conf spark.jars.ivy=/tmp/.ivy \
#   /opt/spark/work-dir/streaming_processor.py

  