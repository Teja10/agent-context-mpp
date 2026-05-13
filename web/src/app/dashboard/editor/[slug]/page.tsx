"use client";

import { useParams } from "next/navigation";

export default function EditArticlePage() {
  const params = useParams<{ slug: string }>();

  return (
    <div className="flex flex-col min-h-screen">
      <nav className="flex justify-between items-center px-5 py-2.5 bg-espresso">
        <div className="flex items-center gap-4">
          <span className="font-serif text-sm text-camel tracking-wide">THOTH</span>
          <span className="text-umber text-xs">/ Editor</span>
        </div>
        <div className="flex items-center gap-2.5">
          <span className="text-stone text-[11px]">Auto-saved</span>
          <button className="border border-umber text-camel px-3.5 py-1.5 text-[11px] rounded-[3px]">
            Save Draft
          </button>
          <button className="bg-brass text-espresso px-3.5 py-1.5 text-[11px] rounded-[3px] font-medium">
            Publish
          </button>
        </div>
      </nav>

      <main className="flex-1 bg-sand">
        <div className="max-w-[640px] mx-auto px-6 py-8">
          <div className="text-center mb-1">
            <div className="text-umber text-[10px] uppercase tracking-[2px] mb-3">THOTH REVIEW</div>
            <h1 className="font-serif text-[28px] italic text-espresso leading-tight mb-1.5">
              {params.slug}
            </h1>
            <div className="text-stone text-[11px] mb-1">{params.slug}</div>
            <div className="w-10 h-[2px] bg-brass mx-auto mt-3 mb-5" />
          </div>

          <div className="flex justify-center gap-0 mb-6 border-b border-khaki">
            <button className="px-6 py-2.5 text-xs text-espresso border-b-2 border-brass tracking-wide font-medium">
              Write
            </button>
            <button className="px-6 py-2.5 text-xs text-umber tracking-wide">
              Agent Context
            </button>
            <button className="px-6 py-2.5 text-xs text-umber tracking-wide">
              Settings
            </button>
          </div>

          <p className="text-stone text-sm">Tiptap editor will be mounted here.</p>
        </div>
      </main>
    </div>
  );
}
