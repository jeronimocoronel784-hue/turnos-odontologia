import { QueryClient } from "@tanstack/react-query";

// Cliente Query único de la app (D7): toda lectura de API pasa por acá.
export function crearQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: 1,
        staleTime: 30_000,
        refetchOnWindowFocus: false,
      },
    },
  });
}
