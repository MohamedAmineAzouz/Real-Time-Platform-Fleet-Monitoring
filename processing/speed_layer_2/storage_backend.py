from config import *
# MinIO
from minio import Minio
from minio.error import S3Error



def get_storage_uri():
    if STORAGE_BACKEND == "minio":
        return f"s3a://{LAKE_BUCKET}/{LAKE_PREFIX}"

    elif STORAGE_BACKEND == "gcs":
        return f"s3a://{LAKE_BUCKET}/{LAKE_PREFIX}"

    raise ValueError(
        f"Unsupported STORAGE_BACKEND={STORAGE_BACKEND}"
    )


def configure_storage(builder):
    if STORAGE_BACKEND == "minio":
        builder = (
            builder
            .config("spark.hadoop.fs.s3a.endpoint", MINIO_ENDPOINT)
            .config("spark.hadoop.fs.s3a.access.key", MINIO_ROOT_USER)
            .config("spark.hadoop.fs.s3a.secret.key", MINIO_ROOT_PASSWORD)
            .config("spark.hadoop.fs.s3a.path.style.access", "true")
            .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
            .config("spark.hadoop.fs.s3a.fast.upload", "true")
            .config("spark.hadoop.fs.s3a.fast.upload.buffer", "bytebuffer")
            .config("spark.hadoop.mapreduce.fileoutputcommitter.algorithm.version", "2")
            .config("spark.hadoop.fs.s3a.committer.name", "directory")
            .config("spark.hadoop.fs.s3a.committer.staging.conflict-mode", "append")
        )

    elif STORAGE_BACKEND == "gcs":

        builder = (
            builder
            .config("spark.hadoop.google.cloud.auth.service.account.enable", "true")
            .config("spark.hadoop.google.cloud.auth.service.account.json.keyfile", GCS_KEYFILE)
        )

    return builder


def ensure_bucket_exists():

    if STORAGE_BACKEND == "minio":
        ensure_minio_bucket()

    elif STORAGE_BACKEND == "gcs":
        ensure_gcs_bucket()


def ensure_minio_bucket():

    endpoint = (
        MINIO_ENDPOINT
        .replace("http://", "")
        .replace("https://", "")
    )

    client = Minio(
        endpoint,
        access_key=MINIO_ROOT_USER,
        secret_key=MINIO_ROOT_PASSWORD,
        secure=False
    )

    try:
        exists = client.bucket_exists(
            LAKE_BUCKET
        )

        if not exists:
            print(
               f"Creating MinIO bucket {LAKE_BUCKET}"
            )

            client.make_bucket(
               LAKE_BUCKET
            )

        else:
            print(
              f"Bucket exists: {LAKE_BUCKET}"
            )

    except S3Error as e:
        raise RuntimeError(
            f"MinIO bucket check failed: {e}"
        )


def ensure_gcs_bucket():

    os.environ[
      "GOOGLE_APPLICATION_CREDENTIALS"
    ] = GCS_KEYFILE

    client = storage.Client()

    bucket = client.lookup_bucket(
        LAKE_BUCKET
    )

    if bucket is None:

        print(
           f"Creating GCS bucket {LAKE_BUCKET}"
        )

        client.create_bucket(
            LAKE_BUCKET
        )

    else:
        print(
           f"Bucket exists: {LAKE_BUCKET}"
        )