import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./index.css";
import "./i18n";
import App from "./App";
import { AuthProvider } from "./lib/auth";
import { BrandingProvider } from "./lib/branding";

const qc = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <BrandingProvider>
          <AuthProvider>
            <App />
          </AuthProvider>
        </BrandingProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
