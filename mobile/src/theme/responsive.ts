/**
 * Responsive layout primitives (minimal monochrome theme phase).
 *
 * The app runs on phones, tablets and in a desktop browser
 * (react-native-web), so a single fixed phone layout is not enough.
 * Rather than a per-screen media-query sprawl, screens read a few
 * derived values from `useResponsive()` and every screen backdrop
 * (`components/Screen`) centres its content in a max-width column on
 * wide viewports. Width classes follow the Material "window size class"
 * thresholds, which map cleanly onto phone / tablet / desktop.
 */

import { useMemo } from "react";
import { useWindowDimensions } from "react-native";

import { spacing } from "./tokens";

export type WidthClass = "compact" | "medium" | "expanded";

export const breakpoints = {
  /** ≥ 600dp: large phones in landscape, small tablets. */
  medium: 600,
  /** ≥ 1024dp: tablets in landscape, desktop browsers. */
  expanded: 1024,
} as const;

export const layout = {
  /** Reading-width column for ordinary screens on wide viewports. */
  contentMaxWidth: 720,
  /** Wider column for screens that benefit from more room (maps, grids). */
  wideMaxWidth: 1080,
} as const;

export interface Responsive {
  width: number;
  height: number;
  widthClass: WidthClass;
  isCompact: boolean;
  isMedium: boolean;
  isExpanded: boolean;
  /** medium or expanded — anything wider than a phone in portrait. */
  isWide: boolean;
  isLandscape: boolean;
  /** Page gutter to use for horizontal padding at this width. */
  horizontalPadding: number;
  /** Width of the centred content column at this viewport width. */
  contentWidth: number;
  /** How many grid columns fit for cards of at least `minItemWidth`
   * inside the content column (never fewer than 1). */
  columnsFor: (minItemWidth: number, gap?: number) => number;
  /** Pixel width of one grid item when the content column is split into
   * `columns` with `gap` between them, inside a container padded by
   * `padding` on each side (defaults to this width's page gutter). */
  itemWidthFor: (columns: number, gap?: number, padding?: number) => number;
}

export function widthClassFor(width: number): WidthClass {
  if (width >= breakpoints.expanded) return "expanded";
  if (width >= breakpoints.medium) return "medium";
  return "compact";
}

/** Pure derivation, exported for tests and for non-hook call sites. */
export function computeResponsive(
  width: number,
  height: number,
  maxWidth: number = layout.contentMaxWidth,
): Responsive {
  const widthClass = widthClassFor(width);
  const isCompact = widthClass === "compact";
  const horizontalPadding = isCompact ? spacing.lg : spacing.xl;
  const contentWidth = Math.min(width, maxWidth);
  const columnsFor = (minItemWidth: number, gap: number = spacing.md): number => {
    const usable = contentWidth - horizontalPadding * 2;
    return Math.max(1, Math.floor((usable + gap) / (minItemWidth + gap)));
  };
  const itemWidthFor = (
    columns: number,
    gap: number = spacing.md,
    padding: number = horizontalPadding,
  ): number => {
    const usable = contentWidth - padding * 2;
    return Math.floor((usable - gap * (columns - 1)) / Math.max(1, columns));
  };
  return {
    width,
    height,
    widthClass,
    isCompact,
    isMedium: widthClass === "medium",
    isExpanded: widthClass === "expanded",
    isWide: !isCompact,
    isLandscape: width > height,
    horizontalPadding,
    contentWidth,
    columnsFor,
    itemWidthFor,
  };
}

export function useResponsive(maxWidth: number = layout.contentMaxWidth): Responsive {
  const { width, height } = useWindowDimensions();
  return useMemo(() => computeResponsive(width, height, maxWidth), [width, height, maxWidth]);
}
