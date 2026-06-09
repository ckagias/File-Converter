export interface Job {
  id: number;
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

export async function uploadFile(file: File, targetFormat: string): Promise<Job> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`/api/files/upload?target_format=${encodeURIComponent(targetFormat)}`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(await extractError(res));
  return res.json();
}

export async function downloadFile(id: number): Promise<Blob> {
  const res = await fetch(`/api/files/${id}/download`);
  if (!res.ok) throw new Error(await extractError(res));
  return res.blob();
}