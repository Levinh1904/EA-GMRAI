import useSWR, { type SWRConfiguration } from 'swr';
import { apiFetch } from './api';

/** Typed SWR hook bound to the authenticated API client. */
export function useApi<T>(path: string | null | undefined, options?: SWRConfiguration<T>) {
  return useSWR<T>(path, (p: string) => apiFetch<T>(p), options);
}
