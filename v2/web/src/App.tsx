import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { CanvasListPage } from "@/pages/CanvasListPage";
import { CanvasPage } from "@/pages/CanvasPage";

const queryClient = new QueryClient();

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<CanvasListPage />} />
          <Route path="/c/:id" element={<CanvasPage />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
