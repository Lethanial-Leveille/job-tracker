// An inline PDF preview backed by an object URL.
//
// The problem it solves: every render used to build a Blob, create a hidden
// <a download>, and click it, so looking at a resume meant a file on disk. Now
// the Blob is shown in place and only reaches the filesystem when the user
// actually asks for it.
//
// Blob URLs are per-document handles, not network requests, so the server's
// `Content-Disposition: attachment` header does not apply here and the PDF
// renders inline. They also leak until revoked, which is what the effect's
// cleanup is for: one URL per blob, revoked when the blob changes or the
// component unmounts.

import { useEffect, useState } from "react";

interface Props {
  blob: Blob | null;
  /** Shown while a render is in flight, so the frame does not flash empty. */
  loading?: boolean;
  className?: string;
}

export function PdfPreview({ blob, loading = false, className = "" }: Props) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!blob) {
      setUrl(null);
      return;
    }
    const next = URL.createObjectURL(blob);
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [blob]);

  return (
    <div
      className={`relative overflow-hidden rounded-interactive border border-line bg-surface ${className}`}
    >
      {url ? (
        // `title` is required for accessibility; #view=FitH asks the viewer to
        // fit the page width, which is what makes a Letter page readable in a
        // narrow panel without the user zooming.
        <iframe
          src={`${url}#view=FitH`}
          title="Resume preview"
          className="h-full w-full"
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center p-6 text-center text-sm text-ink-soft">
          {loading ? "Rendering…" : "No preview yet."}
        </div>
      )}
      {loading && url ? (
        <div className="absolute inset-0 flex items-center justify-center bg-surface/70 text-sm text-ink-soft">
          Rendering…
        </div>
      ) : null}
    </div>
  );
}
