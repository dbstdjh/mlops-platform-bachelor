import { Navigate, Outlet, useLocation } from "react-router-dom";

import { AppShell } from "@/components/app-shell";
import { LoadingCard } from "@/components/ui";
import { useAuth } from "@/hooks/use-auth";

export function ProtectedLayout() {
  const { isAuthenticated, isBootstrapping } = useAuth();
  const location = useLocation();

  if (isBootstrapping) {
    return (
      <div className="mx-auto max-w-xl p-6">
        <LoadingCard label="Bootstrapping session" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate replace state={{ from: location.pathname }} to="/login" />;
  }

  return <AppShell />;
}

export function PublicOnlyRoute() {
  const { isAuthenticated, isBootstrapping } = useAuth();

  if (isBootstrapping) {
    return null;
  }

  if (isAuthenticated) {
    return <Navigate replace to="/overview" />;
  }

  return <Outlet />;
}
