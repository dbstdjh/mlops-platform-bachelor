import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { AuthLayout } from "@/components/auth-layout";
import { PrimaryButton } from "@/components/ui";
import { useAuth } from "@/hooks/use-auth";
import { ApiError } from "@/lib/api";

export function RegisterPage() {
  const { register } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      await register(email, password);
      navigate("/overview", { replace: true });
    } catch (submissionError) {
      setError(submissionError instanceof ApiError ? submissionError.detail : "Unable to create your account.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthLayout title="Create your account" subtitle="Get a clean readout of experiments, datasets, and the registry.">
      <form className="space-y-4" onSubmit={handleSubmit}>
        <Field label="Email" type="email" value={email} onChange={setEmail} />
        <Field label="Password" type="password" value={password} onChange={setPassword} helper="At least 8 characters." />
        {error ? <p className="rounded-2xl bg-danger/10 px-4 py-3 text-sm text-danger">{error}</p> : null}
        <PrimaryButton className="w-full" disabled={isSubmitting} type="submit">
          {isSubmitting ? "Creating account..." : "Create account"}
        </PrimaryButton>
      </form>
      <p className="mt-6 text-sm text-stone-600">
        Already have an account?{" "}
        <Link className="font-semibold text-accent" to="/login">
          Sign in
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
  helper,
}: {
  label: string;
  type: string;
  value: string;
  onChange: (value: string) => void;
  helper?: string;
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
      {helper ? <span className="block text-xs text-stone-500">{helper}</span> : null}
    </label>
  );
}
