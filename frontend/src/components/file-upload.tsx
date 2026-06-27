"use client";

import { useCallback, useRef, useState } from "react";
import { cn } from "@/lib/utils";

export interface FileUploadProps {
  onUpload: (file: File, fieldName: string) => void;
  fieldName: string;
  label: string;
  accept?: string;
}

/**
 * Drag-and-drop file upload component with click-to-browse fallback.
 * Shows the selected file name and validates against accepted types.
 */
export function FileUpload({
  onUpload,
  fieldName,
  label,
  accept,
}: FileUploadProps) {
  const [fileName, setFileName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const validateAndUpload = useCallback(
    (file: File) => {
      setError(null);

      // Validate against accept types if provided
      if (accept) {
        const acceptedTypes = accept.split(",").map((t) => t.trim());
        const fileType = file.type;
        const fileExt = `.${file.name.split(".").pop()?.toLowerCase()}`;

        const isValid = acceptedTypes.some((accepted) => {
          if (accepted.startsWith(".")) {
            return fileExt === accepted.toLowerCase();
          }
          if (accepted.endsWith("/*")) {
            return fileType.startsWith(accepted.replace("/*", "/"));
          }
          return fileType === accepted;
        });

        if (!isValid) {
          setError(`Invalid file type. Accepted: ${accept}`);
          setFileName(null);
          return;
        }
      }

      // Validate file size (max 10MB)
      const maxSize = 10 * 1024 * 1024;
      if (file.size > maxSize) {
        setError("File size exceeds 10MB limit.");
        setFileName(null);
        return;
      }

      if (file.size === 0) {
        setError("File is empty.");
        setFileName(null);
        return;
      }

      setFileName(file.name);
      onUpload(file, fieldName);
    },
    [accept, fieldName, onUpload]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDragOver(false);

      const file = e.dataTransfer.files[0];
      if (file) {
        validateAndUpload(file);
      }
    },
    [validateAndUpload]
  );

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(false);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      validateAndUpload(file);
    }
  };

  const handleClick = () => {
    inputRef.current?.click();
  };

  return (
    <div className="w-full">
      <label className="block text-sm font-medium text-foreground mb-1.5">
        {label}
      </label>

      <div
        onClick={handleClick}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            handleClick();
          }
        }}
        className={cn(
          "relative flex flex-col items-center justify-center rounded-lg border-2 border-dashed px-4 py-6 cursor-pointer transition-colors",
          isDragOver
            ? "border-blue-400 bg-blue-50"
            : "border-border hover:border-primary/50 hover:bg-muted/50",
          error && "border-red-300 bg-red-50/50"
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          onChange={handleFileChange}
          className="sr-only"
          aria-label={label}
        />

        <svg
          className="w-8 h-8 text-muted-foreground mb-2"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
          />
        </svg>

        {fileName ? (
          <p className="text-sm text-foreground font-medium">{fileName}</p>
        ) : (
          <p className="text-sm text-muted-foreground text-center">
            <span className="font-medium text-primary">Click to upload</span>{" "}
            or drag and drop
          </p>
        )}

        {accept && !fileName && (
          <p className="mt-1 text-xs text-muted-foreground">{accept}</p>
        )}
      </div>

      {error && (
        <p className="mt-1.5 text-xs text-red-600" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
