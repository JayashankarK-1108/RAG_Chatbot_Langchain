import os
import fitz
from docx import Document

TMP_DIR = "tmp_images"

R_EMBED = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
W_T = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"


def extract_images(file_path):
    os.makedirs(TMP_DIR, exist_ok=True)
    images = []

    if file_path.endswith(".pdf"):
        doc = fitz.open(file_path)
        for p in range(len(doc)):
            for i, img in enumerate(doc[p].get_images(full=True)):
                pix = fitz.Pixmap(doc, img[0])
                path = f"{TMP_DIR}/page{p}_{i}.png"
                pix.save(path)
                images.append(path)

    elif file_path.endswith(".docx"):
        doc = Document(file_path)
        seen = set()
        for elem in doc.element.body.iter():
            if not elem.tag.endswith("}blip"):
                continue
            rId = elem.get(R_EMBED)
            if not rId or rId in seen or rId not in doc.part.rels:
                continue
            seen.add(rId)
            rel = doc.part.rels[rId]
            if "image" not in rel.target_ref:
                continue
            name = os.path.basename(rel.target_ref)
            path = f"{TMP_DIR}/{name}"
            with open(path, "wb") as f:
                f.write(rel.target_part.blob)
            images.append(path)

    return images


def extract_docx_segments(file_path):
    """
    Walk the DOCX body in document order and build segments where each segment
    is a block of accumulated text followed by the image that immediately comes after it.

    Returns:
        segments  – list of {"text": str, "image": str | None}
        all_images – flat list of all extracted local image paths (for S3 upload)
    """
    os.makedirs(TMP_DIR, exist_ok=True)

    doc = Document(file_path)
    seen = set()
    segments = []
    all_images = []
    current_text_parts = []

    for child in doc.element.body:
        # Extract text from this top-level body element (paragraph or table)
        para_text = "".join(
            t.text for t in child.iter() if t.tag == W_T and t.text
        ).strip()

        # Check if this element contains an image
        image_path = None
        for blip in child.iter():
            if not blip.tag.endswith("}blip"):
                continue
            rId = blip.get(R_EMBED)
            if not rId or rId in seen or rId not in doc.part.rels:
                continue
            seen.add(rId)
            rel = doc.part.rels[rId]
            if "image" not in rel.target_ref:
                continue
            name = os.path.basename(rel.target_ref)
            path = f"{TMP_DIR}/{name}"
            with open(path, "wb") as f:
                f.write(rel.target_part.blob)
            image_path = path
            all_images.append(path)
            break  # one image per body element

        if para_text:
            current_text_parts.append(para_text)

        if image_path:
            # Finalize the current text block: this image belongs to the preceding text
            text = "\n".join(current_text_parts).strip()
            segments.append({"text": text, "image": image_path})
            current_text_parts = []

    # Any remaining text with no following image
    if current_text_parts:
        text = "\n".join(current_text_parts).strip()
        if text:
            segments.append({"text": text, "image": None})

    return segments, all_images
