import io
import os
from pypdf import PdfReader


# Extracts plain text from raw bytes based on file format
def extract_text_from_bytes(content: bytes, filename: str) -> str:
    # Check if the file is a PDF
    if filename.lower().endswith(".pdf"):
        # Read the binary PDF stream page by page
        pdf_stream = io.BytesIO(content)
        reader = PdfReader(pdf_stream)
        pages_text = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                pages_text.append(page_text)
        text = "\n".join(pages_text).strip()
    else:
        # For text files, attempt UTF-8 decoding with Latin-1 fallback
        try:
            text = content.decode("utf-8").strip()
        except UnicodeDecodeError:
            # Fallback to Latin-1 for older or legacy character encodings
            text = content.decode("latin-1").strip()

    # Reject documents that contain no readable text content
    if not text:
        raise ValueError("Document is empty or contains no extractable text.")

    return text


# Reads a file from disk and extracts its text content
def extract_text_from_file(file_path: str) -> str:
    filename = os.path.basename(file_path)
    with open(file_path, "rb") as file_handle:
        content = file_handle.read()
    return extract_text_from_bytes(content, filename)
