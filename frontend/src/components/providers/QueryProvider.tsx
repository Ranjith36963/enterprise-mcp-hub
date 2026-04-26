"use client";

import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";

// ---------------------------------------------------------------------------
// QueryProvider
// ---------------------------------------------------------------------------
// Creates a stable QueryClient per component mount (safe for concurrent mode).
// staleTime defaults:
//   - jobs queries:    30 s  (set per-query at the call site)
//   - profile queries: 5 min (set per-query at the call site)
// The global default here is conservative (0) so individual queries can opt in.
// ---------------------------------------------------------------------------

function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Do not retry on 4xx errors (auth / not-found)
        retry: (failureCount, error) => {
          if (error instanceof Error && "status" in error) {
            const status = (error as { status: number }).status;
            if (status >= 400 && status < 500) return false;
          }
          return failureCount < 2;
        },
        // Let individual queries set their own staleTime
        staleTime: 0,
        // Disable refetch on window focus globally — dashboard controls its own refresh
        refetchOnWindowFocus: false,
      },
    },
  });
}

interface QueryProviderProps {
  children: React.ReactNode;
}

export function QueryProvider({ children }: QueryProviderProps) {
  // useState ensures the QueryClient is not recreated on every render
  const [queryClient] = useState<QueryClient>(makeQueryClient);

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      {process.env.NODE_ENV === "development" && (
        <ReactQueryDevtools initialIsOpen={false} />
      )}
    </QueryClientProvider>
  );
}
