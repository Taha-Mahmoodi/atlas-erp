/**
 * Background-job polling (STRUCTURE §4 `lib/`: framework-agnostic core) — mirrors the
 * backend's own core/jobs split: any module's long-running operation returns a job id that
 * polls the same `/api/v1/jobs/{id}` surface, so this stays here rather than under a
 * business module.
 */

import { api } from "@/lib/apiClient";

export type JobStatus = "PENDING" | "RUNNING" | "COMPLETED" | "FAILED";

/** The 202 body of an endpoint that backgrounds its work — poll getJob(job_id) until done. */
export interface JobSubmitted {
  job_id: string;
  status: JobStatus;
}

export interface Job<TResult = Record<string, unknown>> {
  id: string;
  job_type: string;
  status: JobStatus;
  result: TResult | null;
  error: string | null;
  created_at: string;
}

export function getJob<TResult = Record<string, unknown>>(jobId: string): Promise<Job<TResult>> {
  return api.get<Job<TResult>>(`/jobs/${jobId}`);
}

/** Polls until COMPLETED/FAILED — for flows whose submit endpoint returns either the
 * finished resource (small input) or a job to track (large input, PERFORMANCE §3). */
export async function pollJob<TResult = Record<string, unknown>>(
  jobId: string,
  intervalMs = 1000,
): Promise<Job<TResult>> {
  for (;;) {
    const job = await getJob<TResult>(jobId);
    if (job.status === "COMPLETED" || job.status === "FAILED") {
      return job;
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}
