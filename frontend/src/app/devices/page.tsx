'use client';

import { useState } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { Server, Activity, ArrowRight, Plus, X } from 'lucide-react';
import { fetcher, API_BASE } from '@/lib/api';
import { Device } from '@/lib/types';

export default function DevicesPage() {
  const { data: devices, error, isLoading, mutate } = useSWR<Device[]>(`${API_BASE}/devices/`, fetcher);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({ name: '', description: '' });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');
    setIsSubmitting(true);

    try {
      const response = await fetch(`${API_BASE}/devices/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to create device');
      }

      // Reset form and refresh data
      setFormData({ name: '', description: '' });
      setShowForm(false);
      mutate(); // Refresh the device list
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (error) return <div className="p-8 text-red-400">Failed to load devices</div>;
  if (isLoading) return <div className="container py-12 text-slate-400">Loading devices...</div>;

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white mb-2">Experimental Devices</h1>
          <p className="text-slate-400">Select a device to browse shots and datasets.</p>
        </div>
        {devices && devices.length > 0 && (
          <button
            onClick={() => setShowForm(!showForm)}
            className="flex items-center gap-2 px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-lg transition-colors"
          >
            {showForm ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
            {showForm ? 'Cancel' : 'Add Device'}
          </button>
        )}
      </div>

      {/* Registration Form */}
      {showForm && (
        <div className="card p-6 mb-8">
          <h2 className="text-xl font-semibold text-white mb-4">Register New Device</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="name" className="block text-sm font-medium text-slate-300 mb-2">
                Device Name *
              </label>
              <input
                type="text"
                id="name"
                required
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="e.g., MAST, JET, ITER"
                className="w-full px-4 py-2 bg-slate-900/50 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-colors"
              />
            </div>
            <div>
              <label htmlFor="description" className="block text-sm font-medium text-slate-300 mb-2">
                Description
              </label>
              <textarea
                id="description"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="Brief description of the device..."
                rows={3}
                className="w-full px-4 py-2 bg-slate-900/50 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-colors resize-none"
              />
            </div>
            {formError && (
              <div className="p-3 bg-red-500/10 border border-red-500/50 rounded-lg text-red-400 text-sm">
                {formError}
              </div>
            )}
            <div className="flex gap-3">
              <button
                type="submit"
                disabled={isSubmitting}
                className="px-6 py-2 bg-blue-500 hover:bg-blue-600 disabled:bg-slate-700 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
              >
                {isSubmitting ? 'Creating...' : 'Create Device'}
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowForm(false);
                  setFormData({ name: '', description: '' });
                  setFormError('');
                }}
                className="px-6 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {devices?.map((device) => (
          <Link 
            key={device.name} 
            href={`/devices/${device.name}/shots`}
            className="card group overflow-hidden block"
          >
            <div className="p-6 relative">
              <div className="absolute top-0 right-0 p-6 opacity-10 group-hover:opacity-20 transition-opacity">
                <Server className="w-24 h-24" />
              </div>
              
              <div className="flex items-center gap-3 mb-4">
                <div className="bg-blue-500/20 p-2 rounded-lg text-blue-400">
                  <Activity className="w-5 h-5" />
                </div>
                <h2 className="text-xl font-bold">{device.name}</h2>
              </div>
              
              <p className="text-slate-400 mb-6 line-clamp-2">
                {device.description || "No description available for this device."}
              </p>

              <div className="flex items-center text-sm font-medium text-primary group-hover:text-blue-300 transition-colors">
                Browse Shots <ArrowRight className="w-4 h-4 ml-2 group-hover:translate-x-1 transition-transform" />
              </div>
            </div>
            <div className="h-1 w-full bg-gradient-to-r from-blue-500 to-purple-500 transform scale-x-0 group-hover:scale-x-100 transition-transform origin-left" />
          </Link>
        ))}

        {!devices || devices.length === 0 && (
           <div className="col-span-full">
             {/* Empty state - only show when form is not active */}
             {!showForm && (
               <div className="text-center py-16 bg-slate-800/30 rounded-lg border border-dashed border-slate-700">
                 <div className="flex flex-col items-center gap-4 max-w-md mx-auto">
                   <div className="bg-slate-700/50 p-4 rounded-full">
                     <Server className="w-12 h-12 text-slate-400" />
                   </div>
                   <div>
                     <h3 className="text-xl font-semibold text-white mb-2">No Devices Registered Yet</h3>
                     <p className="text-slate-400 mb-6">
                       Get started by registering your first experimental device. Devices represent fusion reactors or tokamaks that generate data.
                     </p>
                   </div>
                   <button
                     onClick={() => setShowForm(true)}
                     className="flex items-center gap-2 px-6 py-3 bg-blue-500 hover:bg-blue-600 text-white rounded-lg transition-colors font-medium"
                   >
                     <Plus className="w-5 h-5" />
                     Register First Device
                   </button>
                 </div>
               </div>
             )}
           </div>
        )}
      </div>
    </div>
  );
}
