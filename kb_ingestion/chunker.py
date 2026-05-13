
from langchain_text_splitters import RecursiveCharacterTextSplitter


def create_chunks(documents, image_urls, source):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150
    )

    chunks = []
    for doc in documents:
        for text in splitter.split_text(doc.page_content):
            chunks.append({
                "text": text,
                "metadata": {
                    "source": source,
                    "page": doc.metadata.get("page", 0),
                    "image_urls": image_urls
                }
            })
    return chunks


def create_chunks_from_segments(segments, path_to_url, source):
    """
    Create chunks from DOCX segments where each segment's images are associated
    only with the chunks derived from that segment's text.

    segments   – list of {"text": str, "images": list[str]}
    path_to_url – dict mapping local image path -> S3 URL
    source     – filename used as the source metadata field
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150
    )

    chunks = []
    for segment in segments:
        text = segment["text"]
        if not text.strip():
            continue

        # Resolve all image URLs for this segment (supports 0, 1, or multiple images per step)
        chunk_image_urls = [
            path_to_url[img]
            for img in segment.get("images", [])
            if img in path_to_url
        ]

        for chunk_text in splitter.split_text(text):
            chunks.append({
                "text": chunk_text,
                "metadata": {
                    "source": source,
                    "page": 0,
                    "image_urls": chunk_image_urls,
                    "image_order": "positioned",  # signals per-step image mapping
                }
            })

    return chunks
