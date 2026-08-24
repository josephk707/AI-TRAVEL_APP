import { apiGet, ApiError } from "../client";

describe("apiGet", () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
    jest.restoreAllMocks();
  });

  it("returns the parsed JSON body on a 2xx response", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: { status: "ok" } }),
    }) as unknown as typeof fetch;

    const result = await apiGet<{ data: { status: string } }>("/healthz");
    expect(result.data.status).toBe("ok");
  });

  it("throws a typed ApiError using the standard error envelope on a non-2xx response", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ error: { code: "NOT_FOUND", message: "nope" } }),
    }) as unknown as typeof fetch;

    await expect(apiGet("/missing")).rejects.toMatchObject({
      status: 404,
      code: "NOT_FOUND",
      message: "nope",
    });
  });

  it("wraps a network failure in ApiError instead of letting it propagate raw", async () => {
    global.fetch = jest.fn().mockRejectedValue(new Error("connection refused"));

    const error = await apiGet("/healthz").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("NETWORK_ERROR");
  });
});
