import pytest
from app.extractor import extract_text_from_bytes, extract_text_from_file

# Minimal valid single-page PDF containing extractable text
SAMPLE_PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>endobj\n"
    b"4 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"5 0 obj<</Length 44>>stream\n"
    b"BT /F1 12 Tf 72 712 Td (Vendor Agreement Text) Tj ET\n"
    b"endstream\nendobj\n"
    b"xref\n0 6\n"
    b"0000000000 65535 f \n"
    b"0000000009 00000 n \n"
    b"0000000052 00000 n \n"
    b"0000000101 00000 n \n"
    b"0000000212 00000 n \n"
    b"0000000274 00000 n \n"
    b"trailer<</Size 6/Root 1 0 R>>\n"
    b"startxref\n365\n%%EOF\n"
)


# Tests extracting plain UTF-8 text from raw bytes
def test_extract_plain_text():
    sample_content = b"This is a standard SaaS agreement between Acme and Vendor."
    text = extract_text_from_bytes(sample_content, "agreement.txt")
    assert text == "This is a standard SaaS agreement between Acme and Vendor."


# Tests fallback to Latin-1 when non-UTF-8 bytes are encountered
def test_extract_latin1_text():
    sample_content = "Contract with special accent café".encode("latin-1")
    text = extract_text_from_bytes(sample_content, "agreement.txt")
    assert "café" in text


# Tests extracting text from a binary PDF file
def test_extract_pdf():
    text = extract_text_from_bytes(SAMPLE_PDF_BYTES, "contract.pdf")
    assert "Vendor Agreement Text" in text


# Tests that an empty document raises a ValueError
def test_empty_document_raises_error():
    with pytest.raises(ValueError, match="empty or contains no extractable text"):
        extract_text_from_bytes(b"", "empty.txt")


# Tests that whitespace-only document raises a ValueError
def test_whitespace_document_raises_error():
    with pytest.raises(ValueError, match="empty or contains no extractable text"):
        extract_text_from_bytes(b"   \n\t  \r\n", "blank.txt")


# Tests reading a document directly from disk using a temporary file
def test_extract_from_file(tmp_path):
    temp_file = tmp_path / "contract.txt"
    temp_file.write_text("Master Agreement on disk", encoding="utf-8")

    text = extract_text_from_file(str(temp_file))
    assert text == "Master Agreement on disk"
