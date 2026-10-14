import { Fragment, type ReactNode } from "react";

/** Inline `code` and **bold**; everything else is plain text (React escapes it). */
function inline(text: string): ReactNode[] {
  return text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).map((part, i) => {
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return (
        <code key={i} className="rounded-[4px] bg-surface-3 px-1 py-0.5 font-mono text-[0.85em]">
          {part.slice(1, -1)}
        </code>
      );
    }
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}

type Block = { kind: "p" | "ul" | "ol"; items: string[] };

function blocks(text: string): Block[] {
  const result: Block[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    const bullet = /^\s*[-*]\s+(.*)$/.exec(line);
    const numbered = /^\s*\d+\.\s+(.*)$/.exec(line);
    const last = result.at(-1);
    if (!line.trim()) {
      result.push({ kind: "p", items: [] });
    } else if (bullet || numbered) {
      const kind = bullet ? "ul" : "ol";
      const item = (bullet ?? numbered)![1];
      if (last?.kind === kind) last.items.push(item);
      else result.push({ kind, items: [item] });
    } else if (last && last.items.length) {
      // A continuation line belongs to the previous paragraph or list item.
      last.items[last.items.length - 1] += ` ${line.trim()}`;
    } else {
      result.push({ kind: "p", items: [line.trim()] });
    }
  }
  return result.filter((b) => b.items.length);
}

/** The small markdown subset runbooks use, rendered without any raw HTML. */
export function MarkdownLite({ text }: { text: string }) {
  return (
    <div className="flex flex-col gap-3 text-sm leading-relaxed text-fg-secondary">
      {blocks(text).map((block, i) => {
        if (block.kind === "p") return <p key={i}>{inline(block.items.join(" "))}</p>;
        const List = block.kind;
        return (
          <List key={i} className={`flex flex-col gap-1 pl-5 ${List === "ul" ? "list-disc" : "list-decimal"}`}>
            {block.items.map((item, j) => (
              <li key={j}>{inline(item)}</li>
            ))}
          </List>
        );
      })}
    </div>
  );
}
