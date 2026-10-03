import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { HomePage } from "./pages/HomePage";
import { crearQueryClient } from "./shared/query-client";
import "./index.css";

const router = createBrowserRouter([{ path: "/", element: <HomePage /> }]);
const queryClient = crearQueryClient();

const raiz = document.getElementById("root");
if (raiz === null) {
  throw new Error("Falta el elemento #root en index.html.");
}
createRoot(raiz).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
