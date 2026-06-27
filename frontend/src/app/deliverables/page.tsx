"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiClient, ApiError } from "@/lib/api";
import type { FileInfo } from "@/lib/types";

/**
 * Formats a file size in bytes to a human-readable string.
 */
function formatFileSize(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const size = (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0);
  return `${size} ${units[i]}`;
}

/**
 * Returns a file type icon/emoji based on the file extension.
 */
function getFileIcon(filename: string): string {
  const ext = filename.split(".").pop()?.toLowerCase();
  switch (ext) {
    case "md":
      return "📄";
    case "py":
      return "🐍";
    case "ts":
    case "tsx":
    case "js":
    case "jsx":
      return "📜";
    case "json":
      return "📋";
    case "pptx":
      return "📊";
    case "mp4":
      return "🎬";
    case "pdf":
      return "📕";
    case "txt":
      return "📝";
    default:
      return "📁";
  }
}

export default function DeliverablesPage() {
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);

  useEffect(() => {
    async function fetchDeliverables() {
      try {
        const response = await apiClient.getDeliverables();
        setFiles(response.files);
      } catch (err) {
        if (err instanceof ApiError) {
          setError(`Failed to load deliverables: ${err.detail}`);
        } else {
          setError("Failed to load deliverables. Please try again.");
        }
      } finally {
        setLoading(false);
      }
    }

    fetchDeliverables();
  }, []);

  async function handleDownload(file: FileInfo) {
    setDownloading(file.path);
    try {
      const blob = await apiClient.getDeliverable(file.path);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = file.filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      if (err instanceof ApiError) {
        alert(`Download failed: ${err.detail}`);
      } else {
        alert("Download failed. Please try again.");
      }
    } finally {
      setDownloading(null);
    }
  }

  return (
    <main className="min-h-screen bg-gray-50 p-6 md:p-10">
      <div className="mx-auto max-w-4xl">
        {/* Header */}
        <div className="mb-8">
          <Link
            href="/"
            className="text-sm text-blue-600 hover:text-blue-800 hover:underline"
          >
            ← Back to Dashboard
          </Link>
          <h1 className="mt-4 text-3xl font-bold tracking-tight text-gray-900">
            Deliverables
          </h1>
          <p className="mt-2 text-gray-600">
            Download all generated artifacts from your hackathon project.
          </p>
        </div>

        {/* Loading State */}
        {loading && (
          <div className="flex flex-col items-center justify-center rounded-lg border border-gray-200 bg-white p-12">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
            <p className="mt-4 text-gray-500">Loading deliverables...</p>
          </div>
        )}

        {/* Error State */}
        {error && !loading && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-6">
            <p className="text-red-700">{error}</p>
          </div>
        )}

        {/* Empty State */}
        {!loading && !error && files.length === 0 && (
          <div className="flex flex-col items-center justify-center rounded-lg border border-gray-200 bg-white p-12 text-center">
            <span className="text-4xl">📦</span>
            <h2 className="mt-4 text-lg font-medium text-gray-900">
              No deliverables yet
            </h2>
            <p className="mt-2 text-gray-500">
              Deliverables will appear here once the delivery phase is complete.
            </p>
            <Link
              href="/monitor"
              className="mt-4 text-sm text-blue-600 hover:underline"
            >
              Check progress on the monitoring dashboard →
            </Link>
          </div>
        )}

        {/* File List */}
        {!loading && !error && files.length > 0 && (
          <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
            <ul className="divide-y divide-gray-200">
              {files.map((file) => (
                <li
                  key={file.path}
                  className="flex items-center justify-between gap-4 px-6 py-4 hover:bg-gray-50"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="text-xl" aria-hidden="true">
                      {getFileIcon(file.filename)}
                    </span>
                    <div className="min-w-0">
                      <p className="truncate font-medium text-gray-900">
                        {file.filename}
                      </p>
                      <p className="text-sm text-gray-500">
                        {formatFileSize(file.size)}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => handleDownload(file)}
                    disabled={downloading === file.path}
                    className="shrink-0 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {downloading === file.path ? "Downloading..." : "Download"}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </main>
  );
}
