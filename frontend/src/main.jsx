import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import { OrbProvider } from "./context/OrbContext.jsx";
import { ThemeProvider } from "./context/ThemeContext.jsx";
import { ViewportProvider } from "./context/ViewportContext.jsx";
import { ToastProvider } from "./lib/kit.jsx";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ViewportProvider>
      <ThemeProvider>
        <ToastProvider>
        <OrbProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </OrbProvider>
        </ToastProvider>
      </ThemeProvider>
    </ViewportProvider>
  </React.StrictMode>,
);
