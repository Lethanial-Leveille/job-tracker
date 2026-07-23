import type { ReactNode } from "react";
import { BackgroundTexture } from "./BackgroundTexture";
import { Sidebar } from "./Sidebar";

interface Props {
  applicationCount: number;
  onLogout: () => void;
  children: ReactNode;
}

// The frame that holds everything: a fixed sidebar + a scrolling content column,
// over the near-black base with the etched texture behind. "Drama in the frame":
// the heavy styling lives here, so the content column can stay calm.
export function AppShell({ applicationCount, onLogout, children }: Props) {
  return (
    <div className="relative min-h-screen bg-base text-ink-soft">
      <BackgroundTexture />

      <div className="relative z-10 grid grid-cols-[248px_1fr]">
        <Sidebar applicationCount={applicationCount} onLogout={onLogout} />

        <main className="h-screen overflow-y-auto px-8 py-8">
          <div className="mx-auto max-w-6xl">{children}</div>
        </main>
      </div>
    </div>
  );
}
