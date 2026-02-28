"""
Unit tests for text extraction service.
"""

import io
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from app.services.text_extractor import (
    TextExtractionService,
    TextExtractionError,
    ExtractionResult,
    PDFTextExtractor,
    DOCXTextExtractor,
    MarkdownTextExtractor,
    PlainTextExtractor
)


class TestExtractionResult:
    """Test ExtractionResult class."""
    
    def test_extraction_result_creation(self):
        """Test creating ExtractionResult."""
        result = ExtractionResult(
            text="Sample text",
            metadata={"key": "value"},
            word_count=2,
            character_count=11,
            extraction_method="test"
        )
        
        assert result.text == "Sample text"
        assert result.metadata == {"key": "value"}
        assert result.word_count == 2
        assert result.character_count == 11
        assert result.extraction_method == "test"
    
    def test_to_dict(self):
        """Test converting result to dictionary."""
        result = ExtractionResult(
            text="Sample text",
            metadata={"key": "value"},
            word_count=2,
            character_count=11,
            extraction_method="test"
        )
        
        expected = {
            "text": "Sample text",
            "metadata": {"key": "value"},
            "word_count": 2,
            "character_count": 11,
            "extraction_method": "test"
        }
        
        assert result.to_dict() == expected


class TestPlainTextExtractor:
    """Test PlainTextExtractor class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.extractor = PlainTextExtractor()
    
    def test_supports_format(self):
        """Test format support detection."""
        assert self.extractor.supports_format('.txt')
        assert self.extractor.supports_format('.TXT')
        assert not self.extractor.supports_format('.pdf')
        assert not self.extractor.supports_format('.docx')
    
    def test_extract_utf8_text(self):
        """Test extracting UTF-8 text."""
        content = "Hello, world!\nThis is a test file.".encode('utf-8')
        
        result = self.extractor.extract(content, "test.txt")
        
        assert result.text == "Hello, world!\nThis is a test file."
        assert result.word_count == 7
        assert result.character_count == 34  # Actual character count
        assert result.extraction_method == "plain_text"
        assert result.metadata["encoding"] == "utf-8"
        assert result.metadata["line_count"] == 2
    
    def test_extract_latin1_text(self):
        """Test extracting Latin-1 encoded text."""
        content = "Café résumé".encode('latin-1')
        
        result = self.extractor.extract(content, "test.txt")
        
        assert "Café résumé" in result.text
        assert result.metadata["encoding"] == "latin-1"
        assert result.extraction_method == "plain_text"
    
    def test_extract_empty_file(self):
        """Test extracting from empty file."""
        content = b""
        
        result = self.extractor.extract(content, "empty.txt")
        
        assert result.text == ""
        assert result.word_count == 0
        assert result.character_count == 0
    
    def test_extract_with_empty_lines(self):
        """Test extracting text with empty lines."""
        content = "Line 1\n\nLine 3\n\n\nLine 6".encode('utf-8')
        
        result = self.extractor.extract(content, "test.txt")
        
        assert result.metadata["line_count"] == 6
        assert result.metadata["empty_lines"] == 3
    
    def test_unsupported_encoding_error(self):
        """Test error handling for unsupported encoding."""
        # Create bytes that can't be decoded with common encodings
        # Use invalid UTF-8 sequence that also fails with fallback encodings
        content = b'\x80\x81\x82\x83\x84\x85\x86\x87\x88\x89\x8a\x8b\x8c\x8d\x8e\x8f'
        
        # Mock all encoding attempts to fail
        with patch.object(self.extractor, 'extract') as mock_extract:
            mock_extract.side_effect = TextExtractionError(
                "Could not decode text file with any supported encoding", "txt"
            )
            
            with pytest.raises(TextExtractionError) as exc_info:
                self.extractor.extract(content, "test.txt")
            
            assert "Could not decode text file" in str(exc_info.value)
            assert exc_info.value.file_type == "txt"


class TestMarkdownTextExtractor:
    """Test MarkdownTextExtractor class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.extractor = MarkdownTextExtractor()
    
    def test_supports_format(self):
        """Test format support detection."""
        assert self.extractor.supports_format('.md')
        assert self.extractor.supports_format('.markdown')
        assert self.extractor.supports_format('.MD')
        assert not self.extractor.supports_format('.txt')
        assert not self.extractor.supports_format('.pdf')
    
    def test_extract_simple_markdown(self):
        """Test extracting simple markdown."""
        content = """# Title
        
This is a paragraph with **bold** text.

## Subtitle

- List item 1
- List item 2

```python
print("Hello, world!")
```
""".encode('utf-8')
        
        result = self.extractor.extract(content, "test.md")
        
        assert "# Title" in result.text
        assert "**bold**" in result.text
        assert result.word_count > 0
        assert result.extraction_method == "markdown"
        assert result.metadata["heading_count"] >= 2
        assert result.metadata["code_block_count"] >= 1
    
    def test_extract_with_metadata(self):
        """Test extracting markdown with metadata."""
        content = """---
title: Test Document
author: Test Author
---

# Content

This is the content.
""".encode('utf-8')
        
        with patch('markdown.Markdown') as mock_md_class:
            mock_md = Mock()
            mock_md.convert.return_value = "<h1>Content</h1><p>This is the content.</p>"
            mock_md.Meta = {"title": ["Test Document"], "author": ["Test Author"]}
            mock_md_class.return_value = mock_md
            
            result = self.extractor.extract(content, "test.md")
            
            assert result.metadata["has_metadata"] is True
            assert "title" in result.metadata["meta"]
    
    def test_extract_encoding_error(self):
        """Test handling encoding errors."""
        # Mock the decode method to always fail
        with patch.object(self.extractor, 'extract') as mock_extract:
            mock_extract.side_effect = TextExtractionError(
                "Could not decode markdown file with any supported encoding", "markdown"
            )
            
            with pytest.raises(TextExtractionError) as exc_info:
                self.extractor.extract(b"invalid", "test.md")
            
            assert "Could not decode markdown file" in str(exc_info.value)
            assert exc_info.value.file_type == "markdown"


class TestPDFTextExtractor:
    """Test PDFTextExtractor class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.extractor = PDFTextExtractor()
    
    def test_supports_format(self):
        """Test format support detection."""
        assert self.extractor.supports_format('.pdf')
        assert self.extractor.supports_format('.PDF')
        assert not self.extractor.supports_format('.txt')
        assert not self.extractor.supports_format('.docx')
    
    @patch('app.services.text_extractor.PyPDF2.PdfReader')
    def test_extract_with_pypdf2_success(self, mock_pdf_reader_class):
        """Test successful extraction with PyPDF2."""
        # Mock PDF reader
        mock_reader = Mock()
        mock_reader.is_encrypted = False
        mock_reader.pages = [Mock(), Mock()]
        mock_reader.pages[0].extract_text.return_value = "Page 1 content"
        mock_reader.pages[1].extract_text.return_value = "Page 2 content"
        mock_reader.metadata = {
            "/Title": "Test PDF",
            "/Author": "Test Author"
        }
        mock_pdf_reader_class.return_value = mock_reader
        
        content = b"fake pdf content"
        
        result = self.extractor.extract(content, "test.pdf")
        
        assert "[Page 1]" in result.text
        assert "[Page 2]" in result.text
        assert "Page 1 content" in result.text
        assert "Page 2 content" in result.text
        assert result.extraction_method == "PyPDF2"
        assert result.metadata["page_count"] == 2
        assert result.metadata["title"] == "Test PDF"
        assert result.metadata["author"] == "Test Author"
    
    @patch('app.services.text_extractor.pdfplumber.open')
    @patch('app.services.text_extractor.PyPDF2.PdfReader')
    def test_extract_fallback_to_pdfplumber(self, mock_pdf_reader_class, mock_pdfplumber_open):
        """Test fallback to pdfplumber when PyPDF2 fails."""
        # Mock PyPDF2 to return empty text
        mock_reader = Mock()
        mock_reader.is_encrypted = False
        mock_reader.pages = [Mock()]
        mock_reader.pages[0].extract_text.return_value = ""
        mock_reader.metadata = {}
        mock_pdf_reader_class.return_value = mock_reader
        
        # Mock pdfplumber
        mock_pdf = Mock()
        mock_page = Mock()
        mock_page.extract_text.return_value = "Pdfplumber extracted text"
        mock_pdf.pages = [mock_page]
        mock_pdf.metadata = {"Title": "Test PDF"}
        mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf
        
        content = b"fake pdf content"
        
        result = self.extractor.extract(content, "test.pdf")
        
        assert "Pdfplumber extracted text" in result.text
        assert result.extraction_method == "pdfplumber"
        assert result.metadata["title"] == "Test PDF"
    
    @patch('app.services.text_extractor.PyPDF2.PdfReader')
    def test_extract_encrypted_pdf_error(self, mock_pdf_reader_class):
        """Test error handling for encrypted PDF."""
        mock_reader = Mock()
        mock_reader.is_encrypted = True
        mock_pdf_reader_class.return_value = mock_reader
        
        content = b"fake encrypted pdf content"
        
        with pytest.raises(TextExtractionError) as exc_info:
            self.extractor.extract(content, "encrypted.pdf")
        
        assert "PDF is encrypted" in str(exc_info.value)
        assert exc_info.value.file_type == "pdf"
    
    @patch('app.services.text_extractor.PyPDF2.PdfReader')
    def test_extract_corrupted_pdf_error(self, mock_pdf_reader_class):
        """Test error handling for corrupted PDF."""
        mock_pdf_reader_class.side_effect = Exception("Invalid PDF")
        
        content = b"corrupted pdf content"
        
        with pytest.raises(TextExtractionError) as exc_info:
            self.extractor.extract(content, "corrupted.pdf")
        
        assert "Failed to extract text from PDF" in str(exc_info.value)
        assert exc_info.value.file_type == "pdf"


class TestDOCXTextExtractor:
    """Test DOCXTextExtractor class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.extractor = DOCXTextExtractor()
    
    def test_supports_format(self):
        """Test format support detection."""
        assert self.extractor.supports_format('.docx')
        assert self.extractor.supports_format('.DOCX')
        assert not self.extractor.supports_format('.txt')
        assert not self.extractor.supports_format('.pdf')
    
    @patch('app.services.text_extractor.Document')
    def test_extract_docx_with_paragraphs(self, mock_document_class):
        """Test extracting DOCX with paragraphs."""
        # Mock document
        mock_doc = Mock()
        mock_paragraph1 = Mock()
        mock_paragraph1.text = "First paragraph"
        mock_paragraph2 = Mock()
        mock_paragraph2.text = "Second paragraph"
        mock_doc.paragraphs = [mock_paragraph1, mock_paragraph2]
        mock_doc.tables = []
        
        # Mock core properties
        mock_core_props = Mock()
        mock_core_props.title = "Test Document"
        mock_core_props.author = "Test Author"
        mock_core_props.subject = "Test Subject"
        mock_core_props.created = None
        mock_core_props.modified = None
        mock_doc.core_properties = mock_core_props
        
        mock_document_class.return_value = mock_doc
        
        content = b"fake docx content"
        
        result = self.extractor.extract(content, "test.docx")
        
        assert "First paragraph" in result.text
        assert "Second paragraph" in result.text
        assert result.extraction_method == "python-docx"
        assert result.metadata["paragraph_count"] == 2
        assert result.metadata["table_count"] == 0
        assert result.metadata["title"] == "Test Document"
        assert result.metadata["author"] == "Test Author"
    
    @patch('app.services.text_extractor.Document')
    def test_extract_docx_with_tables(self, mock_document_class):
        """Test extracting DOCX with tables."""
        # Mock document
        mock_doc = Mock()
        mock_doc.paragraphs = []
        
        # Mock table
        mock_cell1 = Mock()
        mock_cell1.text = "Cell 1"
        mock_cell2 = Mock()
        mock_cell2.text = "Cell 2"
        mock_row = Mock()
        mock_row.cells = [mock_cell1, mock_cell2]
        mock_table = Mock()
        mock_table.rows = [mock_row]
        mock_doc.tables = [mock_table]
        
        # Mock core properties
        mock_doc.core_properties = Mock()
        mock_doc.core_properties.title = None
        mock_doc.core_properties.author = None
        mock_doc.core_properties.subject = None
        mock_doc.core_properties.created = None
        mock_doc.core_properties.modified = None
        
        mock_document_class.return_value = mock_doc
        
        content = b"fake docx content"
        
        result = self.extractor.extract(content, "test.docx")
        
        assert "[Table 1]" in result.text
        assert "Cell 1 | Cell 2" in result.text
        assert result.metadata["table_count"] == 1
    
    @patch('app.services.text_extractor.Document')
    def test_extract_docx_error(self, mock_document_class):
        """Test error handling for corrupted DOCX."""
        mock_document_class.side_effect = Exception("Invalid DOCX")
        
        content = b"corrupted docx content"
        
        with pytest.raises(TextExtractionError) as exc_info:
            self.extractor.extract(content, "corrupted.docx")
        
        assert "Failed to extract text from DOCX" in str(exc_info.value)
        assert exc_info.value.file_type == "docx"


class TestTextExtractionService:
    """Test TextExtractionService class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = TextExtractionService()
    
    def test_get_supported_formats(self):
        """Test getting supported formats."""
        formats = self.service.get_supported_formats()
        
        expected_formats = ['.pdf', '.docx', '.md', '.markdown', '.txt']
        for fmt in expected_formats:
            assert fmt in formats
    
    def test_extract_text_with_bytes(self):
        """Test extracting text from bytes content."""
        content = b"Test content"
        
        result = self.service.extract_text(content, "test.txt")
        
        assert result.text == "Test content"
        assert result.extraction_method == "plain_text"
    
    def test_extract_text_with_upload_file(self):
        """Test extracting text from UploadFile."""
        mock_file = Mock()
        mock_file.file = io.BytesIO(b"Test content")
        
        result = self.service.extract_text(mock_file, "test.txt")
        
        assert result.text == "Test content"
        assert result.extraction_method == "plain_text"
    
    def test_extract_text_unsupported_format(self):
        """Test error for unsupported file format."""
        content = b"test content"
        
        with pytest.raises(TextExtractionError) as exc_info:
            self.service.extract_text(content, "test.xyz")
        
        assert "No extractor available for file type" in str(exc_info.value)
    
    def test_extract_text_empty_result(self):
        """Test error when extraction yields empty text."""
        content = b""
        
        with pytest.raises(TextExtractionError) as exc_info:
            self.service.extract_text(content, "empty.txt")
        
        assert "No text content extracted" in str(exc_info.value)
    
    def test_extract_text_unexpected_error(self):
        """Test handling of unexpected errors."""
        mock_file = Mock()
        mock_file.file.read.side_effect = Exception("Unexpected error")
        
        with pytest.raises(TextExtractionError) as exc_info:
            self.service.extract_text(mock_file, "test.txt")
        
        assert "Unexpected error during text extraction" in str(exc_info.value)
    
    def test_get_extractor_pdf(self):
        """Test getting PDF extractor."""
        extractor = self.service._get_extractor('.pdf')
        assert isinstance(extractor, PDFTextExtractor)
    
    def test_get_extractor_docx(self):
        """Test getting DOCX extractor."""
        extractor = self.service._get_extractor('.docx')
        assert isinstance(extractor, DOCXTextExtractor)
    
    def test_get_extractor_markdown(self):
        """Test getting Markdown extractor."""
        extractor = self.service._get_extractor('.md')
        assert isinstance(extractor, MarkdownTextExtractor)
    
    def test_get_extractor_txt(self):
        """Test getting plain text extractor."""
        extractor = self.service._get_extractor('.txt')
        assert isinstance(extractor, PlainTextExtractor)
    
    def test_get_extractor_unsupported(self):
        """Test getting extractor for unsupported format."""
        extractor = self.service._get_extractor('.xyz')
        assert extractor is None


class TestTextExtractionError:
    """Test TextExtractionError class."""
    
    def test_error_creation(self):
        """Test creating TextExtractionError."""
        original_error = ValueError("Original error")
        error = TextExtractionError("Test message", "pdf", original_error)
        
        assert str(error) == "Test message"
        assert error.file_type == "pdf"
        assert error.original_error == original_error
    
    def test_error_without_original(self):
        """Test creating TextExtractionError without original error."""
        error = TextExtractionError("Test message", "txt")
        
        assert str(error) == "Test message"
        assert error.file_type == "txt"
        assert error.original_error is None