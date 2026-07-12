// The abstract geometric-organic texture from docs/design.md: felt more than
// seen. Built entirely from geometry (concentric arcs + a thin radiating
// lattice), never a literal motif. It is fixed behind the whole shell at very
// low opacity, ignores pointer events, and is CSS-masked so it lives in the top
// negative space and fades out well before the dense table — never behind data.
//
// All the knobs are here: bump the wrapper opacity to make it more present, or
// change the mask to move where it sits.
export function BackgroundTexture() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-0 text-ink"
      style={{
        opacity: 0.05,
        maskImage:
          "radial-gradient(130% 90% at 82% -5%, black 0%, transparent 62%)",
        WebkitMaskImage:
          "radial-gradient(130% 90% at 82% -5%, black 0%, transparent 62%)",
      }}
    >
      <svg
        className="h-full w-full"
        viewBox="0 0 1200 800"
        preserveAspectRatio="xMidYMid slice"
        fill="none"
        stroke="currentColor"
      >
        {/* Concentric arcs radiating from a point off the top-right corner —
            the "advanced geometry" feel without any real-world reference. */}
        <g strokeWidth="1">
          {[120, 220, 320, 420, 540, 680, 840].map((r) => (
            <circle key={r} cx="1080" cy="40" r={r} />
          ))}
        </g>

        {/* A faint radiating lattice: straight spokes crossing the arcs, plus a
            couple of long organic sweeps to keep it from reading as purely
            mechanical. */}
        <g strokeWidth="0.75" opacity="0.7">
          <line x1="1080" y1="40" x2="120" y2="760" />
          <line x1="1080" y1="40" x2="360" y2="800" />
          <line x1="1080" y1="40" x2="620" y2="820" />
          <line x1="1080" y1="40" x2="-40" y2="520" />
        </g>

        <g strokeWidth="1" opacity="0.6">
          <path d="M -40 300 C 300 220, 620 360, 1240 180" />
          <path d="M -40 520 C 360 460, 700 600, 1240 420" />
        </g>
      </svg>
    </div>
  );
}
