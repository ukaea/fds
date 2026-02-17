import { Activity } from 'lucide-react';

export default function SourcesPage() {
  return (
    <div className="container mx-auto px-4 py-12 text-center">
      <div className="inline-block p-4 rounded-full bg-purple-500/10 mb-6 animate-pulse">
        <Activity className="w-12 h-12 text-purple-400" />
      </div>
      <h1 className="text-3xl font-bold text-white mb-4">Data Sources Catalog</h1>
      <p className="text-slate-400 max-w-md mx-auto mb-8">
        This registry will list diagnostic instruments, simulation codes, and data producers available in the FDS ecosystem.
      </p>
      <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-8 max-w-2xl mx-auto">
        <p className="text-sm text-slate-500 font-mono">
            Work in Progress
        </p>
      </div>
    </div>
  );
}
