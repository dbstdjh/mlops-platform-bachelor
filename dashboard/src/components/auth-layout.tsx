export function AuthLayout({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_0.9fr]">
      <div className="hidden bg-ink px-12 py-14 text-paper lg:flex lg:flex-col lg:justify-between">
        <div className="space-y-4">
          <p className="font-mono text-xs uppercase tracking-[0.34em] text-paper/60">Phase 1 Dashboard</p>
          <h1 className="max-w-lg text-5xl font-semibold tracking-[-0.06em]">
            A clear readout of your experiments, datasets, and model artifacts.
          </h1>
          <p className="max-w-md text-base text-paper/70">
            Built for fast thesis demos and day-to-day tracking. Light, deliberate, and focused on what the control
            plane already knows.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          {[
            ["Experiments", "Track run health, metrics, and latest outcomes."],
            ["Datasets", "See versioned feature assets without touching raw bytes."],
            ["Registry", "Browse repositories and model versions tied to runs."],
          ].map(([label, detail]) => (
            <div key={label} className="rounded-[24px] border border-white/10 bg-white/5 p-5">
              <p className="text-sm font-semibold">{label}</p>
              <p className="mt-2 text-sm text-paper/60">{detail}</p>
            </div>
          ))}
        </div>
      </div>
      <div className="flex items-center justify-center px-6 py-10 sm:px-10">
        <div className="w-full max-w-lg rounded-[32px] border border-border bg-mist/90 p-8 shadow-card sm:p-10">
          <div className="space-y-2">
            <p className="font-mono text-xs uppercase tracking-[0.34em] text-accent">MLOps Platform</p>
            <h2 className="text-3xl font-semibold tracking-[-0.05em]">{title}</h2>
            <p className="text-sm text-stone-600">{subtitle}</p>
          </div>
          <div className="mt-8">{children}</div>
        </div>
      </div>
    </div>
  );
}
