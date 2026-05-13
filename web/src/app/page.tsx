export default function Home() {
  return (
    <div className="flex flex-col min-h-screen">
      <nav className="flex justify-between items-center px-8 py-4 border-b border-khaki">
        <span className="font-serif text-lg tracking-wide">THOTH</span>
        <button className="bg-espresso text-ivory px-5 py-2 text-sm rounded-[3px]">
          Connect Wallet
        </button>
      </nav>

      <main className="flex-1 flex flex-col items-center pt-12 pb-8">
        <div className="text-center max-w-xl mb-8">
          <h1 className="font-serif text-[28px] italic text-espresso mb-3">
            Knowledge, valued.
          </h1>
          <p className="text-umber text-sm leading-relaxed">
            A marketplace for ideas — where publishers are paid for insight and
            readers invest in understanding.
          </p>
        </div>

        <div className="w-full max-w-[720px] px-6">
          <div className="text-umber text-[11px] uppercase tracking-[2px] pb-2 mb-5 border-b border-khaki">
            Latest Articles
          </div>
          <p className="text-stone text-sm">No articles yet.</p>
        </div>
      </main>
    </div>
  );
}
