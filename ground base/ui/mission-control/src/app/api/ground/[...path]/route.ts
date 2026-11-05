export const dynamic = "force-dynamic";

async function proxy(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const token = process.env.GROUND_OPERATOR_TOKEN;
  if (!token) {
    return Response.json(
      { ok: false, error: { code: "unauthorized", detail: "GROUND_OPERATOR_TOKEN is not set" } },
      { status: 500 },
    );
  }
  const { path } = await context.params;
  const incoming = new URL(request.url);
  const origin = process.env.GROUND_API_ORIGIN ?? "http://127.0.0.1:8765";
  const target = `${origin}/api/v1/${path.join("/")}${incoming.search}`;
  const headers = new Headers();
  headers.set("x-ground-operator-token", token);
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  const idempotency = request.headers.get("idempotency-key");
  if (idempotency) headers.set("idempotency-key", idempotency);
  const init: RequestInit = { method: request.method, headers, cache: "no-store" };
  if (request.method !== "GET" && request.method !== "HEAD") init.body = await request.text();
  const response = await fetch(target, init);
  const outgoing = new Headers();
  const type = response.headers.get("content-type");
  if (type) outgoing.set("content-type", type);
  outgoing.set("cache-control", "no-store");
  return new Response(response.body, { status: response.status, headers: outgoing });
}

export const GET = proxy;
export const POST = proxy;
