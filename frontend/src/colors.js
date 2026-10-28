// Swatch for each colour label produced by the classifier (VCoR classes).
export const SWATCH = {
  beige: "#d9c7a3",
  black: "#1b1b1b",
  blue: "#2f6fdb",
  brown: "#7a4a2a",
  gold: "#c9a227",
  green: "#2e8b57",
  grey: "#8a8f98",
  gray: "#8a8f98",
  orange: "#ee7a1c",
  pink: "#e57fb0",
  purple: "#7d4bc2",
  red: "#d23b3b",
  silver: "#c4c9d0",
  tan: "#c19a6b",
  white: "#f4f4f2",
  yellow: "#f2d02b",
  unknown: "transparent",
};

export const swatch = (c) => SWATCH[(c || "unknown").toLowerCase()] ?? "#888";
