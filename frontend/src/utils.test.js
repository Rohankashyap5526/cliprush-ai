import { describe, expect, it } from "vitest";
import { DEFAULT_OPTS, PRESETS, formatTime, slug, socialCaption, validateOpts } from "./utils";

const video = { metadata: { duration: 600, has_audio: true } };

describe("validateOpts", () => {
  it("accepts defaults", () => expect(validateOpts(DEFAULT_OPTS, video)).toBe(""));
  it("accepts every preset", () => {
    for (const p of PRESETS) expect(validateOpts({ ...DEFAULT_OPTS, ...p.set }, video)).toBe("");
  });
  it("catches max < min, typed-as-string numbers and range errors", () => {
    expect(validateOpts({ ...DEFAULT_OPTS, min_duration: "40", max_duration: "20" }, video)).toMatch(/shorter than the minimum/);
    expect(validateOpts({ ...DEFAULT_OPTS, min_duration: "" }, video)).toMatch(/Minimum/);
    expect(validateOpts({ ...DEFAULT_OPTS, max_duration: 500 }, video)).toMatch(/Maximum/);
    expect(validateOpts({ ...DEFAULT_OPTS, clip_count: 99 }, video)).toMatch(/1 and 20/);
  });
  it("explains short videos and missing audio", () => {
    expect(validateOpts(DEFAULT_OPTS, { metadata: { duration: 8, has_audio: true } })).toMatch(/only 8 s/);
    expect(validateOpts(DEFAULT_OPTS, { metadata: { duration: 100, has_audio: false } })).toMatch(/no audio/);
  });
});

describe("helpers", () => {
  it("formats time", () => { expect(formatTime(75)).toBe("1:15"); expect(formatTime(3725)).toBe("1:02:05"); expect(formatTime(undefined)).toBe("0:00"); });
  it("slugs safely", () => { expect(slug("Wait: what?! / ../x")).toBe("wait-what-x"); expect(slug("???")).toBe("clip"); });
  it("builds a social caption", () => {
    expect(socialCaption({ title: "T", description: "D", hashtags: ["#a", "#b"] })).toBe("T\n\nD\n\n#a #b");
    expect(socialCaption({ title: "T" })).toBe("T");
  });
});
