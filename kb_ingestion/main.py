import os
from dotenv import load_dotenv

# Load .env from project root
load_dotenv()

from kb_ingestion.document_loader import load_documents
from kb_ingestion.image_extractor import extract_images, extract_docx_segments
from kb_ingestion.s3_uploader import upload_images, upload_images_mapped
from kb_ingestion.chunker import create_chunks, create_chunks_from_segments
from kb_ingestion.embeddings import get_embeddings
from kb_ingestion.vector_store import upsert_vectors

DATA_DIR = "data/documents"

REQUIRED_ENV_VARS = [
    "OPENAI_API_KEY",
    "PINECONE_API_KEY",
    "PINECONE_INDEX",
    "AWS_REGION",
    "S3_BUCKET_NAME",
]

def validate_env():
    missing = [v for v in REQUIRED_ENV_VARS if not os.getenv(v)]
    if missing:
        raise EnvironmentError(
            f"❌ Missing required environment variables: {', '.join(missing)}\n"
            f"   Please fill them in the .env file at the project root."
        )
    print("✅ All environment variables are set.")

def main():
    validate_env()

    files = [f for f in os.listdir(DATA_DIR) if os.path.isfile(os.path.join(DATA_DIR, f))]
    if not files:
        print("⚠️  No files found in data/documents/")
        return

    print(f"\n📂 Found {len(files)} file(s) to process.\n")

    for file in files:
        file_path = os.path.join(DATA_DIR, file)
        print(f"{'='*50}")
        print(f"🔄 Processing: {file}")

        try:
            if file.endswith(".docx"):
                # DOCX: segment-based pipeline — each chunk gets only its own image
                segments, images = extract_docx_segments(file_path)
                print(f"   🖼️  Extracted {len(images)} image(s) from {len(segments)} segment(s)")

                path_to_url = upload_images_mapped(images, prefix=file)
                print(f"   ☁️  Uploaded {len(path_to_url)} image(s) to S3")

                chunks = create_chunks_from_segments(segments, path_to_url, source=file)
                print(f"   ✂️  Created {len(chunks)} text chunk(s)")
            else:
                # PDF / TXT / HTML: existing bulk pipeline
                documents = load_documents(file_path)
                print(f"   📄 Loaded {len(documents)} document chunk(s)")

                images = extract_images(file_path)
                print(f"   🖼️  Extracted {len(images)} image(s)")

                image_urls = upload_images(images, prefix=file)
                print(f"   ☁️  Uploaded {len(image_urls)} image(s) to S3")

                chunks = create_chunks(documents, image_urls, source=file)
                print(f"   ✂️  Created {len(chunks)} text chunk(s)")

            # 5. Generate embeddings
            embeddings = get_embeddings()

            # 6. Store in Pinecone
            upsert_vectors(chunks, embeddings)
            print(f"   📌 Upserted vectors to Pinecone")

            print(f"   ✅ Completed ingestion for: {file}")

        except ValueError as e:
            print(f"   ⚠️  Skipped {file}: {e}")
        except Exception as e:
            print(f"   ❌ Failed to process {file}: {e}")

    print(f"\n🎉 Ingestion pipeline finished.")

if __name__ == "__main__":
    main()
