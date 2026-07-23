import { useState, type FormEvent } from "react";
import { login } from "../../lib/api";
import { setToken } from "../../lib/auth";

interface Props {
  // Called with the new token once login succeeds, so App can flip to the app.
  onLoggedIn: (token: string) => void;
}

// The gate the whole app sits behind. A single centered card: email, password,
// and one purple primary action (the one sanctioned purple button, per the
// design system). Shows the backend's "incorrect email or password" on a 401.
export function LoginPage({ onLoggedIn }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const token = await login(email, password);
      setToken(token);
      onLoggedIn(token);
      // No setSubmitting(false): on success this component unmounts as the app
      // switches over, so there is nothing left to re-enable.
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
      setSubmitting(false);
    }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-base px-4 text-ink-soft">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-frame border border-line bg-surface/60 p-8 backdrop-blur-sm"
      >
        <div className="mb-8 text-center">
          <div className="text-sm font-semibold tracking-[0.2em] text-ink">
            SCOUT
          </div>
          <div className="mt-1 text-[11px] uppercase tracking-[0.18em] text-ink-muted">
            Sign in to continue
          </div>
        </div>

        <label className="mb-1.5 block text-xs font-medium text-ink-soft">
          Email
        </label>
        <input
          type="email"
          autoComplete="username"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          className="mb-4 w-full rounded-interactive border border-line-strong bg-surface/60 px-3 py-2.5 text-sm text-ink placeholder:text-ink-muted focus:border-accent focus:shadow-glow focus:outline-none"
        />

        <label className="mb-1.5 block text-xs font-medium text-ink-soft">
          Password
        </label>
        <input
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          className="mb-2 w-full rounded-interactive border border-line-strong bg-surface/60 px-3 py-2.5 text-sm text-ink placeholder:text-ink-muted focus:border-accent focus:shadow-glow focus:outline-none"
        />

        {error && (
          <p className="mb-2 text-sm text-red-400" role="alert">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="mt-4 w-full rounded-interactive bg-accent py-2.5 text-sm font-medium text-white shadow-glow transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
