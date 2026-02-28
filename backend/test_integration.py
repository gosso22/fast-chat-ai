#!/usr/bin/env python3
"""
Simple integration test for text extraction service.
"""

import io
from app.services.text_extractor import TextExtractionService

def test_text_extraction_integration():
    """Test that text extraction service works with different file types."""
    service = TextExtractionService()
    
    # Test plain text
    txt_content = b"Hello, world!\nThis is a test document."
    result = service.extract_text(txt_content, "test.txt")
    print(f"TXT extraction: {result.word_count} words, method: {result.extraction_method}")
    assert result.text.strip() == "Hello, world!\nThis is a test document."
    
    # Test markdown
    md_content = b"""# Test Document
    
This is a **markdown** document with:
- List items
- More items

## Section 2
Some more content.
"""
    result = service.extract_text(md_content, "test.md")
    print(f"MD extraction: {result.word_count} words, method: {result.extraction_method}")
    assert "# Test Document" in result.text
    assert result.metadata["heading_count"] >= 2
    
    # Test supported formats
    formats = service.get_supported_formats()
    print(f"Supported formats: {formats}")
    expected_formats = ['.pdf', '.docx', '.md', '.markdown', '.txt']
    for fmt in expected_formats:
        assert fmt in formats
    
    print("✅ All integration tests passed!")

if __name__ == "__main__":
    test_text_extraction_integration()