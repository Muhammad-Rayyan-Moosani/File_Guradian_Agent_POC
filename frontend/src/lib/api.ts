import type { AppSettings, ValidationProfile, ValidationRun } from "../types";

// Same-origin by default. In production, Flask serves both the UI and the API
// on one port, so a relative path like "/api/runs" hits the right place no
// matter which machine opens the app. During development the Vite dev server
// proxies "/api" to the backend (see vite.config.ts), so this works there too.
const API_BASE = "";

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
  deleteRun: (
    id: string
  ): Promise<{ id: string; ok: boolean; file_deleted: boolean }> =>
    request(`/api/runs/${id}`, { method: "DELETE" }),

  getSettings: (): Promise<AppSettings> => request("/api/settings"),
  updateSettings: (settings: AppSettings): Promise<AppSettings> =>
    request("/api/settings", {
      method: "PUT",
      body: JSON.stringify(settings),
    }),
};
