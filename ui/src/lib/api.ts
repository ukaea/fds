import { signOut } from 'next-auth/react';

export const fetcher = async (url: string) => {
  const res = await fetch(url);
  if (!res.ok) {
    if (res.status === 401) {
      await signOut({ callbackUrl: '/' });
    }
    const errorBody = await res.text().catch(() => '');
    throw new Error(`An error occurred while fetching the data: ${res.status} ${res.statusText} ${errorBody}`);
  }
  return res.json();
};

export const API_BASE = '/api/v1';
