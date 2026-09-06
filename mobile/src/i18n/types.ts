/** Widens string-literal leaves (the `en` resource is `as const`) to
 * plain `string` so a translation file can provide any real translated
 * text for a key, not just the literal English string back. */
export type DeepPartial<T> = {
  [K in keyof T]?: T[K] extends string ? string : T[K] extends object ? DeepPartial<T[K]> : T[K];
};
