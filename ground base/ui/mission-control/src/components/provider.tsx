"use client";

import { createContext, useContext, type ReactNode } from "react";
import { useOperator } from "@/hooks/useOperator";

export type SessionValue = ReturnType<typeof useOperator>;

type Session = SessionValue;

const SessionContext = createContext<Session | null>(null);

export function OperatorProvider({ children }: { children: ReactNode }) {
  const value = useOperator();
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useOptionalSession(): Session | null {
  return useContext(SessionContext);
}

export function useSession(): Session {
  const value = useOptionalSession();
  if (!value) throw new Error("OperatorProvider is required");
  return value;
}
