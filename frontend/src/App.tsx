import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Dashboard } from "./pages/Dashboard";
import { RunDetail } from "./pages/RunDetail";
import { Profiles } from "./pages/Profiles";
import { ProfileEditor } from "./pages/ProfileEditor";
import { Settings } from "./pages/Settings";
import { Login } from "./pages/Login";
import { AuthProvider, useAuth } from "./lib/auth";
import "./App.css";

// Decides what to show based on login state: nothing while we check, the login
// screen when a sign-in is required, otherwise the full app.
function Gate() {
  const { loading, authEnabled, authenticated } = useAuth();

  if (loading) {
    return <div className="min-h-screen bg-slate-100" />;
  }
  if (authEnabled && !authenticated) {
    return <Login />;
  }

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

function App() {
  return (
    <AuthProvider>
      <Gate />
    </AuthProvider>
  );
}

export default App;
