import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider } from "@/hooks/use-auth";
import { ProtectedLayout, PublicOnlyRoute } from "@/components/routes";
import { AccountPage } from "@/pages/account-page";
import { DatasetDetailPage } from "@/pages/dataset-detail-page";
import { DatasetsPage } from "@/pages/datasets-page";
import { DeploymentDetailPage } from "@/pages/deployment-detail-page";
import { DeploymentsPage } from "@/pages/deployments-page";
import { ExperimentDetailPage } from "@/pages/experiment-detail-page";
import { ExperimentsPage } from "@/pages/experiments-page";
import { LoginPage } from "@/pages/login-page";
import { ModelDetailPage } from "@/pages/model-detail-page";
import { NotFoundPage } from "@/pages/not-found-page";
import { OverviewPage } from "@/pages/overview-page";
import { RegisterPage } from "@/pages/register-page";
import { RepositoryDetailPage } from "@/pages/repository-detail-page";
import { RepositoriesPage } from "@/pages/repositories-page";
import { RunDetailPage } from "@/pages/run-detail-page";

export function App() {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route element={<PublicOnlyRoute />}>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
            </Route>

            <Route element={<ProtectedLayout />}>
              <Route path="/" element={<Navigate replace to="/overview" />} />
              <Route path="/overview" element={<OverviewPage />} />
              <Route path="/experiments" element={<ExperimentsPage />} />
              <Route path="/experiments/:slug" element={<ExperimentDetailPage />} />
              <Route path="/experiments/:slug/runs/:runNumber" element={<RunDetailPage />} />
              <Route path="/datasets" element={<DatasetsPage />} />
              <Route path="/datasets/:slug/versions/:version" element={<DatasetDetailPage />} />
              <Route path="/repositories" element={<RepositoriesPage />} />
              <Route path="/repositories/:slug" element={<RepositoryDetailPage />} />
              <Route path="/repositories/:slug/models/:version" element={<ModelDetailPage />} />
              <Route path="/deployments" element={<DeploymentsPage />} />
              <Route path="/deployments/:slug" element={<DeploymentDetailPage />} />
              <Route path="/account" element={<AccountPage />} />
            </Route>

            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
