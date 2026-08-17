import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("PromptEditorDialog theme", () => {
  it("uses snowfall tokens for layer, panel, and fields", () => {
    const source = readFileSync(resolve(process.cwd(), "src/components/PromptEditorDialog.vue"), "utf8");
    expect(source).toContain("var(--prompt-snow-overlay)");
    expect(source).toContain("var(--prompt-snow-surface)");
    expect(source).toContain("var(--prompt-snow-surface-muted)");
  });
});
