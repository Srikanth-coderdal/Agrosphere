"use client";

import Image from "next/image";
import {
  ChangeEvent,
  DragEvent,
  useCallback,
  useRef,
  useState,
} from "react";
import { useLanguage } from "../lib/useLanguage";
import { getMessages } from "../lib/i18n";

/* ── Types ──────────────────────────────────────────────────────────── */
interface ImageUploaderProps {
  onSelect: (file: File | null, comment: string) => void;
  disabled?: boolean;
}

interface PreviewState {
  file: File;
  objectUrl: string;
}

/* ── Helpers ────────────────────────────────────────────────────────── */
const ACCEPTED = ["image/jpeg", "image/png", "image/webp"];
const ACCEPT_ATTR = ".jpg,.jpeg,.png,.webp";

function formatSize(bytes: number): string {
  if (bytes >= 1_048_576) return `${(bytes / 1_048_576).toFixed(2)} MB`;
  return `${(bytes / 1024).toFixed(1)} KB`;
}

function isValidType(file: File): boolean {
  return ACCEPTED.includes(file.type);
}

/* ── Component ──────────────────────────────────────────────────────── */
export default function ImageUploader({
  onSelect,
  disabled = false,
}: ImageUploaderProps) {
  const { language } = useLanguage();
  const msg = getMessages(language);

  const [preview, setPreview] = useState<PreviewState | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  /* ── File handling ─────────────────────────────────────────────── */
  const applyFile = useCallback(
    (file: File) => {
      if (!isValidType(file)) {
        setError("Only JPG, PNG, and WebP images are accepted.");
        return;
      }
      setError(null);
      // Revoke previous blob URL to avoid memory leaks
      setPreview((prev) => {
        if (prev) URL.revokeObjectURL(prev.objectUrl);
        return { file, objectUrl: URL.createObjectURL(file) };
      });
      onSelect(file, comment);
    },
    [comment, onSelect],
  );

  const clearFile = useCallback(() => {
    setPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev.objectUrl);
      return null;
    });
    if (inputRef.current) inputRef.current.value = "";
    onSelect(null, comment);
  }, [comment, onSelect]);

  /* ── Input change ──────────────────────────────────────────────── */
  const handleInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) applyFile(file);
  };

  /* ── Drag events ───────────────────────────────────────────────── */
  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (!disabled) setDragOver(true);
  };

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
    if (disabled) return;
    const file = e.dataTransfer.files?.[0];
    if (file) applyFile(file);
  };

  /* ── Comment change ────────────────────────────────────────────── */
  const handleCommentChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setComment(val);
    onSelect(preview?.file ?? null, val);
  };

  /* ── Render ────────────────────────────────────────────────────── */
  return (
    <div className="flex flex-col gap-4">
      {/* ── Drop zone / Preview ── */}
      {!preview ? (
        <div
          role="button"
          tabIndex={disabled ? -1 : 0}
          aria-label="Image upload drop zone"
          aria-disabled={disabled}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => !disabled && inputRef.current?.click()}
          onKeyDown={(e) => {
            if (!disabled && (e.key === "Enter" || e.key === " ")) {
              e.preventDefault();
              inputRef.current?.click();
            }
          }}
          className={[
            "flex flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed px-6 py-12 text-center transition-colors duration-200",
            dragOver
              ? "border-emerald-500 bg-emerald-100/70"
              : "border-emerald-300 bg-emerald-50/50 hover:bg-emerald-50",
            disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer",
          ].join(" ")}
        >
          {/* Upload icon */}
          <span className="text-5xl" aria-hidden="true">🖼️</span>

          <p className="text-base font-semibold" style={{ color: "var(--primary)" }}>
            {dragOver ? msg.scan.uploader.dropLabel : msg.scan.uploader.dragLabel}
          </p>
          <p className="text-sm" style={{ color: "var(--foreground)", opacity: 0.55 }}>
            {msg.scan.uploader.browseLabel}
          </p>
          <p className="text-xs" style={{ color: "var(--foreground)", opacity: 0.4 }}>
            {msg.scan.uploader.acceptedLabel}
          </p>

          {/* Hidden file input */}
          <input
            ref={inputRef}
            id="image-upload-input"
            type="file"
            accept={ACCEPT_ATTR}
            className="sr-only"
            disabled={disabled}
            onChange={handleInputChange}
          />
        </div>
      ) : (
        /* ── Live preview ── */
        <div className="flex flex-col gap-2">
          <div className="relative overflow-hidden rounded-2xl border border-emerald-200 bg-slate-100 shadow-sm">
            <Image
              src={preview.objectUrl}
              alt={`Preview of ${preview.file.name}`}
              width={800}
              height={450}
              className="h-64 w-full object-cover"
              unoptimized
            />

            {/* Remove button overlay */}
            <button
              type="button"
              onClick={clearFile}
              disabled={disabled}
              aria-label="Remove selected image"
              className={[
                "absolute right-3 top-3 flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold shadow-md transition-opacity",
                "bg-white/90 backdrop-blur-sm hover:bg-white",
                disabled ? "cursor-not-allowed opacity-40" : "cursor-pointer",
              ].join(" ")}
              style={{ color: "var(--primary)" }}
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-3.5 w-3.5"
                viewBox="0 0 20 20"
                fill="currentColor"
                aria-hidden="true"
              >
                <path
                  fillRule="evenodd"
                  d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                  clipRule="evenodd"
                />
              </svg>
              {msg.scan.uploader.removeChange}
            </button>
          </div>

          {/* File metadata */}
          <div className="flex items-center gap-3 px-1 text-xs" style={{ opacity: 0.6 }}>
            <span aria-label="File name" className="truncate font-medium">
              📄 {preview.file.name}
            </span>
            <span aria-label="File size" className="shrink-0">
              {formatSize(preview.file.size)}
            </span>
          </div>
        </div>
      )}

      {/* ── Validation error ── */}
      {error && (
        <p
          role="alert"
          className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium"
          style={{
            background: "color-mix(in srgb, #ef4444 10%, transparent)",
            color: "#b91c1c",
          }}
        >
          ⚠️ {error}
        </p>
      )}

      {/* ── Farmer comment ── */}
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="farmer-comment"
          className="text-sm font-semibold"
          style={{ color: "var(--foreground)" }}
        >
          Farmer Notes / Symptoms{" "}
          <span className="font-normal opacity-50">(Optional)</span>
        </label>
        <textarea
          id="farmer-comment"
          rows={3}
          value={comment}
          onChange={handleCommentChange}
          disabled={disabled}
          placeholder="e.g., Yellow spots appearing on lower leaves for 3 days..."
          className={[
            "w-full resize-y rounded-xl border px-4 py-3 text-sm text-slate-900 outline-none transition-colors duration-150 placeholder:opacity-40",
            "border-emerald-200 bg-white focus:border-emerald-500 focus:ring-2",
            disabled ? "cursor-not-allowed opacity-50" : "",
          ].join(" ")}
          style={
            {
              color: "var(--foreground)",
              "--tw-ring-color": "color-mix(in srgb, var(--primary) 25%, transparent)",
            } as React.CSSProperties
          }
        />
      </div>
    </div>
  );
}
