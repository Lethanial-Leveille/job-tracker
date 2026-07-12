import { AppShell } from "./components/layout/AppShell";
import { ApplicationsPage } from "./components/applications/ApplicationsPage";
import { useApplications } from "./lib/useApplications";

// Root composition. The applications fetch lives here (the common ancestor) so
// the sidebar count and the table share one source of truth. v1 has a single
// screen, so there is no router yet.
export function App() {
  const state = useApplications();

  return (
    <AppShell applicationCount={state.applications.length}>
      <ApplicationsPage {...state} />
    </AppShell>
  );
}
