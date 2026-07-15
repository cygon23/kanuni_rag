import { Suspense } from "react";

import { DocumentsExperience } from "@/components/DocumentsExperience";

export default function DocumentsPage() {
  return (
    <Suspense fallback={null}>
      <DocumentsExperience />
    </Suspense>
  );
}
