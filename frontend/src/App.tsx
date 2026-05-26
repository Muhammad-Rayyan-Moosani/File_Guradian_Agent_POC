import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Dashboard } from "./pages/Dashboard";
import { RunDetail } from "./pages/RunDetail";
import { Profiles } from "./pages/Profiles";
import { ProfileEditor } from "./pages/ProfileEditor";
import { Settings } from "./pages/Settings";
import "./App.css";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/runs/:id" element={<RunDetail />} />
          <Route path="/profiles" element={<Profiles />} />
          <Route path="/profiles/new" element={<ProfileEditor />} />
          <Route path="/profiles/:id/edit" element={<ProfileEditor />} />
          <Route path="/settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
