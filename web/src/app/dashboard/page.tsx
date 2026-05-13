"use client";

export default function DashboardPage() {
  return (
    <div className="flex flex-col min-h-screen">
      <nav className="flex justify-between items-center px-8 py-3 border-b border-khaki">
        <div className="flex items-center gap-5">
          <span className="font-serif text-base tracking-wide">THOTH</span>
          <span className="text-umber text-[13px]">Dashboard</span>
        </div>
      </nav>

      <main className="flex-1 max-w-[720px] mx-auto w-full px-6 py-8">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h1 className="font-serif text-[22px] italic text-espresso">My Articles</h1>
            <p className="text-umber text-xs mt-1">0 articles</p>
          </div>
          <button className="bg-espresso text-ivory px-5 py-2.5 text-xs rounded-[3px] tracking-wide">
            + New Article
          </button>
        </div>
        <p className="text-stone text-sm">No articles yet. Create your first article to get started.</p>
      </main>
    </div>
  );
}
