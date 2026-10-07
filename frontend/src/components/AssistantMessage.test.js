import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import AssistantMessage from "./AssistantMessage.js";

const render = (text) => renderToStaticMarkup(createElement(AssistantMessage, { text }));

test("renders the policy table with line breaks inside cells", () => {
  const html = render("FPT policy\n\n| Area | Requirement |\n| --- | --- |\n| Training | **8 hours** per year.<br>All employees. |\n");
  assert.match(html, /<table>/);
  assert.match(html, /<th>Area<\/th>/);
  assert.match(html, /<strong>8 hours<\/strong>/);
  assert.match(html, /per year\.<br\/>\s*All employees\./);
  assert.doesNotMatch(html, /&lt;br|\| ---/);
});

test("partial streamed Markdown renders without errors", () => {
  for (const prefix of ["| Area", "| Area | Requirement |\n| ---", "**Training", "Hello <br"]) {
    assert.equal(typeof render(prefix), "string");
  }
});

test("raw HTML and unsafe links do not execute", () => {
  const html = render('<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>\n\n[link](javascript:alert(1))');
  assert.doesNotMatch(html, /<script|<img|onerror|href="javascript:/);
});
