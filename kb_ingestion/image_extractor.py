import os
import fitz
from docx import Document

TMP_DIR = "tmp_images"

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
        # Walk body XML in visual order to get images in document sequence
        R_EMBED = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
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
