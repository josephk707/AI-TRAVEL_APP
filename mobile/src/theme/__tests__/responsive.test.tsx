import { renderHook } from "@testing-library/react-native";

import { computeResponsive, layout, useResponsive, widthClassFor } from "../responsive";
import { spacing } from "../tokens";

describe("widthClassFor", () => {
  it("classifies phone, tablet and desktop widths", () => {
    expect(widthClassFor(320)).toBe("compact");
    expect(widthClassFor(599)).toBe("compact");
    expect(widthClassFor(600)).toBe("medium");
    expect(widthClassFor(1023)).toBe("medium");
    expect(widthClassFor(1024)).toBe("expanded");
    expect(widthClassFor(1920)).toBe("expanded");
  });
});

describe("computeResponsive", () => {
  it("keeps a phone full-width with the compact gutter and a single column", () => {
    const r = computeResponsive(390, 844);

    expect(r.isCompact).toBe(true);
    expect(r.isWide).toBe(false);
    expect(r.isLandscape).toBe(false);
    expect(r.horizontalPadding).toBe(spacing.lg);
    expect(r.contentWidth).toBe(390);
    expect(r.columnsFor(280)).toBe(1);
  });

  it("uses the wider gutter and two columns on a tablet", () => {
    const r = computeResponsive(820, 1180);

    expect(r.isMedium).toBe(true);
    expect(r.isWide).toBe(true);
    expect(r.horizontalPadding).toBe(spacing.xl);
    expect(r.contentWidth).toBe(layout.contentMaxWidth);
    expect(r.columnsFor(280)).toBe(2);
  });

  it("caps the content column and yields multiple grid columns in a desktop browser", () => {
    const r = computeResponsive(1440, 900);

    expect(r.isExpanded).toBe(true);
    expect(r.isLandscape).toBe(true);
    expect(r.contentWidth).toBe(layout.contentMaxWidth);
    // 720 - 2*32 = 656 usable; (656 + 16) / (280 + 16) = 2.27 -> 2 columns
    expect(r.columnsFor(280)).toBe(2);
    expect(r.columnsFor(200)).toBe(3);
  });

  it("honours a wider column budget when asked", () => {
    const r = computeResponsive(1440, 900, layout.wideMaxWidth);

    expect(r.contentWidth).toBe(layout.wideMaxWidth);
    expect(r.columnsFor(280)).toBe(3);
  });

  it("never returns fewer than one column", () => {
    expect(computeResponsive(240, 400).columnsFor(400)).toBe(1);
  });
});

describe("useResponsive", () => {
  it("reads the window size and exposes the derived layout values", async () => {
    const { result } = await renderHook(() => useResponsive());

    expect(typeof result.current.width).toBe("number");
    expect(typeof result.current.height).toBe("number");
    expect(["compact", "medium", "expanded"]).toContain(result.current.widthClass);
    expect(result.current.columnsFor(100)).toBeGreaterThanOrEqual(1);
  });
});
