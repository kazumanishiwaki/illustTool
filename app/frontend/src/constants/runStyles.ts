export const DEFAULT_RUN_STYLE_IDS = [
  "naive_wobbly_line",
  "grain_flat",
  "print_relief_lino",
  "editorial_outline_minimal",
  "flat_vector",
] as const;

export type AppTab = "generate" | "import" | "review" | "styles";

export const APP_TABS: AppTab[] = ["generate", "import", "review", "styles"];
