import { useEffect, useState } from "react";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { ApplicationsPage } from "./components/applications/ApplicationsPage";
import { ApplicationDetailPage } from "./components/applications/ApplicationDetailPage";
import { AddOpportunity } from "./components/applications/AddOpportunity";
import { LoginPage } from "./components/auth/LoginPage";
import { BaseResumePanel } from "./components/resume/BaseResumePanel";
import { ResumeBuilder } from "./components/resume/ResumeBuilder";
import { clearToken, getToken } from "./lib/auth";
import { deleteApplication } from "./lib/api";
import type { Application } from "./lib/types";
import { useApplications } from "./lib/useApplications";
import type { ApplicationsState } from "./lib/useApplications";
import type { View } from "./components/layout/Sidebar";

// Root composition, the auth gate, and the app's routes.
//
// The views used to be a useState swap, which the code justified with "adding
// react-router for two screens would be more machinery than the app has
// earned". True at two screens; there are now four, and the swap had two costs
// that only a real router fixes: the browser Back button left the app entirely
// (there were no history entries to go back to), and a refresh always dumped you
// on the list no matter where you were. Both are now handled, and an
// application has a URL you can bookmark.
//
// Caddy on the droplet already serves `try_files {path} /index.html`, so a deep
// link like /applications/<id> survives a hard refresh in production.
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
    // Deliberately outside the router: logging in leaves the URL alone, so a
    // deep link followed while signed out lands on the right page afterwards.
    return <LoginPage onLoggedIn={setTokenState} />;
  }

  function handleLogout() {
    clearToken();
    setTokenState(null);
  }

  return (
    <BrowserRouter>
      <AuthedApp onLogout={handleLogout} />
    </BrowserRouter>
  );
}

// The authenticated app. Split into its own component so useApplications (which
// fetches on mount) only runs once we have a token — mounting it before login
// would fire an unauthenticated request and immediately 401.
function AuthedApp({ onLogout }: { onLogout: () => void }) {
  const state = useApplications();
  const location = useLocation();
  const navigate = useNavigate();

  // The sidebar still speaks in views, not paths; the URL is the source of
  // truth and this translates between them.
  const current: View = location.pathname.startsWith("/resume")
    ? "resume"
    : "applications";

  return (
    <AppShell
      current={current}
      onNavigate={(view) =>
        navigate(view === "resume" ? "/resume" : "/applications")
      }
      applicationCount={state.applications.length}
      onLogout={onLogout}
    >
      <Routes>
        <Route path="/applications" element={<ApplicationsPage {...state} />} />
        {/* Static segments outrank dynamic ones in react-router's matching, so
            /applications/new is never swallowed by /applications/:id. */}
        <Route path="/applications/new" element={<AddApplicationRoute {...state} />} />
        <Route path="/applications/:id" element={<ApplicationDetailRoute {...state} />} />
        {/* Static before dynamic, same rule as /applications/new above. */}
        <Route
          path="/resume/base"
          element={<BaseResumePanel onBack={() => navigate("/resume")} />}
        />
        <Route
          path="/resume"
          element={<ResumeBuilder onClose={() => navigate("/applications")} />}
        />
        {/* Anything else, including "/", lands on the pipeline. */}
        <Route path="*" element={<Navigate to="/applications" replace />} />
      </Routes>
    </AppShell>
  );
}

// Bridges the :id in the URL to the detail page's props.
function ApplicationDetailRoute({
  applications,
  loading,
  refetch,
  setStatus,
}: ApplicationsState) {
  const { id } = useParams();
  const navigate = useNavigate();
  const application = applications.find((a) => a.id === id) ?? null;

  if (application === null) {
    // A hard refresh straight onto this URL arrives before the list does, so
    // "not found" would be a lie for a moment. Wait for the fetch, and only
    // then treat a missing id as missing.
    if (loading) {
      return (
        <div className="grid place-items-center rounded-frame border border-line-strong bg-surface px-6 py-16 text-center text-sm text-ink-muted">
          Loading…
        </div>
      );
    }
    return <Navigate to="/applications" replace />;
  }

  async function handleDelete(app: Application) {
    if (!window.confirm("Delete this application? This cannot be undone.")) return;
    await deleteApplication(app.id);
    refetch();
    navigate("/applications");
  }

  return (
    // key by id so moving between applications rebuilds the page from scratch.
    // Without it React reuses the instance, and the Overview tab's form state
    // (seeded once from props) would keep showing the previous row's values.
    <ApplicationDetailPage
      key={application.id}
      application={application}
      onBack={() => navigate("/applications")}
      onSaved={refetch}
      onDelete={handleDelete}
      onStatusChange={setStatus}
    />
  );
}

// The add flow, as a route so Back leaves it the way you'd expect.
function AddApplicationRoute({ applications, refetch }: ApplicationsState) {
  const navigate = useNavigate();
  return (
    <AddOpportunity
      applications={applications}
      onClose={() => navigate("/applications")}
      onSaved={() => {
        refetch();
        navigate("/applications");
      }}
      // Leaving the add flow straight into the row you already had, so a
      // duplicate warning ends somewhere useful.
      onOpenExisting={(id) => navigate(`/applications/${id}`)}
    />
  );
}
