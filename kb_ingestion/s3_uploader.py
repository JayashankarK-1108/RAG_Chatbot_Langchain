import boto3
import os


def upload_images(image_paths, prefix):
    s3 = boto3.client(
        "s3",
        region_name=os.getenv("AWS_REGION"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )
    bucket = os.getenv("S3_BUCKET_NAME")

    urls = []
    for image in image_paths:
        key = f"{prefix}/{os.path.basename(image)}"
        s3.upload_file(image, bucket, key, ExtraArgs={"ContentType": "image/png"})
        urls.append(f"s3://{bucket}/{key}")

    return urls
