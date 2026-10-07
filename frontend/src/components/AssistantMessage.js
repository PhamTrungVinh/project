import { createElement } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Convert only explicit line breaks; leave other raw HTML disabled.
function remarkLineBreaks() {
  return function transform(node) {
    if (!node.children) return;
    node.children = node.children.map((child) => {
      if (child.type === "html" && /^<br\s*\/?\s*>$/i.test(child.value.trim())) {
        return { type: "break" };
      }
      transform(child);
      return child;
    });
  };
}

const components = {
  table: ({ children }) => createElement("div", { className: "chat-table" },
    createElement("table", null, children)),
  a: ({ href, children }) => createElement("a", { href, target: "_blank", rel: "noopener noreferrer" }, children),
};

export default function AssistantMessage({ text }) {
  return createElement(Markdown, {
    remarkPlugins: [remarkGfm, remarkLineBreaks], skipHtml: true, components,
  }, text);
}
