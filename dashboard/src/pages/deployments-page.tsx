import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Boxes, ChevronRight, Container, PackageOpen, Rocket, X } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { EmptyState, ErrorState, LabelChips, LoadingCard, PageHeader, PaginationControls, Panel, PrimaryButton, SearchInput, SecondaryButton, SectionTitle, SelectInput, StatusBadge } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/date";
import type { ArtifactImage, ArtifactImageTag, Deployment, IssuedRegistryToken, Model, Repository } from "@/types/api";

type DeploymentMode = "file" | "image";
const PAGE_SIZE = 10;

interface SelectedImageTag {
  image: ArtifactImage;
  tag: ArtifactImageTag;
}

interface ModelOption {
  repository: Repository;
  model: Model;
}

export function DeploymentsPage() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("created_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [offset, setOffset] = useState(0);

  const deploymentsQuery = useQuery({
    queryKey: ["deployments", { search, sortBy, sortDir, offset }],
    queryFn: () => api.listDeploymentsPage({ search, sort_by: sortBy, sort_dir: sortDir, limit: PAGE_SIZE, offset }),
    refetchInterval: (query) => {
      const deployments = query.state.data?.items;
      return deployments?.some((deployment) => isDeploymentInProgress(deployment.status)) ? 1000 : false;
    },
  });

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Deployments"
        title="Model serving"
        description="Live endpoints, deployable model artifacts, custom images, and serving observability."
        action={
          <PrimaryButton onClick={() => setDrawerOpen(true)} type="button">
            <Rocket className="mr-2 h-4 w-4" />
            Create deployment
          </PrimaryButton>
        }
      />

      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_170px_175px]">
        <SearchInput placeholder="Search deployments, endpoints, images" value={search} onChange={(value) => { setSearch(value); setOffset(0); }} />
        <SelectInput
          onValueChange={(value) => { setSortBy(value); setOffset(0); }}
          options={[
            { value: "created_at", label: "Newest" },
            { value: "name", label: "Name" },
            { value: "status", label: "Status" },
            { value: "source_type", label: "Source" },
          ]}
          value={sortBy}
        />
        <SelectInput
          onValueChange={(value) => { setSortDir(value as "asc" | "desc"); setOffset(0); }}
          options={[
            { value: "desc", label: "Descending" },
            { value: "asc", label: "Ascending" },
          ]}
          value={sortDir}
        />
      </div>

      {deploymentsQuery.isLoading ? (
        <LoadingCard label="Loading deployments" />
      ) : deploymentsQuery.isError ? (
        <ErrorState description="The deployment list could not be loaded." />
      ) : !deploymentsQuery.data || deploymentsQuery.data.items.length === 0 ? (
        <EmptyState
          title="No deployments found"
          description="Create a deployment from a READY sklearn pickle model or a pushed custom image, or adjust the current search."
          action={
            <SecondaryButton onClick={() => setDrawerOpen(true)} type="button">
              Create deployment
            </SecondaryButton>
          }
        />
      ) : (
        <div className="space-y-4">
          <PaginationControls total={deploymentsQuery.data.total} limit={PAGE_SIZE} offset={offset} onOffsetChange={setOffset} />
          <div className="grid gap-5 xl:grid-cols-2">
            {deploymentsQuery.data.items.map((deployment) => (
              <DeploymentCard deployment={deployment} key={deployment.slug} />
            ))}
          </div>
          <PaginationControls total={deploymentsQuery.data.total} limit={PAGE_SIZE} offset={offset} onOffsetChange={setOffset} />
        </div>
      )}

      {drawerOpen ? <CreateDeploymentDrawer onClose={() => setDrawerOpen(false)} /> : null}
    </div>
  );
}

function DeploymentCard({ deployment }: { deployment: Deployment }) {
  return (
    <Link className="block" to={`/deployments/${deployment.slug}`}>
      <Panel className="h-full space-y-5 transition hover:border-accent/45 hover:bg-white/80">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 space-y-2">
            <div className="flex items-center gap-3">
              <Rocket className="h-5 w-5 text-accent" />
              <h2 className="truncate text-2xl font-semibold tracking-[-0.03em]">{deployment.name}</h2>
            </div>
            <p className="font-mono text-xs uppercase tracking-[0.18em] text-stone-500">{deployment.slug}</p>
          </div>
          <StatusBadge status={deployment.status} />
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <Meta label="Source">{deployment.source_type === "image" ? "Custom image" : "Prebuilt sklearn pickle"}</Meta>
          <Meta label="Created">{formatDateTime(deployment.created_at)}</Meta>
          <Meta label="Endpoint">{deployment.endpoint_url ?? "Pending"}</Meta>
          <Meta label="Image">{deployment.image_ref ?? "File-backed model"}</Meta>
        </div>

        <div className="space-y-2">
          <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Labels</p>
          <LabelChips labels={deployment.labels} />
        </div>
      </Panel>
    </Link>
  );
}

function CreateDeploymentDrawer({ onClose }: { onClose: () => void }) {
  const [mode, setMode] = useState<DeploymentMode>("file");
  const [selectedModelKey, setSelectedModelKey] = useState("");
  const [selectedImage, setSelectedImage] = useState<SelectedImageTag | null>(null);
  const [modelSearch, setModelSearch] = useState("");
  const [imageSearch, setImageSearch] = useState("");
  const [registryTokenName, setRegistryTokenName] = useState("");
  const [issuedRegistryToken, setIssuedRegistryToken] = useState<IssuedRegistryToken | null>(null);
  const [deploymentName, setDeploymentName] = useState("");
  const [labelsJson, setLabelsJson] = useState("{}");
  const [inputSchemaJson, setInputSchemaJson] = useState("{}");
  const [outputSchemaJson, setOutputSchemaJson] = useState("{}");
  const [formError, setFormError] = useState("");
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const modelOptionsQuery = useQuery({
    enabled: mode === "file",
    queryKey: ["deployable-model-options"],
    queryFn: async () => {
      const repositoryPage = await api.listRepositoriesPage({ limit: 100, sort_by: "created_at", sort_dir: "desc" });
      const modelsByRepository = await Promise.all(
        repositoryPage.items.map(async (repository) => ({
          repository,
          models: (await api.listModelsPage(repository.slug, { limit: 100, sort_by: "created_at", sort_dir: "desc" })).items,
        })),
      );
      return modelsByRepository.flatMap(({ repository, models }) =>
        models
          .filter((model) => model.status === "READY" && model.file_type === "pickle")
          .map((model) => ({ repository, model })),
      );
    },
  });

  const registryStatusQuery = useQuery({
    enabled: mode === "image",
    queryKey: ["artifact-registry-status"],
    queryFn: api.getArtifactRegistryStatus,
  });

  const registryTokensQuery = useQuery({
    enabled: mode === "image" && registryStatusQuery.data?.enabled === true,
    queryKey: ["artifact-registry-tokens"],
    queryFn: api.listRegistryTokens,
  });

  const artifactImagesQuery = useQuery({
    enabled: mode === "image" && registryStatusQuery.data?.enabled === true,
    queryKey: ["artifact-registry-images", imageSearch],
    queryFn: async () => (await api.listArtifactImagesPage({ search: imageSearch, limit: 25 })).items,
  });

  const selectedModel = useMemo(
    () => modelOptionsQuery.data?.find((option) => modelKey(option) === selectedModelKey) ?? null,
    [modelOptionsQuery.data, selectedModelKey],
  );

  const enableRegistryMutation = useMutation({
    mutationFn: api.enableArtifactRegistry,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["artifact-registry-status"] });
      await queryClient.invalidateQueries({ queryKey: ["artifact-registry-images"] });
    },
  });

  const createRegistryTokenMutation = useMutation({
    mutationFn: api.createRegistryToken,
    onSuccess: (token) => {
      setIssuedRegistryToken(token);
      setRegistryTokenName("");
      void queryClient.invalidateQueries({ queryKey: ["artifact-registry-tokens"] });
    },
  });

  const revokeRegistryTokenMutation = useMutation({
    mutationFn: api.revokeRegistryToken,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["artifact-registry-tokens"] });
    },
  });

  const createDeploymentMutation = useMutation({
    mutationFn: async () => {
      const labels = parseJsonObject(labelsJson, "Labels");
      const inputSchema = parseNullableJsonObject(inputSchemaJson, "Input schema");
      const outputSchema = parseNullableJsonObject(outputSchemaJson, "Output schema");
      const payload = {
        name: deploymentName.trim(),
        labels,
        input_schema: inputSchema,
        output_schema: outputSchema,
      };

      if (mode === "file") {
        if (!selectedModel) {
          throw new ApiError(422, "Choose a READY pickle model.");
        }
        return api.createModelDeployment(selectedModel.repository.slug, selectedModel.model.version, payload);
      }

      if (!selectedImage) {
        throw new ApiError(422, "Choose a custom image tag.");
      }
      return api.createArtifactImageDeployment(selectedImage.image.name, selectedImage.tag.tag, payload);
    },
    onSuccess: (deployment) => {
      navigate(`/deployments/${deployment.slug}`);
      void queryClient.invalidateQueries({ queryKey: ["deployments"] });
    },
  });

  async function handleCreateRegistryToken() {
    await createRegistryTokenMutation.mutateAsync({ name: registryTokenName });
  }

  async function handleCreateDeployment(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    if (!deploymentName.trim()) {
      setFormError("Choose a deployment name.");
      return;
    }
    try {
      await createDeploymentMutation.mutateAsync();
    } catch (error) {
      setFormError(error instanceof ApiError ? error.detail : error instanceof Error ? error.message : "The deployment could not be created.");
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-ink/35 backdrop-blur-sm" role="dialog" aria-modal="true">
      <div className="ml-auto flex h-full w-full max-w-5xl flex-col border-l border-border bg-mist shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-border bg-paper px-6 py-5">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.28em] text-olive">Create deployment</p>
            <h2 className="mt-1 text-2xl font-semibold tracking-[-0.03em]">Choose a serving source</h2>
          </div>
          <button
            aria-label="Close create deployment drawer"
            className="rounded-full border border-border bg-white p-2 text-stone-600 transition hover:border-accent hover:text-accent"
            onClick={onClose}
            type="button"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
          <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
            <div className="space-y-3">
              <SourceOption
                active={mode === "file"}
                description="Use the platform sklearn-pickle serving image with a READY pickle model artifact."
                icon={<PackageOpen className="h-5 w-5" />}
                label="Prebuilt sklearn pickle"
                onClick={() => setMode("file")}
              />
              <SourceOption
                active={mode === "image"}
                description="Deploy a container image pushed to your managed Gitea registry namespace."
                icon={<Container className="h-5 w-5" />}
                label="Custom image"
                onClick={() => setMode("image")}
              />
            </div>

            <form className="space-y-5" onSubmit={handleCreateDeployment}>
              {mode === "file" ? (
                <ModelPicker
                  modelOptions={modelOptionsQuery.data ?? []}
                  modelSearch={modelSearch}
                  selectedModelKey={selectedModelKey}
                  setModelSearch={setModelSearch}
                  setSelectedModelKey={setSelectedModelKey}
                  isLoading={modelOptionsQuery.isLoading}
                  isError={modelOptionsQuery.isError}
                />
              ) : (
                <ImagePicker
                  artifactImagesQuery={artifactImagesQuery}
                  enableRegistryMutation={enableRegistryMutation}
                  issuedRegistryToken={issuedRegistryToken}
                  registryStatusQuery={registryStatusQuery}
                  registryTokenName={registryTokenName}
                  registryTokensQuery={registryTokensQuery}
                  revokeRegistryTokenMutation={revokeRegistryTokenMutation}
                  selectedImage={selectedImage}
                  imageSearch={imageSearch}
                  setImageSearch={setImageSearch}
                  setIssuedRegistryToken={setIssuedRegistryToken}
                  setRegistryTokenName={setRegistryTokenName}
                  setSelectedImage={setSelectedImage}
                  onCreateRegistryToken={() => void handleCreateRegistryToken()}
                />
              )}

              <Panel className="space-y-4 bg-paper/70 shadow-none">
                <SectionTitle title="Configuration" description="Schemas are passed through to the gateway and custom plot discovery." />
                <label className="block space-y-2">
                  <span className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">Deployment name</span>
                  <input
                    className="w-full rounded-2xl border border-border bg-paper px-4 py-3 text-sm outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/20"
                    onChange={(event) => setDeploymentName(event.target.value)}
                    placeholder={mode === "file" ? "fraud pickle prod" : selectedImage ? `${selectedImage.image.name} prod` : "custom image prod"}
                    value={deploymentName}
                  />
                </label>
                <JsonTextArea label="Labels JSON" onChange={setLabelsJson} value={labelsJson} />
                <JsonTextArea label="Input schema JSON" onChange={setInputSchemaJson} value={inputSchemaJson} />
                <JsonTextArea label="Output schema JSON" onChange={setOutputSchemaJson} value={outputSchemaJson} />
                {formError ? <p className="text-sm text-danger">{formError}</p> : null}
                <div className="flex flex-wrap items-center gap-3">
                  <PrimaryButton disabled={createDeploymentMutation.isPending} type="submit">
                    {createDeploymentMutation.isPending ? "Creating..." : "Deploy"}
                  </PrimaryButton>
                  <SecondaryButton onClick={onClose} type="button">
                    Cancel
                  </SecondaryButton>
                </div>
              </Panel>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}

function SourceOption({
  active,
  description,
  icon,
  label,
  onClick,
}: {
  active: boolean;
  description: string;
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      aria-pressed={active}
      className={`w-full rounded-[20px] border p-4 text-left transition ${active ? "border-accent/60 bg-accent/10" : "border-border bg-paper/75 hover:border-accent/35 hover:bg-white"}`}
      onClick={onClick}
      type="button"
    >
      <div className="flex items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-white text-accent">{icon}</span>
        <span className="font-semibold">{label}</span>
      </div>
      <p className="mt-3 text-sm text-stone-600">{description}</p>
    </button>
  );
}

function ModelPicker({
  modelOptions,
  modelSearch,
  selectedModelKey,
  setModelSearch,
  setSelectedModelKey,
  isLoading,
  isError,
}: {
  modelOptions: ModelOption[];
  modelSearch: string;
  selectedModelKey: string;
  setModelSearch: (value: string) => void;
  setSelectedModelKey: (value: string) => void;
  isLoading: boolean;
  isError: boolean;
}) {
  const filteredOptions = useMemo(() => {
    const needle = modelSearch.trim().toLowerCase();
    if (!needle) {
      return modelOptions;
    }
    return modelOptions.filter((option) =>
      `${option.repository.name} ${option.repository.slug} ${option.model.name} ${option.model.version} ${option.model.status}`
        .toLowerCase()
        .includes(needle),
    );
  }, [modelOptions, modelSearch]);

  if (isLoading) {
    return <LoadingCard label="Loading READY pickle models" />;
  }
  if (isError) {
    return <ErrorState description="The model list could not be loaded." />;
  }
  return (
    <Panel className="space-y-4 bg-paper/70 shadow-none">
      <SectionTitle title="Model artifact" description="Only READY pickle models are shown for the prebuilt serving image." />
      <SearchInput placeholder="Filter models by repository, name, or version" value={modelSearch} onChange={setModelSearch} />
      {filteredOptions.length === 0 ? (
        <p className="text-sm text-stone-500">No READY pickle models are available yet.</p>
      ) : (
        <div className="grid gap-3">
          {filteredOptions.map((option) => {
            const key = modelKey(option);
            const active = key === selectedModelKey;
            return (
              <button
                aria-pressed={active}
                className={`flex items-center justify-between gap-4 rounded-2xl border px-4 py-3 text-left transition ${active ? "border-accent/60 bg-accent/10" : "border-border bg-white/60 hover:border-accent/35 hover:bg-white"}`}
                key={key}
                onClick={() => setSelectedModelKey(key)}
                type="button"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold">{option.model.name}</p>
                  <p className="font-mono text-xs text-stone-500">
                    {option.repository.slug} / {option.model.version}
                  </p>
                </div>
                <ChevronRight className="h-4 w-4 shrink-0 text-stone-400" />
              </button>
            );
          })}
        </div>
      )}
    </Panel>
  );
}

function ImagePicker({
  artifactImagesQuery,
  enableRegistryMutation,
  issuedRegistryToken,
  registryStatusQuery,
  registryTokenName,
  registryTokensQuery,
  revokeRegistryTokenMutation,
  selectedImage,
  imageSearch,
  setImageSearch,
  setIssuedRegistryToken,
  setRegistryTokenName,
  setSelectedImage,
  onCreateRegistryToken,
}: {
  artifactImagesQuery: { data?: ArtifactImage[]; isLoading: boolean; isError: boolean };
  enableRegistryMutation: { isPending: boolean; mutate: () => void };
  issuedRegistryToken: IssuedRegistryToken | null;
  registryStatusQuery: {
    data?: Awaited<ReturnType<typeof api.getArtifactRegistryStatus>>;
    isLoading: boolean;
    isError: boolean;
  };
  registryTokenName: string;
  registryTokensQuery: { data?: Awaited<ReturnType<typeof api.listRegistryTokens>> };
  revokeRegistryTokenMutation: { isPending: boolean; mutate: (name: string) => void };
  selectedImage: SelectedImageTag | null;
  imageSearch: string;
  setImageSearch: (value: string) => void;
  setIssuedRegistryToken: (token: IssuedRegistryToken | null) => void;
  setRegistryTokenName: (value: string) => void;
  setSelectedImage: (value: SelectedImageTag) => void;
  onCreateRegistryToken: () => void;
}) {
  const registryStatus = registryStatusQuery.data;
  const tokens = registryTokensQuery.data ?? [];
  const images = artifactImagesQuery.data ?? [];

  if (registryStatusQuery.isLoading) {
    return <LoadingCard label="Loading artifact registry" />;
  }
  if (registryStatusQuery.isError) {
    return <ErrorState description="The artifact registry status could not be loaded." />;
  }
  if (!registryStatus?.enabled) {
    return (
      <Panel className="space-y-4 bg-paper/70 shadow-none">
        <SectionTitle title="Artifact registry" description="Enable custom image deployments for this account." />
        <div className="flex items-center justify-between gap-4">
          <p className="text-sm text-stone-600">Custom image deployments are not enabled yet.</p>
          <PrimaryButton disabled={enableRegistryMutation.isPending} onClick={() => enableRegistryMutation.mutate()} type="button">
            {enableRegistryMutation.isPending ? "Enabling..." : "Enable registry"}
          </PrimaryButton>
        </div>
      </Panel>
    );
  }

  return (
    <Panel className="space-y-5 bg-paper/70 shadow-none">
      <SectionTitle title="Custom image" description="Images are loaded on demand from the managed registry." />
      <div className="grid gap-3 md:grid-cols-2">
        <Meta label="Namespace">{registryStatus.namespace}</Meta>
        <Meta label="Docker login">{registryStatus.docker_login_command}</Meta>
      </div>

      <div className="flex flex-col gap-3 md:flex-row">
        <input
          className="min-w-0 flex-1 rounded-full border border-border bg-paper px-4 py-3 outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
          onChange={(event) => setRegistryTokenName(event.target.value)}
          placeholder="docker-workstation"
          value={registryTokenName}
        />
        <SecondaryButton disabled={!registryTokenName.trim()} onClick={onCreateRegistryToken} type="button">
          Create Docker token
        </SecondaryButton>
      </div>

      {issuedRegistryToken ? (
        <div className="rounded-[20px] border border-accent/25 bg-accent/8 p-4">
          <p className="font-mono text-xs uppercase tracking-[0.24em] text-accent">One-time plaintext token</p>
          <p className="mt-3 break-all rounded-2xl bg-paper px-4 py-3 font-mono text-sm">{issuedRegistryToken.token}</p>
          <p className="mt-3 break-all font-mono text-sm text-stone-600">{issuedRegistryToken.docker_login_command}</p>
          <SecondaryButton className="mt-4" onClick={() => setIssuedRegistryToken(null)} type="button">
            Dismiss
          </SecondaryButton>
        </div>
      ) : null}

      {tokens.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {tokens.map((token) => (
            <button
              className="rounded-full border border-border bg-white px-3 py-1 font-mono text-[11px] text-stone-600 transition hover:border-danger hover:text-danger"
              disabled={revokeRegistryTokenMutation.isPending}
              key={token.name}
              onClick={() => revokeRegistryTokenMutation.mutate(token.name)}
              type="button"
            >
              {token.name} · revoke
            </button>
          ))}
        </div>
      ) : null}

      <SearchInput placeholder="Filter images by name, tag, or reference" value={imageSearch} onChange={setImageSearch} />

      {artifactImagesQuery.isLoading ? (
        <LoadingCard label="Loading images" />
      ) : artifactImagesQuery.isError ? (
        <ErrorState description="The image list could not be loaded." />
      ) : images.length === 0 ? (
        <p className="text-sm text-stone-500">No custom images have been pushed yet.</p>
      ) : (
        <div className="grid gap-3">
          {images.map((image) => (
            <CompactImageCard image={image} key={image.name} selected={selectedImage} onSelect={(tag) => setSelectedImage({ image, tag })} />
          ))}
        </div>
      )}
    </Panel>
  );
}

function CompactImageCard({
  image,
  selected,
  onSelect,
}: {
  image: ArtifactImage;
  selected: SelectedImageTag | null;
  onSelect: (tag: ArtifactImageTag) => void;
}) {
  return (
    <div className="rounded-2xl border border-border bg-white/70 p-4">
      <div className="flex items-center gap-3">
        <Boxes className="h-5 w-5 text-olive" />
        <h3 className="min-w-0 truncate text-base font-semibold">{image.name}</h3>
      </div>
      <div className="mt-3 grid gap-2">
        {image.tags.map((tag) => {
          const active = selected?.image.name === image.name && selected.tag.tag === tag.tag;
          return (
            <button
              aria-pressed={active}
              className={`grid gap-2 rounded-xl border px-3 py-2 text-left text-sm transition md:grid-cols-[140px_minmax(0,1fr)_160px] md:items-center ${active ? "border-accent/60 bg-accent/10" : "border-border bg-paper/70 hover:border-accent/35 hover:bg-white"}`}
              key={tag.image_ref}
              onClick={() => onSelect(tag)}
              type="button"
            >
              <span className="font-mono text-xs text-ink">{tag.tag}</span>
              <span className="min-w-0 truncate font-mono text-xs text-stone-500">{tag.image_ref}</span>
              <span className="text-xs text-stone-500">{tag.created_at ? formatDateTime(tag.created_at) : "Unknown"}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function JsonTextArea({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="block space-y-2">
      <span className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">{label}</span>
      <textarea
        className="min-h-20 w-full resize-y rounded-2xl border border-border bg-paper px-4 py-3 font-mono text-xs outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/20"
        onChange={(event) => onChange(event.target.value)}
        value={value}
      />
    </label>
  );
}

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0 rounded-2xl border border-border bg-paper/75 p-4">
      <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">{label}</p>
      <div className="mt-2 break-words text-sm text-stone-700">{children}</div>
    </div>
  );
}

function parseNullableJsonObject(value: string, label: string): Record<string, unknown> | null {
  const trimmed = value.trim();
  if (!trimmed || trimmed === "null") {
    return null;
  }
  return parseJsonObject(trimmed, label);
}

function parseJsonObject(value: string, label: string): Record<string, unknown> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error(`${label} must be valid JSON.`);
  }
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error(`${label} must be a JSON object.`);
  }
  return parsed as Record<string, unknown>;
}

function modelKey(option: ModelOption) {
  return `${option.repository.slug}:${option.model.version}`;
}

const IN_PROGRESS_DEPLOYMENT_STATUSES = new Set(["PENDING", "DEPLOYING", "DELETING"]);

function isDeploymentInProgress(status: string) {
  return IN_PROGRESS_DEPLOYMENT_STATUSES.has(status);
}
