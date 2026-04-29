export const STORAGE_KEY = "mlops.dashboard.token";

const rawBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

export const API_BASE_URL = rawBaseUrl.replace(/\/+$/, "");
