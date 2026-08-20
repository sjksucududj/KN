import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@/index.css";
import App from "@/App";
import { Toaster } from "@/components/ui/toaster";
import ConfirmHost from "@/components/ConfirmHost";

// Suppress benign "ResizeObserver loop ..." error yang dimunculkan overlay dev
// CRA saat Radix Popover/cmdk mengukur layout. Tidak berdampak fungsional &
// tidak muncul di production build.
const RESIZE_OBSERVER_MSG = "ResizeObserver loop";
window.addEventListener("error", (e) => {
  if (e.message && e.message.includes(RESIZE_OBSERVER_MSG)) {
    e.stopImmediatePropagation();
    e.preventDefault();
  }
});


const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
    },
  },
});

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
      <Toaster />
      {/* FASE P5 — satu instansi dialog konfirmasi untuk seluruh aplikasi, supaya
          `askConfirm()/askReason()/askText()` bisa dipanggil dari layar & hook mana pun
          tanpa `window.confirm` yang memblokir peramban. Lihat services/confirmService.js. */}
      <ConfirmHost />
    </QueryClientProvider>
  </React.StrictMode>,
);
