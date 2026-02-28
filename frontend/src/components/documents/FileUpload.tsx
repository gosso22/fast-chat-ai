import { useState, useRef } from 'react';
import type { DragEvent, ChangeEvent } from 'react';

interface FileUploadProps {
  onUpload: (file: File) => void;
  disabled?: boolean;
}

const ACCEPTED_FORMATS = ['.pdf', '.txt', '.docx', '.md'];
const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB

export function FileUpload({ onUpload, disabled = false }: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const validateFile = (file: File): string | null => {
    // Check file size
    if (file.size > MAX_FILE_SIZE) {
      return `File size exceeds 50MB limit (${(file.size / 1024 / 1024).toFixed(2)}MB)`;
    }

    // Check file format
    const extension = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!ACCEPTED_FORMATS.includes(extension)) {
      return `Invalid file format. Supported formats: ${ACCEPTED_FORMATS.join(', ')}`;
    }

    return null;
  };

  const handleFile = (file: File) => {
    setError(null);
    const validationError = validateFile(file);
    
    if (validationError) {
      setError(validationError);
      return;
    }

    onUpload(file);
  };

  const handleDragEnter = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (!disabled) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    if (disabled) return;

    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) {
      handleFile(files[0]);
    }
  };

  const handleFileSelect = (e: ChangeEvent<HTMLInputElement>) => {
    if (disabled) return;
    
    const files = e.target.files;
    if (files && files.length > 0) {
      handleFile(files[0]);
    }
    // Reset input value to allow selecting the same file again
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleClick = () => {
    if (!disabled) {
      fileInputRef.current?.click();
    }
  };

  return (
    <div>
      <div
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={handleClick}
        className={`
          border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors
          ${isDragging ? 'border-[#00E5FF] bg-cyan-50' : 'border-gray-300 hover:border-[#00E5FF]'}
          ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
        `}
        data-testid="file-upload-zone"
      >
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_FORMATS.join(',')}
          onChange={handleFileSelect}
          className="hidden"
          disabled={disabled}
          data-testid="file-input"
        />
        
        <svg
          className="mx-auto h-12 w-12 text-[#00E5FF]"
          stroke="currentColor"
          fill="none"
          viewBox="0 0 48 48"
          aria-hidden="true"
        >
          <path
            d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        
        <p className="mt-2 text-gray-600">
          {isDragging ? 'Drop file here' : 'Drag and drop files here, or click to select'}
        </p>
        <p className="text-sm text-gray-400 mt-2">
          Supports PDF, TXT, DOCX, and Markdown files (max 50MB)
        </p>
      </div>

      {error && (
        <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-md" data-testid="upload-error">
          <p className="text-sm text-red-600">{error}</p>
        </div>
      )}
    </div>
  );
}
