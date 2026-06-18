import { useMemo } from "react";

import { createDefaultApiClient } from "./apiClient";
import { WorkbenchContext } from "./workbenchContext";
import { WorkbenchService, type WorkbenchGateway } from "./workbenchService";

interface WorkbenchProviderProps {
  children: React.ReactNode;
  service?: WorkbenchGateway;
}

export function WorkbenchProvider({ children, service }: WorkbenchProviderProps) {
  const value = useMemo(
    () => service ?? new WorkbenchService(createDefaultApiClient()),
    [service],
  );
  return <WorkbenchContext.Provider value={value}>{children}</WorkbenchContext.Provider>;
}
