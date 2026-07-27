import { useEffect, useState } from "react";
import { AppShell } from "./components/layout/AppShell";
import { ApplicationsPage } from "./components/applications/ApplicationsPage";
import { LoginPage } from "./components/auth/LoginPage";
import { clearToken, getToken } from "./lib/auth";
import { useApplications } from "./lib/useApplications";
import { ResumeBuilder } from "./components/resume/ResumeBuilder";
import type { View } from "./components/layout/Sidebar";

// Root composition and the auth gate. Token state is plain useState (seeded from
// localStorage) — a single-screen app doesn't need a Context yet. No token shows
// the login screen; a token shows the app.
export function App() {
  const [token, setTokenState] = useState<string | null>(getToken());

  // api.ts fires "auth:unauthorized" when any authenticated call gets a 401
  // (token expired or invalid). Clearing token state drops back to login.
  useEffect(() => {
    function handleUnauthorized() {
      setTokenState(null);
    }
    window.addEventListener("auth:unauthorized", handleUnauthorized);
    return () =>
      window.removeEventListener("auth:unauthorized", handleUnauthorized);
  }, []);

  if (!token) {
    return <LoginPage onLoggedIn={setTokenState} />;
  }

  function handleLogout() {
    clearToken();
    setTokenState(null);
  }

  return <AuthedApp onLogout={handleLogout} />;
}

// The authenticated app. Split into its own component so useApplications (which
// fetches on mount) only runs once we have a token — mounting it before login
// would fire an unauthenticated request and immediately 401.
function AuthedApp({ onLogout }: { onLogout: () => void }) {
  const state = useApplications();
  // Which top-level view is showing. Applications is home; Resume is the builder.
  const [view, setView] = useState<View>("applications");

  return (
    <AppShell
      current={view}
      onNavigate={setView}
      applicationCount={state.applications.length}
      onLogout={onLogout}
    >
      {view === "resume" ? (
        <ResumeBuilder onClose={() => setView("applications")} />
      ) : (
        <ApplicationsPage {...state} />
      )}
    </AppShell>
  );
}
