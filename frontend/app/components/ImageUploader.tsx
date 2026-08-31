"use client";

import Image from "next/image";
import useProfileStore from "@/store/useProfileStore";
import { useLocation } from "@/hooks/useLocation";
import {
  ChangeEvent,
  DragEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { getMessages } from "../lib/i18n";
import { flushScanQueue } from "@/lib/syncManager";

/* ── Types ──────────────────────────────────────────────────────────── */
type CaptureMode = "file" | "camera";

interface ImageUploaderProps {
  onSelect: (
    file: File | null,
    comment: string,
    latitude?: number,
    longitude?: number,
  ) => void;
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

function dataURLtoFile(dataUrl: string, filename: string): File {
  const arr = dataUrl.split(",");
  const mimeMatch = arr[0].match(/:(.*?);/);
  const mime = mimeMatch ? mimeMatch[1] : "image/jpeg";
  const bstr = atob(arr[1]);
  let n = bstr.length;
  const u8arr = new Uint8Array(n);
  while (n--) {
    u8arr[n] = bstr.charCodeAt(n);
  }
  return new File([u8arr], filename, { type: mime });
}

/**
 * Rescales image down so neither width nor height exceeds 1024px while
 * maintaining aspect ratio, and exports as a JPEG with 0.7 quality.
 */
async function compressImage(
  fileOrBlob: Blob | File,
  filename?: string
): Promise<{ file: File; dataUrl: string }> {
  return new Promise((resolve, reject) => {
    const img = new window.Image();
    const objectUrl = URL.createObjectURL(fileOrBlob);

    img.onload = () => {
      URL.revokeObjectURL(objectUrl);
      let width = img.naturalWidth || img.width;
      let height = img.naturalHeight || img.height;
      const maxDim = 1024;

      if (width > maxDim || height > maxDim) {
        const ratio = Math.min(maxDim / width, maxDim / height);
        width = Math.round(width * ratio);
        height = Math.round(height * ratio);
      }

      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        reject(new Error("Failed to get 2D canvas context for compression."));
        return;
      }

      ctx.drawImage(img, 0, 0, width, height);
      const dataUrl = canvas.toDataURL("image/jpeg", 0.7);

      const baseName =
        filename ||
        (fileOrBlob instanceof File
          ? fileOrBlob.name.replace(/\.[^/.]+$/, "")
          : `scan-${Date.now()}`);
      const outFilename =
        baseName.endsWith(".jpg") || baseName.endsWith(".jpeg")
          ? baseName
          : `${baseName}.jpg`;

      const compressedFile = dataURLtoFile(dataUrl, outFilename);
      resolve({ file: compressedFile, dataUrl });
    };

    img.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      reject(new Error("Failed to load image for compression."));
    };

    img.src = objectUrl;
  });
}

/* ── Component ──────────────────────────────────────────────────────── */
export default function ImageUploader({
  onSelect,
  disabled = false,
}: ImageUploaderProps) {
  const { language } = useProfileStore();
  const msg = getMessages(language);
  const { location } = useLocation();

  const [mode, setMode] = useState<CaptureMode>("file");
  const [preview, setPreview] = useState<PreviewState | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [cameraError, setCameraError] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  /* ── Notify parent with lat/lng ─────────────────────────────────── */
  const notifyParent = useCallback(
    (file: File | null, currentComment: string) => {
      onSelect(
        file,
        currentComment,
        location?.lat,
        location?.lng,
      );
    },
    [onSelect, location],
  );

  /* ── Camera helpers ────────────────────────────────────────────── */
  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
  }, []);

  const startCamera = useCallback(async () => {
    setCameraError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } },
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
    } catch {
      setCameraError("Camera access denied or unavailable. Try file upload instead.");
    }
  }, []);

  /* ── Switch between modes ──────────────────────────────────────── */
  const switchMode = useCallback(
    (newMode: CaptureMode) => {
      if (newMode === mode) return;
      stopCamera();
      setCameraError(null);
      setMode(newMode);
    },
    [mode, stopCamera],
  );

  /* Start camera when mode becomes "camera" */
  useEffect(() => {
    if (mode === "camera" && !preview) {
      startCamera();
    }
    return () => {
      if (mode === "camera") {
        stopCamera();
      }
    };
  }, [mode, preview, startCamera, stopCamera]);

  /* Cleanup on unmount */
  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, [stopCamera]);

  /* ── Online queue flusher listener ── */
  useEffect(() => {
    const handleOnline = () => {
      void flushScanQueue(async (itemPayload) => {
        try {
          const form = new FormData();
          if (itemPayload.imageBlob instanceof Blob) {
            form.append("image", itemPayload.imageBlob, "scan.jpg");
          } else if (itemPayload.image instanceof Blob) {
            form.append("image", itemPayload.image, "scan.jpg");
          }
          if (itemPayload.cropType) form.append("crop_type", String(itemPayload.cropType));
          if (itemPayload.latitude !== undefined) form.append("latitude", String(itemPayload.latitude));
          if (itemPayload.longitude !== undefined) form.append("longitude", String(itemPayload.longitude));
          if (itemPayload.farmerComment) form.append("farmer_comment", String(itemPayload.farmerComment));
          if (itemPayload.language) form.append("language", String(itemPayload.language));
          const opContext =
            itemPayload.operational_context ||
            itemPayload.operationalContext ||
            itemPayload.context_mode ||
            itemPayload.contextMode;
          if (opContext) {
            form.append("operational_context", String(opContext));
          }

          const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
          const res = await fetch(`${apiBase}/api/scan`, {
            method: "POST",
            body: form,
          });
          return res.ok;
        } catch {
          return false;
        }
      });
    };

    window.addEventListener("online", handleOnline);
    return () => {
      window.removeEventListener("online", handleOnline);
    };
  }, []);

/* ── File handling ─────────────────────────────────────────────── */
  const applyFile = useCallback(
    async (file: File) => {
      if (!isValidType(file)) {
        setError("Only JPG, PNG, and WebP images are accepted.");
        return;
      }
      setError(null);
      stopCamera();

      try {
        const { file: compressedFile, dataUrl } = await compressImage(file, file.name);
        setPreview((prev) => {
          if (prev) URL.revokeObjectURL(prev.objectUrl);
          return { file: compressedFile, objectUrl: dataUrl };
        });
        notifyParent(compressedFile, comment);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to compress selected image."
        );
      }
    },
    [comment, notifyParent, stopCamera],
  );

  const clearFile = useCallback(() => {
    setPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev.objectUrl);
      return null;
    });
    if (inputRef.current) inputRef.current.value = "";
    notifyParent(null, comment);
  }, [comment, notifyParent]);

  /* ── Snap photo from live stream ───────────────────────────────── */
  const snapPhoto = useCallback(async () => {
    const video = videoRef.current;
    if (!video || !video.videoWidth || !video.videoHeight) return;

    let width = video.videoWidth;
    let height = video.videoHeight;
    const maxDim = 1024;

    if (width > maxDim || height > maxDim) {
      const ratio = Math.min(maxDim / width, maxDim / height);
      width = Math.round(width * ratio);
      height = Math.round(height * ratio);
    }

    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.drawImage(video, 0, 0, width, height);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.7);
    const compressedFile = dataURLtoFile(dataUrl, `scan-${Date.now()}.jpg`);

    stopCamera();
    setPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev.objectUrl);
      return { file: compressedFile, objectUrl: dataUrl };
    });
    notifyParent(compressedFile, comment);
  }, [comment, notifyParent, stopCamera]);

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
    notifyParent(preview?.file ?? null, val);
  };

  /* ── Render ────────────────────────────────────────────────────── */
  return (
    <div className="flex flex-col gap-4">
      {/* ── Mode toggle ── */}
      {!preview && (
        <div className="flex rounded-xl border border-emerald-200 bg-white p-1 self-start">
          <button
            type="button"
            onClick={() => switchMode("file")}
            className={`rounded-lg px-4 py-2 text-xs font-bold transition-colors ${
              mode === "file"
                ? "bg-emerald-50 text-emerald-700"
                : "bg-transparent text-slate-700 hover:bg-slate-50"
            }`}
            aria-pressed={mode === "file"}
          >
            📁 File Upload
          </button>
          <button
            type="button"
            onClick={() => switchMode("camera")}
            className={`rounded-lg px-4 py-2 text-xs font-bold transition-colors ${
              mode === "camera"
                ? "bg-emerald-50 text-emerald-700"
                : "bg-transparent text-slate-700 hover:bg-slate-50"
            }`}
            aria-pressed={mode === "camera"}
          >
            📷 Live Camera
          </button>
        </div>
      )}

      {/* ── Camera error ── */}
      {cameraError && mode === "camera" && (
        <p
          role="alert"
          className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium"
          style={{
            background: "color-mix(in srgb, #ef4444 10%, transparent)",
            color: "#b91c1c",
          }}
        >
          ⚠️ {cameraError}
        </p>
      )}

      {/* ── Live camera stream ── */}
      {mode === "camera" && !preview && !cameraError && (
        <div className="flex flex-col gap-3">
          <div className="relative overflow-hidden rounded-2xl border border-emerald-200 bg-slate-900 shadow-sm">
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className="h-64 w-full object-cover"
            />
          </div>
          <button
            type="button"
            onClick={snapPhoto}
            disabled={disabled}
            className="flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm font-bold text-white transition-all hover:brightness-110 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50"
            style={{ background: "var(--primary)" }}
          >
            <span aria-hidden="true">📸</span>
            Snap Photo
          </button>
        </div>
      )}

      {/* ── File drop zone ── */}
      {mode === "file" && !preview && (
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
            capture="environment"
            className="sr-only"
            disabled={disabled}
            onChange={handleInputChange}
          />
        </div>
      )}

      {/* ── Image preview ── */}
      {preview && (
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
