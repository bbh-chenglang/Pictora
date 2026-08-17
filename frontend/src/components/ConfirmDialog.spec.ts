import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("ConfirmDialog theme", () => {
  it("uses snowfall tokens for its overlay, surface, and destructive action", () => {
    const source = readFileSync(resolve(process.cwd(), "src/components/ConfirmDialog.vue"), "utf8");
    expect(source).toContain("var(--prompt-snow-overlay)");
    expect(source).toContain("var(--prompt-snow-surface)");
    expect(source).toContain("var(--prompt-snow-danger)");
  });
});
