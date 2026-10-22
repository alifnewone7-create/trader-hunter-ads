import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Landing from "@/pages/Landing";
import DownloadPage from "@/pages/DownloadPage";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {process.env.REACT_APP_ENABLE_DOWNLOAD !== "false" && (
          <Route path="/download" element={<DownloadPage />} />
        )}
        <Route path="*" element={<Landing />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
