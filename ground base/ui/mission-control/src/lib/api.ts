export function groundPath(path: string): string {
  const trimmed = path.replace(/^\/+/, "");
  return `/api/ground/${trimmed}`;
}

export function actionBody(sessionEpoch: number, extra: Record<string, unknown> = {}): Record<string, unknown> {
  return { session_epoch: sessionEpoch, ...extra };
}
