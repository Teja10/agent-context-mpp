export default async function ArticlePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;

  return (
    <div className="flex flex-col min-h-screen">
      <nav className="flex justify-between items-center px-8 py-4 border-b border-khaki">
        <span className="font-serif text-lg tracking-wide">THOTH</span>
      </nav>

      <main className="flex-1 max-w-[560px] mx-auto px-6 py-8">
        <div className="text-umber text-[11px] uppercase tracking-[1px] mb-3">THOTH REVIEW</div>
        <h1 className="font-serif text-[24px] italic text-espresso leading-tight mb-2">
          Article: {slug}
        </h1>
        <div className="w-10 h-[2px] bg-brass mb-4" />
        <p className="text-stone text-sm">Article content and paywall will be rendered here.</p>
      </main>
    </div>
  );
}
