export const fetcher = (url: string) => fetch(url).then((res) => res.json());

export const API_BASE = '/api/v1';
