import { Link } from "react-router-dom";

import { EmptyState, PrimaryButton } from "@/components/ui";

export function NotFoundPage() {
  return (
    <div className="p-6">
      <EmptyState
        title="Page not found"
        description="The path you asked for does not exist in this Phase 1 dashboard."
        action={
          <Link to="/overview">
            <PrimaryButton type="button">Back to overview</PrimaryButton>
          </Link>
        }
      />
    </div>
  );
}
