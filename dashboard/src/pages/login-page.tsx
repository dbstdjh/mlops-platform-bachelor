import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { AuthLayout } from "@/components/auth-layout";
import { PrimaryButton } from "@/components/ui";
import { useAuth } from "@/hooks/use-auth";
import { ApiError } from "@/lib/api";

export function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      await login(email, password);
      const next = (location.state as { from?: string } | null)?.from ?? "/overview";
      navigate(next, { replace: true });
    } catch (submissionError) {
      setError(submissionError instanceof ApiError ? submissionError.detail : "Unable to sign in right now.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthLayout title="Welcome back" subtitle="Use your control-plane credentials to unlock the dashboard.">
      <form className="space-y-4" onSubmit={handleSubmit}>
        <Field label="Email" type="email" value={email} onChange={setEmail} />
        <Field label="Password" type="password" value={password} onChange={setPassword} />
        {error ? <p className="rounded-2xl bg-danger/10 px-4 py-3 text-sm text-danger">{error}</p> : null}
        <PrimaryButton className="w-full" disabled={isSubmitting} type="submit">
          {isSubmitting ? "Signing in..." : "Sign in"}
        </PrimaryButton>
      </form>
      <p className="mt-6 text-sm text-stone-600">
        Need an account?{" "}
        <Link className="font-semibold text-accent" to="/register">
          Register here
        </Link>
        .
      </p>
    </AuthLayout>
  );
}

function Field({
  label,
  type,
  value,
  onChange,
}: {
  label: string;
  type: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block space-y-2">
      <span className="text-sm font-semibold">{label}</span>
      <input
        className="w-full rounded-2xl border border-border bg-paper px-4 py-3 outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/20"
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required
      />
    </label>
  );
}
