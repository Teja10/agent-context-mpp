export default function LoginPage() {
  return (
    <div className="min-h-screen flex flex-col" style={{ background: "linear-gradient(160deg, #f5f0e8 0%, #e8dcc8 40%, #d4c5a9 100%)" }}>
      <nav className="flex justify-between items-center px-8 py-4">
        <span className="font-serif text-lg text-espresso tracking-wide">THOTH</span>
        <span className="text-umber text-sm cursor-pointer">Explore articles</span>
      </nav>

      <div className="flex-1 flex items-start justify-center pt-[12vh]">
        <div className="bg-parchment border border-camel rounded-[10px] p-10 w-[370px]"
          style={{ boxShadow: "0 1px 0 #c9b896, 0 2px 0 #c9b896, 0 4px 0 rgba(139, 115, 85, 0.15), 0 8px 24px rgba(44, 36, 22, 0.12), 0 16px 48px rgba(44, 36, 22, 0.08)" }}>
          <div className="text-center mb-7">
            <div className="text-umber text-[10px] uppercase tracking-[3px] mb-2.5">Welcome to</div>
            <div className="font-serif text-[26px] italic text-espresso mb-2">Thoth</div>
            <div className="w-[30px] h-[2px] bg-brass mx-auto mb-2.5" />
            <p className="text-umber text-[13px]">Connect a wallet to read, write, and publish.</p>
          </div>
          <p className="text-stone text-xs text-center">Privy login will be integrated here.</p>
        </div>
      </div>
    </div>
  );
}
