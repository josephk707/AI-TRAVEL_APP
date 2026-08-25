import { apiGet } from "../client";
import { fetchNearbyPois, fetchPoi, searchPois } from "../pois";

jest.mock("../client", () => ({
  apiGet: jest.fn(),
}));

const mockApiGet = apiGet as jest.Mock;

const SAMPLE_POI = {
  id: "11111111-1111-4111-8111-111111111111",
  name: "Taj Mahal",
  category: "heritage",
  location: { lat: 27.1751, lng: 78.0421 },
  address: "Agra",
  city: "Agra",
  region: "Uttar Pradesh",
  country: "India",
  opening_hours: null,
  avg_cost: null,
  source: "curated",
  is_heritage_flagship: false,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("searchPois", () => {
  afterEach(() => jest.clearAllMocks());

  it("builds the query string from the given params and maps the envelope", async () => {
    mockApiGet.mockResolvedValue({ data: [SAMPLE_POI], meta: null });

    const result = await searchPois({ query: "Taj Mahal", category: "heritage" });

    expect(mockApiGet).toHaveBeenCalledWith(
      expect.stringContaining("/v1/pois/search?"),
      undefined,
    );
    const calledUrl = mockApiGet.mock.calls[0][0] as string;
    expect(calledUrl).toContain("query=Taj+Mahal");
    expect(calledUrl).toContain("category=heritage");
    expect(result.pois).toEqual([SAMPLE_POI]);
    expect(result.degraded).toBe(false);
    expect(result.message).toBeNull();
  });

  it("surfaces meta.degraded_mode and meta.message when the backend degrades", async () => {
    mockApiGet.mockResolvedValue({
      data: [],
      meta: { degraded_mode: true, message: "Live search is temporarily unavailable." },
    });

    const result = await searchPois({ query: "somewhere obscure" });

    expect(result.degraded).toBe(true);
    expect(result.message).toBe("Live search is temporarily unavailable.");
  });

  it("omits undefined params from the query string", async () => {
    mockApiGet.mockResolvedValue({ data: [] });

    await searchPois({ query: "temple" });

    const calledUrl = mockApiGet.mock.calls[0][0] as string;
    expect(calledUrl).not.toContain("category=");
    expect(calledUrl).not.toContain("lat=");
  });
});

describe("fetchNearbyPois", () => {
  afterEach(() => jest.clearAllMocks());

  it("sends lat/lng/radius_m as query params", async () => {
    mockApiGet.mockResolvedValue({ data: [SAMPLE_POI] });

    const result = await fetchNearbyPois({ lat: 27.17, lng: 78.04, radiusM: 2000 });

    const calledUrl = mockApiGet.mock.calls[0][0] as string;
    expect(calledUrl).toContain("/v1/pois/nearby?");
    expect(calledUrl).toContain("lat=27.17");
    expect(calledUrl).toContain("lng=78.04");
    expect(calledUrl).toContain("radius_m=2000");
    expect(result).toEqual([SAMPLE_POI]);
  });
});

describe("fetchPoi", () => {
  afterEach(() => jest.clearAllMocks());

  it("requests the specific poi id and returns the unwrapped data", async () => {
    mockApiGet.mockResolvedValue({ data: SAMPLE_POI });

    const result = await fetchPoi("11111111-1111-4111-8111-111111111111");

    expect(mockApiGet).toHaveBeenCalledWith(
      "/v1/pois/11111111-1111-4111-8111-111111111111",
      undefined,
    );
    expect(result).toEqual(SAMPLE_POI);
  });
});
