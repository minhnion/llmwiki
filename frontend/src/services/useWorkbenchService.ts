import { useContext } from "react";

import { WorkbenchContext } from "./workbenchContext";
import type { WorkbenchGateway } from "./workbenchService";

export function useWorkbenchService(): WorkbenchGateway {
  const service = useContext(WorkbenchContext);
  if (!service) {
    throw new Error("WorkbenchProvider is required.");
  }
  return service;
}
