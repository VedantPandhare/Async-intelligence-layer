import Nav from "@/components/Nav";
import AuthGuard from "@/components/AuthGuard";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <div className="flex h-screen overflow-hidden bg-slate-950">
        <Nav />
        <main className="flex-1 overflow-y-auto p-7 lg:p-9">
          {children}
        </main>
      </div>
    </AuthGuard>
  );
}
