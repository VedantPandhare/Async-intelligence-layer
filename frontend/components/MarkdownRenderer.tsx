import ReactMarkdown from "react-markdown";

export default function MarkdownRenderer({ content }: { content: string }) {
  return (
    <div className="prose prose-invert prose-sm max-w-none
      prose-headings:text-slate-100 prose-headings:font-semibold prose-headings:tracking-tight
      prose-p:text-slate-300 prose-p:leading-relaxed
      prose-strong:text-slate-100 prose-strong:font-semibold
      prose-code:text-slate-200 prose-code:bg-slate-800 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-xs
      prose-ul:text-slate-300 prose-li:text-slate-300
      prose-blockquote:border-slate-700 prose-blockquote:text-slate-400 prose-blockquote:not-italic
      prose-hr:border-slate-800">
      <ReactMarkdown>{content}</ReactMarkdown>
    </div>
  );
}
