import type { ValidationProfile, ValidationRun } from "../types";

const API_BASE = "http://127.0.0.1:5000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(
      detail.error
        ? `${detail.error}${detail.detail ? ` — ${detail.detail}` : ""}`
        : `${res.status} ${res.statusText}`
    );
  }
  return res.json() as Promise<T>;
}

export const api = {
  listProfiles: (): Promise<ValidationProfile[]> => request("/api/profiles"),
  getProfile: (id: string): Promise<ValidationProfile> =>
    request(`/api/profiles/${id}`),
  createProfile: (profile: ValidationProfile): Promise<ValidationProfile> =>
    request("/api/profiles", {
      method: "POST",
      body: JSON.stringify(profile),
    }),
  updateProfile: (
    id: string,
    profile: ValidationProfile
  ): Promise<ValidationProfile> =>
    request(`/api/profiles/${id}`, {
      method: "PUT",
      body: JSON.stringify(profile),
    }),
  deleteProfile: (
    id: string
  ): Promise<{ id: string; ok: boolean; deleted: boolean }> =>
    request(`/api/profiles/${id}`, { method: "DELETE" }),

  listRuns: (): Promise<ValidationRun[]> => request("/api/runs"),
  getRun: (id: string): Promise<ValidationRun> => request(`/api/runs/${id}`),
};
