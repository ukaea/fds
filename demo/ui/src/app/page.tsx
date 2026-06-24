'use client';

import Link from 'next/link';
import useSWR from 'swr';
import { Database, Server, Activity, BookOpen } from 'lucide-react';
import { fetcher, API_BASE } from '@/lib/api';
import { Device } from '@/lib/types';

export default function Home() {
  const { data: devices, error: devicesError, isLoading: devicesLoading } = useSWR<Device[]>(`${API_BASE}/devices/`, fetcher);

  return (
    <div className="container mx-auto px-4 py-12">
      <div className="text-center mb-16 space-y-4 animate-fade-in">
        <h1 className="text-5xl font-extrabold tracking-tight text-foreground pb-2">
          Fusion Data Service
        </h1>
        <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
          Advanced access to experimental data and metadata for the fusion energy community.
        </p>
      </div>

      {/* Devices Section */}
      <div className="mb-12">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="bg-muted p-2 rounded-lg text-foreground">
              <Server className="w-6 h-6" />
            </div>
            <h2 className="text-2xl font-bold text-foreground">Experimental Devices</h2>
          </div>
          <Link
            href="/devices"
            className="text-sm text-foreground hover:text-foreground transition-colors"
          >
            View All →
          </Link>
        </div>

        {devicesLoading && (
          <div className="card p-8 text-center text-muted-foreground">
            Loading devices...
          </div>
        )}

        {devicesError && (
          <div className="card p-8 text-center text-destructive">
            Failed to load devices
          </div>
        )}

        {!devicesLoading && !devicesError && (!devices || devices.length === 0) && (
          <div className="card p-8 text-center">
            <div className="flex flex-col items-center gap-4 max-w-md mx-auto">
              <div className="bg-muted/50 p-4 rounded-full">
                <Server className="w-12 h-12 text-muted-foreground" />
              </div>
              <div>
                <h3 className="text-xl font-semibold text-foreground mb-2">No Devices Available</h3>
                <p className="text-muted-foreground">
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
                className="card p-6 group hover:bg-muted transition-colors"
              >
                <div className="flex items-start gap-3 mb-3">
                  <div className="bg-muted p-2 rounded-lg text-foreground group-hover:bg-accent transition-colors">
                    <Server className="w-5 h-5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-lg font-semibold text-foreground mb-1 truncate">{device.name}</h3>
                    <p className="text-sm text-muted-foreground line-clamp-2">
                      {device.description || 'No description available'}
                    </p>
                  </div>
                </div>
                <div className="text-xs text-foreground group-hover:text-foreground transition-colors font-medium">
                  View Shots →
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* Other Sections */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        <Link href="/sources" className="card group p-8 flex flex-col items-center text-center hover:bg-muted transition-colors">
          <div className="bg-muted p-4 rounded-full mb-6 group-hover:scale-110 transition-transform">
            <Activity className="w-8 h-8 text-foreground" />
          </div>
          <h2 className="text-2xl font-bold mb-3">Data Sources</h2>
          <p className="text-muted-foreground">Discover diagnostic instruments, simulation codes, and data producers.</p>
        </Link>
        <Link href="/datasets" className="card group p-8 flex flex-col items-center text-center hover:bg-muted transition-colors">
          <div className="bg-muted p-4 rounded-full mb-6 group-hover:scale-110 transition-transform">
            <Database className="w-8 h-8 text-muted-foreground" />
          </div>
          <h2 className="text-2xl font-bold mb-3">Datasets</h2>
          <p className="text-muted-foreground">Search and access scientific data directly via the global catalog.</p>
        </Link>
        <a href="http://localhost:4001" target="_blank" rel="noopener noreferrer" className="card group p-8 flex flex-col items-center text-center hover:bg-muted transition-colors">
          <div className="bg-muted p-4 rounded-full mb-6 group-hover:scale-110 transition-transform">
            <BookOpen className="w-8 h-8 text-foreground" />
          </div>
          <h2 className="text-2xl font-bold mb-3">Documentation</h2>
          <p className="text-muted-foreground">Concepts, data model, provenance, and demo walkthrough.</p>
        </a>
      </div>
    </div>
  );
}
