import type { ImageCategory } from "./api";

export const CATEGORIES: { value: ImageCategory; label: string }[] = [
  { value: "hero", label: "Hero" },
  { value: "amenities", label: "Amenities" },
  { value: "gallery", label: "Gallery" },
];

export const categoryLabel = (c: ImageCategory) => CATEGORIES.find((o) => o.value === c)?.label ?? c;
