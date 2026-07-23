import { useState, type FormEvent, type ReactNode } from "react";
import { login } from "../../lib/api";
import { setToken } from "../../lib/auth";

interface Props {
  // Called with the new token once login succeeds, so App can flip to the app.
  onLoggedIn: (token: string) => void;
}

// The gate the whole app sits behind. Two panels: a brand/hero column on the
// left (hidden on small screens) and the sign-in form on the right. Only the
// email/password flow is real; "Continue with Google", "Forgot?", and "Create
// an account" are shown to match the target design but are not wired to any
// backend yet, so they surface an honest "not set up yet" note instead of
// pretending to work.
export function LoginPage({ onLoggedIn }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [keepSignedIn, setKeepSignedIn] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setSubmitting(true);
    try {
      const token = await login(email, password);
      setToken(token);
      onLoggedIn(token);
      // No setSubmitting(false): on success this component unmounts.
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
      setSubmitting(false);
    }
  }

  function notYet(feature: string) {
    setError(null);
    setNotice(`${feature} isn't set up yet.`);
  }

  return (
    <div className="grid min-h-screen bg-base text-ink-soft lg:grid-cols-2">
      <FloatKeyframes />

      {/* Left: brand + hero. Hidden below lg, where the form stands alone. */}
      <aside className="relative hidden overflow-hidden border-r border-line-strong px-12 py-12 lg:flex lg:flex-col lg:justify-between">
        <RadialTexture />

        <div className="relative z-10 flex items-center gap-3">
          <LogoMark />
          <div className="leading-tight">
            <div className="text-sm font-semibold tracking-[0.2em] text-ink">
              SCOUT
            </div>
            <div className="text-[10px] uppercase tracking-[0.18em] text-ink-muted">
              Opportunity Tracker
            </div>
          </div>
        </div>

        <div className="relative z-10 max-w-md">
          <span className="inline-flex items-center gap-2 rounded-full border border-accent-line bg-accent-subtle px-3 py-1 text-[11px] font-medium uppercase tracking-[0.16em] text-ink-soft">
            <span className="size-1.5 rounded-full bg-accent" />
            Your application command center
          </span>

          <h1 className="mt-6 text-5xl font-semibold leading-[1.05] tracking-tight text-ink">
            Every opportunity, tracked from the dark.
          </h1>

          <p className="mt-5 text-[15px] leading-relaxed text-ink-soft">
            Paste a posting and Scout reads it for you. Deadlines, requirements,
            and priority, organized into one calm pipeline.
          </p>

          <PipelineCard />
        </div>

        <div className="relative z-10 text-xs text-ink-muted">
          Fall 2026 cycle. Built for the deadline-driven.
        </div>
      </aside>

      {/* Right: the sign-in form. */}
      <main className="flex items-center justify-center px-6 py-12">
        <form onSubmit={handleSubmit} className="w-full max-w-sm">
          <h2 className="text-3xl font-semibold text-ink">Welcome back</h2>
          <p className="mt-1.5 text-sm text-ink-muted">Sign in to your pipeline.</p>

          <label className="mt-8 mb-1.5 block text-xs font-medium text-ink-soft">
            Email
          </label>
          <Field icon={mailIcon}>
            <input
              type="email"
              autoComplete="username"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full bg-transparent py-2.5 pl-11 pr-3 text-sm text-ink placeholder:text-ink-muted focus:outline-none"
            />
          </Field>

          <div className="mt-4 mb-1.5 flex items-center justify-between">
            <label className="text-xs font-medium text-ink-soft">Password</label>
            <button
              type="button"
              onClick={() => notYet("Password reset")}
              className="text-xs font-medium text-accent hover:text-accent-hover"
            >
              Forgot?
            </button>
          </div>
          <Field icon={lockIcon}>
            <input
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full bg-transparent py-2.5 pl-11 pr-11 text-sm text-ink placeholder:text-ink-muted focus:outline-none"
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? "Hide password" : "Show password"}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-muted hover:text-ink"
            >
              {showPassword ? eyeOffIcon : eyeIcon}
            </button>
          </Field>

          <label className="mt-4 flex cursor-pointer items-center gap-2.5 text-sm text-ink-soft">
            <input
              type="checkbox"
              checked={keepSignedIn}
              onChange={(e) => setKeepSignedIn(e.target.checked)}
              className="size-4 accent-[#8b5cf6]"
            />
            Keep me signed in
          </label>

          {error && (
            <p className="mt-4 text-sm text-red-400" role="alert">
              {error}
            </p>
          )}
          {notice && (
            <p className="mt-4 text-sm text-ink-muted" role="status">
              {notice}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="mt-5 flex w-full items-center justify-center gap-2 rounded-interactive bg-accent py-3 text-sm font-medium text-white shadow-glow transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {submitting ? "Signing in…" : "Sign in"}
            {!submitting && <span aria-hidden="true">→</span>}
          </button>

          <div className="my-6 flex items-center gap-4 text-[11px] uppercase tracking-[0.18em] text-ink-muted">
            <span className="h-px flex-1 bg-line" />
            or
            <span className="h-px flex-1 bg-line" />
          </div>

          <button
            type="button"
            onClick={() => notYet("Google sign-in")}
            className="flex w-full items-center justify-center gap-3 rounded-interactive border border-line-strong bg-surface py-3 text-sm font-medium text-ink transition-colors hover:border-line-strong hover:bg-surface-hover"
          >
            {googleIcon}
            Continue with Google
          </button>

          <p className="mt-6 text-center text-sm text-ink-muted">
            New to Scout?{" "}
            <button
              type="button"
              onClick={() => notYet("Account creation")}
              className="font-semibold text-accent hover:text-accent-hover"
            >
              Create an account
            </button>
          </p>
        </form>
      </main>
    </div>
  );
}

// --- Left-panel pieces ------------------------------------------------------

// Reused brand mark: a purple tile with the nested hexagon glyph (matches the
// Sidebar's LogoMark — one of the few sanctioned purple elements).
function LogoMark() {
  return (
    <span className="grid size-11 place-items-center rounded-interactive bg-accent shadow-glow">
      <svg width="22" height="22" viewBox="0 0 18 18" aria-hidden="true">
        <path
          d="M9 2 15 5.5V12.5L9 16 3 12.5V5.5Z"
          fill="none"
          stroke="#fff"
          strokeWidth="1.3"
          strokeLinejoin="round"
        />
        <path
          d="M9 5.5 12 7.25v3.5L9 12.5 6 10.75v-3.5Z"
          fill="#fff"
          fillOpacity="0.9"
        />
      </svg>
    </span>
  );
}

// Faint concentric arcs, echoing the app shell's BackgroundTexture but centered
// off the top-left of this panel. Decorative only.
function RadialTexture() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 text-ink"
      style={{ opacity: 0.05 }}
    >
      <svg
        className="h-full w-full"
        viewBox="0 0 600 800"
        preserveAspectRatio="xMidYMid slice"
        fill="none"
        stroke="currentColor"
      >
        <g strokeWidth="1">
          {[120, 220, 320, 440, 580, 720].map((r) => (
            <circle key={r} cx="120" cy="120" r={r} />
          ))}
        </g>
      </svg>
    </div>
  );
}

// A sample pipeline, faked for the marketing panel. The rows drift gently up and
// down on a staggered loop (see FloatKeyframes), giving the card subtle life.
function PipelineCard() {
  const rows = [
    { initials: "AN", name: "Anthropic", sub: "Design Technologist", status: "Interview", faded: false },
    { initials: "KH", name: "Knight-Hennessy", sub: "Graduate Fellowship", status: "Drafting", faded: false },
    { initials: "GO", name: "Google", sub: "SWE Internship", status: "Discovered", faded: true },
  ];
  return (
    <div className="mt-10 rounded-frame border border-line bg-surface/50 p-3">
      {rows.map((row, i) => (
        <div
          key={row.name}
          className="scout-float flex items-center gap-3 rounded-interactive px-3 py-3"
          style={{ animationDelay: `${i * 0.6}s`, opacity: row.faded ? 0.45 : 1 }}
        >
          <span className="grid size-9 shrink-0 place-items-center rounded-lg border border-line-strong bg-base text-[11px] font-semibold text-ink-soft">
            {row.initials}
          </span>
          <div className="flex-1 leading-tight">
            <div className="text-[13px] font-medium text-ink">{row.name}</div>
            <div className="text-[11px] text-ink-muted">{row.sub}</div>
          </div>
          <span className="rounded-md border border-line px-2 py-1 text-[11px] text-ink-soft">
            {row.status}
          </span>
        </div>
      ))}
    </div>
  );
}

// Keyframes for the pipeline drift, honoring reduced-motion. Injected once.
function FloatKeyframes() {
  return (
    <style>{`
      @keyframes scoutFloat { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-6px); } }
      .scout-float { animation: scoutFloat 3.4s ease-in-out infinite; }
      @media (prefers-reduced-motion: reduce) { .scout-float { animation: none; } }
    `}</style>
  );
}

// --- Form field wrapper + icons ---------------------------------------------

// An input shell that positions a leading icon and draws the focus ring on the
// whole field (focus-within), so the icon sits inside the same bordered box.
function Field({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <div className="relative rounded-interactive border border-line-strong bg-surface/60 focus-within:border-accent focus-within:shadow-glow">
      <span className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-muted">
        {icon}
      </span>
      {children}
    </div>
  );
}

function iconBox(children: ReactNode) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 18 18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

const mailIcon = iconBox(
  <>
    <rect x="2.5" y="4" width="13" height="10" rx="1.5" />
    <path d="M3 5l6 4.5L15 5" />
  </>,
);

const lockIcon = iconBox(
  <>
    <rect x="3.5" y="8" width="11" height="7" rx="1.5" />
    <path d="M6 8V6a3 3 0 0 1 6 0v2" />
  </>,
);

const eyeIcon = iconBox(
  <>
    <path d="M1.5 9S4 4 9 4s7.5 5 7.5 5-2.5 5-7.5 5-7.5-5-7.5-5Z" />
    <circle cx="9" cy="9" r="2" />
  </>,
);

const eyeOffIcon = iconBox(
  <>
    <path d="M3 3l12 12" />
    <path d="M7.3 4.3A7.4 7.4 0 0 1 9 4c5 0 7.5 5 7.5 5a12 12 0 0 1-2.2 2.7M4.6 5.6A12 12 0 0 0 1.5 9S4 14 9 14a7.4 7.4 0 0 0 2.4-.4" />
  </>,
);

// The multicolor Google "G" mark.
const googleIcon = (
  <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden="true">
    <path
      fill="#4285F4"
      d="M45 24c0-1.6-.1-2.8-.4-4H24v7.6h12c-.2 2-1.6 5-4.6 7l7 5.4C42.6 40 45 32.9 45 24Z"
    />
    <path
      fill="#34A853"
      d="M24 46c6.5 0 11.9-2.1 15.9-5.8l-7-5.4c-2 1.3-4.6 2.2-8.9 2.2-6.8 0-12.5-4.6-14.6-10.8l-7.2 5.6C6.1 40.9 14.4 46 24 46Z"
    />
    <path
      fill="#FBBC05"
      d="M9.4 26.2c-.5-1.5-.8-3.1-.8-4.7s.3-3.2.8-4.7l-7.2-5.6C.8 14.3 0 18.1 0 21.5s.8 7.2 2.2 10.3l7.2-5.6Z"
    />
    <path
      fill="#EA4335"
      d="M24 8.5c3.5 0 6 .1 8.7 2.6l6.2-6.2C35.9 1.6 30.5 0 24 0 14.4 0 6.1 5.1 2.2 12.7l7.2 5.6C11.5 12.1 17.2 8.5 24 8.5Z"
    />
  </svg>
);
