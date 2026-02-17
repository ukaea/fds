'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { Database, Lock, Unlock, Download, Activity, ArrowLeft, ChevronRight } from 'lucide-react';
import { useSession, signIn } from "next-auth/react";

export default function DatasetPage() {
  const params = useParams();
  const { device, shot, dataset } = params;
  
  const { data: session, status } = useSession();
  const [accessValues, setAccessValues] = useState<{granted: boolean, token?: string}>({ granted: false });

  const handleRequestAccess = () => {
      if (status !== "authenticated") {
          signIn("keycloak");
          return;
      }

      // Simulate API call to get credentials (now gated by auth)
      setTimeout(() => {
          setAccessValues({ 
              granted: true, 
              token: "eyJh... (Real keycloak token would go here)" 
            });
      }, 800);
  };

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Breadcrumbs / Header */}
      <div className="mb-8">
         <Link href={`/devices/${device}/shots/${shot}`} className="inline-flex items-center text-sm text-slate-400 hover:text-white mb-4 transition-colors">
            <ArrowLeft className="w-4 h-4 mr-1" /> Back to Datasets
         </Link>
         <div className="flex items-center gap-2 text-sm text-slate-500 mb-2">
            <span>{device}</span> <ChevronRight className="w-3 h-3"/> 
            <span>Shot {shot}</span> <ChevronRight className="w-3 h-3"/>
            <span className="text-white font-medium">{dataset}</span>
         </div>
         <h1 className="text-3xl font-bold flex items-center gap-3">
            <Database className="text-primary" />
            {dataset}
         </h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Left Column: Metadata & Controls */}
        <div className="space-y-6">
            <div className="card p-6">
                <h3 className="text-lg font-bold mb-4 border-b border-slate-700 pb-2">Data Access</h3>
                
                {!accessValues.granted ? (
                    <div className="text-center py-6">
                        <Lock className="w-12 h-12 text-slate-600 mx-auto mb-3" />
                        <p className="text-slate-400 mb-4">You need temporary credentials to access this Icechunk store.</p>
                        <button 
                            onClick={handleRequestAccess}
                            className="bg-primary hover:bg-blue-600 text-white font-bold py-2 px-4 rounded w-full transition-colors flex items-center justify-center gap-2"
                        >
                            <Unlock className="w-4 h-4" /> 
                            {status === "authenticated" ? "Request Access" : "Sign In to Request Access"}
                        </button>
                    </div>
                ) : (
                    <div className="animate-fade-in">
                        <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 p-3 rounded mb-4 flex items-center gap-2">
                            <Unlock className="w-4 h-4" /> Access Granted
                        </div>
                        <div className="text-xs font-mono bg-slate-950 p-3 rounded mb-4 break-all opacity-70">
                            Token: {session?.accessToken || "Mock_S3_Token"}
                        </div>
                        <button className="w-full border border-slate-600 hover:bg-slate-800 text-white py-2 px-4 rounded flex items-center justify-center gap-2 transition-colors">
                            <Download className="w-4 h-4" /> Download Zarr Config
                        </button>
                    </div>
                )}
            </div>

            <div className="card p-6">
                <h3 className="text-lg font-bold mb-4 border-b border-slate-700 pb-2">Provenance</h3>
                <div className="space-y-4 text-sm">
                    <div className="flex justify-between items-center border-b border-slate-700/50 pb-2 last:border-0 hover:bg-slate-800/30 px-2 rounded transition-colors">
                        <span className="text-slate-500 font-medium">Source</span>
                        <span className="text-white font-mono bg-slate-800 px-2 py-0.5 rounded text-xs">ThomsonScattering</span>
                    </div>
                     <div className="flex justify-between items-center border-b border-slate-700/50 pb-2 last:border-0 hover:bg-slate-800/30 px-2 rounded transition-colors">
                        <span className="text-slate-500 font-medium">Processing</span>
                        <span className="text-white">Post-Shot Analysis</span>
                    </div>
                     <div className="flex justify-between items-center border-b border-slate-700/50 pb-2 last:border-0 hover:bg-slate-800/30 px-2 rounded transition-colors">
                        <span className="text-slate-500 font-medium">Owner</span>
                        <span className="text-white">Dr. A. Scientist</span>
                    </div>
                </div>
            </div>
        </div>

        {/* Right Column: Visualization */}
        <div className="lg:col-span-2">
            <div className="card h-[600px] flex flex-col relative overflow-hidden">
                <div className="absolute inset-0 bg-slate-950/50 z-0">
                    {/* Grid Background Pattern */}
                    <div className="h-full w-full" style={{ backgroundImage: 'radial-gradient(rgba(255,255,255,0.1) 1px, transparent 1px)', backgroundSize: '20px 20px' }}></div>
                </div>

                <div className="relative z-10 p-4 flex justify-between items-center border-b border-white/5 bg-slate-900/50 backdrop-blur">
                    <h3 className="font-mono text-sm text-blue-400 flex items-center gap-2">
                        <Activity className="w-4 h-4" /> VISUALIZER
                    </h3>
                    <div className="flex gap-2">
                        <span className="text-xs bg-slate-800 px-2 py-1 rounded text-slate-400">Time: 0.0 - 1.5s</span>
                        <span className="text-xs bg-slate-800 px-2 py-1 rounded text-slate-400">10k samples</span>
                    </div>
                </div>

                <div className="flex-1 flex items-center justify-center relative z-10">
                    {!accessValues.granted ? (
                        <div className="text-center">
                            <Activity className="w-16 h-16 text-slate-700 mx-auto mb-4 animate-pulse" />
                            <p className="text-slate-500">Waiting for data access...</p>
                        </div>
                    ) : (
                        <div className="w-full h-full p-4 animate-fade-in flex flex-col items-center justify-center">
                            {/* Placeholder Chart */}
                            <svg viewBox="0 0 400 200" className="w-full h-full text-primary drop-shadow-[0_0_10px_rgba(59,130,246,0.5)]">
                                <path d="M0,100 Q50,0 100,100 T200,100 T300,100 T400,100" fill="none" stroke="currentColor" strokeWidth="2" />
                                <path d="M0,100 Q50,50 100,150 T200,50 T300,150 T400,100" fill="none" stroke="#a855f7" strokeWidth="2" className="opacity-70" />
                            </svg>
                            <p className="text-xs text-slate-500 mt-4">
                                Rendering Te (eV) and Ne (m^-3) from chunk store...
                            </p>
                        </div>
                    )}
                </div>
            </div>
        </div>

      </div>
    </div>
  );
}
