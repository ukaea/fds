'use client';

import useSWR from 'swr';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { fetcher, API_BASE } from '@/lib/api';
import { Shot } from '@/lib/types';
import { useDeviceLabel } from '@/lib/use-device-label';
import { Calendar, Database, ChevronRight } from 'lucide-react';
import { ClientDate } from '@/components/client-date';

export default function ShotListPage() {
  const params = useParams();
  const deviceName = params.device as string;
  const deviceLabel = useDeviceLabel(deviceName);

  const { data: shots, error, isLoading } = useSWR<Shot[]>(
    deviceName ? `${API_BASE}/devices/${deviceName}/shots/` : null,
    fetcher
  );

  if (error) return <div className="container py-12 text-destructive">Failed to load shots</div>;
  if (isLoading) return <div className="container py-12 text-muted-foreground">Loading shots for {deviceLabel}...</div>;

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-8">
        <div className="flex items-center text-sm text-muted-foreground mb-2">
            <Link href="/devices" className="hover:text-primary transition-colors">Devices</Link>
            <ChevronRight className="w-4 h-4 mx-2" />
            <span className="text-foreground font-medium">{deviceLabel}</span>
        </div>
        <h1 className="text-3xl font-bold text-foreground">Shots</h1>
        <p className="text-muted-foreground">History of experiments on {deviceLabel}.</p>
      </div>

      <div className="space-y-4">
        {shots?.map((shot) => (
          <Link
            key={shot.id}
            href={`/devices/${deviceName}/shots/${shot.id}`}
            className="block card p-6 hover:bg-muted transition-colors group"
          >
            <div className="flex items-center justify-between">
              <div>
                <div className="flex items-center gap-3 mb-1">
                    <span className="bg-muted text-foreground px-3 py-1 rounded-full text-xs font-mono font-bold">
                        #{shot.id}
                    </span>
                    <span className="text-foreground font-medium">
                        Standard Plasma Experiment
                    </span>
                </div>
                <div className="flex items-center gap-4 text-sm text-muted-foreground mt-2">
                    <div className="flex items-center gap-1">
                        <Calendar className="w-4 h-4" />
                        <ClientDate timestamp={shot.timestamp} />
                    </div>
                    <div className="flex items-center gap-1">
                        <Database className="w-4 h-4" />
                        Metadata Available
                    </div>
                </div>
              </div>

              <ChevronRight className="text-muted-foreground group-hover:text-primary group-hover:translate-x-1 transition-all" />
            </div>
          </Link>
        ))}

        {!shots || shots.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground bg-muted/20 rounded-lg border border-dashed border-border">
                No shots found for this device.
            </div>
        ) : null}
      </div>
    </div>
  );
}
