import ReactMarkdown from "react-markdown";

export default function MarkdownRenderer({ content }: { content: string }) {
  return (
    <div className="prose prose-invert prose-sm max-w-none
      prose-headings:text-slate-100 prose-headings:font-semibold
      prose-p:text-slate-300 prose-p:leading-relaxed
      prose-strong:text-slate-100
      prose-code:text-brand-400 prose-code:bg-slate-800 prose-code:px-1 prose-code:rounded
      prose-ul:text-slate-300 prose-li:text-slate-300
      prose-blockquote:border-brand-500 prose-blockquote:text-slate-400
      prose-hr:border-slate-800">
      <ReactMarkdown>{content}</ReactMarkdown>
    </div>
  );
}
