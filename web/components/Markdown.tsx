import { Fragment, type ReactNode } from "react";

// 助理回覆只會用到粗體、條列、小標，自己轉成 React 節點，不用 dangerouslySetInnerHTML
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? (
      <strong key={i} className="font-semibold text-ink">{part.slice(2, -2)}</strong>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
}

export function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let list: string[] = [];
  const flush = () => {
    if (list.length) {
      blocks.push(
        <ul key={`ul${blocks.length}`} className="my-2 space-y-1 pl-4">
          {list.map((li, i) => <li key={i} className="list-[circle] marker:text-river">{inline(li)}</li>)}
        </ul>,
      );
      list = [];
    }
  };
  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    const item = line.match(/^\s*(?:[-*・]|\d+\.)\s+(.*)$/);
    if (item) {
      list.push(item[1]);
      continue;
    }
    flush();
    if (!line.trim()) continue;
    const head = line.match(/^#{1,4}\s+(.*)$/);
    blocks.push(
      head ? (
        <p key={blocks.length} className="mt-3 font-semibold">{inline(head[1])}</p>
      ) : (
        <p key={blocks.length} className="my-1.5">{inline(line)}</p>
      ),
    );
  }
  flush();
  return <div className="leading-relaxed break-words">{blocks}</div>;
}
