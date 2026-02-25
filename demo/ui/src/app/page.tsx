'use client';

import Link from 'next/link';
import useSWR from 'swr';
import { Database, Server, Activity, Plus } from 'lucide-react';
import { fetcher, API_BASE } from '@/lib/api';
import { Device } from '@/lib/types';

export default function Home() {
  const { data: devices, error: devicesError, isLoading: devicesLoading } = useSWR<Device[]>(`${API_BASE}/devices/`, fetcher);

  return (
    <div className="container mx-auto px-4 py-12">
      <div className="text-center mb-16 space-y-4 animate-fade-in">
        <h1 className="text-5xl font-extrabold tracking-tight text-white pb-2">
          UKAEA Data
        </h1>
        <p className="text-xl text-slate-400 max-w-2xl mx-auto">
          Advanced access to experimental data and metadata for the fusion energy community.
        </p>
      </div>

      {/* Devices Section */}
      <div className="mb-12">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="bg-ukaea-secondary-blue/20 p-2 rounded-lg text-ukaea-secondary-blue">
              <Server className="w-6 h-6" />
            </div>
            <h2 className="text-2xl font-bold text-white">Experimental Devices</h2>
          </div>
          <Link
            href="/devices"
            className="text-sm text-ukaea-secondary-blue hover:text-white transition-colors"
          >
            View All →
          </Link>
        </div>

        {devicesLoading && (
          <div className="card p-8 text-center text-slate-400">
            Loading devices...
          </div>
        )}

        {devicesError && (
          <div className="card p-8 text-center text-ukaea-secondary-red">
            Failed to load devices
          </div>
        )}

        {!devicesLoading && !devicesError && (!devices || devices.length === 0) && (
          <div className="card p-8 text-center">
            <div className="flex flex-col items-center gap-4 max-w-md mx-auto">
              <div className="bg-slate-700/50 p-4 rounded-full">
                <Server className="w-12 h-12 text-slate-400" />
              </div>
              <div>
                <h3 className="text-xl font-semibold text-white mb-2">No Devices Available</h3>
                <p className="text-slate-400">
                  There are no experimental devices registered in the system yet, or you don't have permission to view them.
                </p>
              </div>
            </div>
          </div>
        )}

        {!devicesLoading && !devicesError && devices && devices.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {devices.map((device) => (
              <Link
                key={device.name}
                href={`/devices/${device.name}/shots`}
                className="card p-6 group hover:bg-slate-800/50 transition-colors"
              >
                <div className="flex items-start gap-3 mb-3">
                  <div className="bg-ukaea-secondary-blue/20 p-2 rounded-lg text-ukaea-secondary-blue group-hover:bg-ukaea-secondary-blue/30 transition-colors">
                    <Server className="w-5 h-5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-lg font-semibold text-white mb-1 truncate">{device.name}</h3>
                    <p className="text-sm text-slate-400 line-clamp-2">
                      {device.description || 'No description available'}
                    </p>
                  </div>
                </div>
                <div className="text-xs text-ukaea-secondary-blue group-hover:text-white transition-colors font-medium">
                  View Shots →
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* Other Sections */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <Link href="/sources" className="card group p-8 flex flex-col items-center text-center hover:bg-slate-800/50 transition-colors">
          <div className="bg-ukaea-secondary-yellow/10 p-4 rounded-full mb-6 group-hover:scale-110 transition-transform">
            <Activity className="w-8 h-8 text-ukaea-secondary-yellow" />
          </div>
          <h2 className="text-2xl font-bold mb-3">Data Sources</h2>
          <p className="text-slate-400">Discover diagnostic instruments, simulation codes, and data producers.</p>
        </Link>
        <Link href="/datasets" className="card group p-8 flex flex-col items-center text-center hover:bg-slate-800/50 transition-colors">
            <div className="bg-ukaea-secondary-green/10 p-4 rounded-full mb-6 group-hover:scale-110 transition-transform">
            <Database className="w-8 h-8 text-ukaea-secondary-green" />
            </div>
          <h2 className="text-2xl font-bold mb-3">Datasets</h2>
          <p className="text-slate-400">Search and access scientific data directly via the global catalog.</p>
        </Link>
      </div>
    </div>
  );
}
