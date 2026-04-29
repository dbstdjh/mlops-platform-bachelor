import { groupDatasets } from "@/lib/datasets";

describe("groupDatasets", () => {
  it("groups versions by slug and sorts latest first", () => {
    const grouped = groupDatasets([
      {
        name: "Iris",
        slug: "iris",
        version: 1,
        status: "READY",
        file_type: "parquet",
        created_at: "2026-04-01T10:00:00Z",
        labels: {},
      },
      {
        name: "Iris",
        slug: "iris",
        version: 2,
        status: "PENDING",
        file_type: "parquet",
        created_at: "2026-04-02T10:00:00Z",
        labels: {},
      },
      {
        name: "Wine",
        slug: "wine",
        version: 1,
        status: "READY",
        file_type: "csv",
        created_at: "2026-04-03T10:00:00Z",
        labels: {},
      },
    ]);

    expect(grouped).toHaveLength(2);
    expect(grouped[0].slug).toBe("wine");
    expect(grouped[1].latest.version).toBe(2);
    expect(grouped[1].versions.map((item) => item.version)).toEqual([2, 1]);
  });
});
