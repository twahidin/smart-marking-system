export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

async function parse(res: Response) {
  if (res.status === 204) return null;
  const text = await res.text();
  let body: any = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = null; }
  if (!res.ok) {
    const err = body?.error ?? { code: "http_" + res.status, message: text || res.statusText };
    throw new ApiError(res.status, err.code, err.message);
  }
  return body;
}

const json = (method: string) => async <T>(path: string, body?: unknown): Promise<T> =>
  parse(await fetch(path, { method, headers: body === undefined ? {} : { "Content-Type": "application/json" },
                            body: body === undefined ? undefined : JSON.stringify(body), credentials: "same-origin" }));

export const api = {
  get: json("GET"),
  post: json("POST"),
  put: json("PUT"),
  async postForm<T>(path: string, form: FormData): Promise<T> {
    return parse(await fetch(path, { method: "POST", body: form, credentials: "same-origin" }));
  },
};
