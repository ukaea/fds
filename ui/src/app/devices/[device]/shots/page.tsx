'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { ChevronRight } from 'lucide-react';
import { useDeviceLabel } from '@/lib/use-device-label';
import { ShotList } from '@/components/shot-list';

export default function ShotListPage() {
  const params = useParams();
  const deviceName = params.device as string;
  const deviceLabel = useDeviceLabel(deviceName);

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

      <ShotList deviceName={deviceName} />
    </div>
  );
}
