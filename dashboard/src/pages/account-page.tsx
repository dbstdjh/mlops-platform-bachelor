import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ErrorState, LoadingCard, PageHeader, Panel, PrimaryButton, SecondaryButton, SectionTitle } from "@/components/ui";
import { useAuth } from "@/hooks/use-auth";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/date";
import type { IssuedApiKey } from "@/types/api";

export function AccountPage() {
  const { user } = useAuth();
  const [keyName, setKeyName] = useState("");
  const [issuedKey, setIssuedKey] = useState<IssuedApiKey | null>(null);
  const queryClient = useQueryClient();

  const apiKeysQuery = useQuery({
    queryKey: ["api-keys"],
    queryFn: api.listApiKeys,
  });

  const createKeyMutation = useMutation({
    mutationFn: api.createApiKey,
    onSuccess: (key) => {
      setIssuedKey(key);
      setKeyName("");
      void queryClient.invalidateQueries({ queryKey: ["api-keys"] });
    },
  });

  const revokeKeyMutation = useMutation({
    mutationFn: api.revokeApiKey,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["api-keys"] });
    },
  });

  async function handleCreateKey(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await createKeyMutation.mutateAsync({ name: keyName });
  }

  if (!user) {
    return <LoadingCard label="Loading account" />;
  }

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Account"
        title="Profile and API keys"
        description="Identity details and SDK credentials for local workflows."
      />

      <Panel className="space-y-5">
        <SectionTitle title="Profile" description="Authenticated identity resolved from the existing bearer-token flow." />
        <div className="grid gap-4 md:grid-cols-2">
          <Meta label="Email">{user.email}</Meta>
          <Meta label="Created at">{formatDateTime(user.created_at)}</Meta>
          <Meta label="Active">{user.is_active ? "Yes" : "No"}</Meta>
          <Meta label="Verified">{user.is_verified ? "Yes" : "No"}</Meta>
        </div>
      </Panel>

      <Panel className="space-y-5">
        <SectionTitle title="Issue a new API key" description="Plaintext is shown exactly once, then forgotten by the backend." />
        <form className="flex flex-col gap-3 md:flex-row" onSubmit={handleCreateKey}>
          <input
            className="flex-1 rounded-full border border-border bg-paper px-4 py-3 outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
            onChange={(event) => setKeyName(event.target.value)}
            placeholder="sdk"
            required
            value={keyName}
          />
          <PrimaryButton disabled={createKeyMutation.isPending} type="submit">
            {createKeyMutation.isPending ? "Issuing..." : "Create API key"}
          </PrimaryButton>
        </form>
        {createKeyMutation.isError ? (
          <ErrorState description="The API key could not be created. Check for duplicate names or auth issues." />
        ) : null}
        {issuedKey ? (
          <div className="rounded-[24px] border border-accent/25 bg-accent/8 p-5">
            <p className="font-mono text-xs uppercase tracking-[0.24em] text-accent">One-time secret</p>
            <p className="mt-3 break-all rounded-2xl bg-paper px-4 py-3 font-mono text-sm">{issuedKey.api_key}</p>
            <p className="mt-3 text-sm text-stone-600">
              This value is only returned once. The list below intentionally never includes the plaintext key again.
            </p>
            <SecondaryButton className="mt-4" onClick={() => setIssuedKey(null)} type="button">
              Dismiss
            </SecondaryButton>
          </div>
        ) : null}
      </Panel>

      <Panel className="space-y-5">
        <SectionTitle title="Existing API keys" description="Stored as hashed records; revoke them whenever a workstation or workflow changes hands." />
        {apiKeysQuery.isLoading ? (
          <LoadingCard label="Loading API keys" />
        ) : apiKeysQuery.isError ? (
          <ErrorState description="The API key list could not be loaded." />
        ) : !apiKeysQuery.data || apiKeysQuery.data.length === 0 ? (
          <p className="text-sm text-stone-500">No API keys have been issued yet.</p>
        ) : (
          <div className="space-y-3">
            {apiKeysQuery.data.map((key) => (
              <div key={key.name} className="flex flex-col gap-4 rounded-[24px] border border-border bg-paper/70 p-5 md:flex-row md:items-center md:justify-between">
                <div className="space-y-1">
                  <p className="text-lg font-semibold">{key.name}</p>
                  <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">{key.prefix}</p>
                  <p className="text-sm text-stone-600">Issued {formatDateTime(key.created_at)}</p>
                </div>
                <div className="flex items-center gap-3">
                  <span className={`rounded-full px-3 py-1 font-mono text-[11px] uppercase tracking-[0.18em] ${key.is_revoked ? "bg-danger/10 text-danger" : "bg-success/10 text-success"}`}>
                    {key.is_revoked ? "Revoked" : "Active"}
                  </span>
                  <SecondaryButton
                    disabled={key.is_revoked || revokeKeyMutation.isPending}
                    onClick={() => revokeKeyMutation.mutate(key.name)}
                    type="button"
                  >
                    Revoke
                  </SecondaryButton>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>

    </div>
  );
}

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-border bg-paper/75 p-4">
      <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">{label}</p>
      <div className="mt-2 text-sm text-stone-700">{children}</div>
    </div>
  );
}
