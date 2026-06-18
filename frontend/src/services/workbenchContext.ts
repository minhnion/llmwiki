import { createContext } from "react";

import type { WorkbenchGateway } from "./workbenchService";

export const WorkbenchContext = createContext<WorkbenchGateway | null>(null);
