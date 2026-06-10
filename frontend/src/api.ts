export interface Job {
  id: string;
  original_filename: string;
  source_format: string;
  target_format: string;
  status: "pending" | "converting" | "done" | "error";
  output_filename: string | null;
  file_size: number;
  error_message: string | null;
  created_at: string;
}

async function extractError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return body.detail ?? body.message ?? `HTTP ${res.status}`;
  } catch {
    return `HTTP ${res.status}`;
  }
}

export async function getFormats(): Promise<Record<string, string[]>> {
  const res = await fetch("/api/formats");
  if (!res.ok) throw new Error(await extractError(res));
  return res.json();
}

export function uploadFile(
  file: File,
  targetFormat: string,
  onProgress: (pct: number) => void,
  signal: AbortSignal,
): Promise<Job> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append("file", file);

    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable) onProgress((e.loaded / e.total) * 100);
    });

    xhr.addEventListener("load", () => {
      if (xhr.status === 201) {
        try {
          resolve(JSON.parse(xhr.responseText) as Job);
        } catch {
          reject(new Error("Invalid server response"));
        }
      } else if (xhr.status === 413) {
        reject(new Error("File is too large for this format."));
      } else if (xhr.status === 400) {
        try {
          const body = JSON.parse(xhr.responseText);
          reject(new Error(body.detail ?? "Invalid request"));
        } catch {
          reject(new Error("Invalid request"));
        }
      } else {
        reject(new Error(`Upload failed (HTTP ${xhr.status})`));
      }
    });

    xhr.addEventListener("error", () => reject(new Error("Network error during upload")));
    xhr.addEventListener("abort", () => reject(new DOMException("Upload cancelled", "AbortError")));

    signal.addEventListener("abort", () => xhr.abort());

    xhr.open("POST", `/api/files/upload?target_format=${encodeURIComponent(targetFormat)}`);
    xhr.send(form);
  });
}

export async function downloadFile(id: string): Promise<Blob> {
  const res = await fetch(`/api/files/${id}/download`);
  if (!res.ok) throw new Error(await extractError(res));
  return res.blob();
}