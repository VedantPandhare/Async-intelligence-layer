export default function Spinner({ className = "w-6 h-6" }: { className?: string }) {
  return (
    <div className={`${className} border-2 border-slate-700 border-t-slate-300 rounded-full animate-spin`} />
  );
}
