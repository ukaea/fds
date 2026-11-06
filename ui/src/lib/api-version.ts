// The version of FDS's API this UI speaks. FDS serves it at API_VERSION, and the
// browser reaches it through the UI's proxy at API_BASE, which lives in
// app/api/v1 and has to move with it.
export const API_VERSION = '/v1';
export const API_BASE = `/api${API_VERSION}`;
