import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const SKILLS_VIEW_SOURCE = readFileSync(resolve(process.cwd(), "src/components/SkillsView.vue"), "utf8");

describe("SkillsView category filter theme", () => {
  it("uses a snow-white category filter in the skill plaza", () => {
    expect(SKILLS_VIEW_SOURCE).toContain('.skills-toolbar select { background:#fff; color:#17191d;');
    expect(SKILLS_VIEW_SOURCE).toContain('.skills-toolbar select option { background:#fff; color:#17191d; }');
  });
});
