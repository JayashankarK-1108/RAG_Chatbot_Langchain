import boto3
import os


def _s3_client():
    return boto3.client(
        "s3",
        region_name=os.getenv("AWS_REGION"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )


def upload_images(image_paths, prefix):
    s3 = _s3_client()
    bucket = os.getenv("S3_BUCKET_NAME")

    urls = []
    for image in image_paths:
        key = f"{prefix}/{os.path.basename(image)}"
        s3.upload_file(image, bucket, key, ExtraArgs={"ContentType": "image/png"})
        urls.append(f"s3://{bucket}/{key}")

    return urls


def upload_images_mapped(image_paths, prefix):
    """Upload images and return a dict mapping local path -> S3 URL."""
    s3 = _s3_client()
    bucket = os.getenv("S3_BUCKET_NAME")

    path_to_url = {}
    for image in image_paths:
        key = f"{prefix}/{os.path.basename(image)}"
        s3.upload_file(image, bucket, key, ExtraArgs={"ContentType": "image/png"})
        path_to_url[image] = f"s3://{bucket}/{key}"

    return path_to_url
