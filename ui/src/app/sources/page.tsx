'use client';

import { useState } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { Activity, ChevronRight, Cpu, Gauge, Search, Users } from 'lucide-react';
import { fetcher, API_BASE } from '@/lib/api';
import { Source } from '@/lib/types';

// Sources grouped by what they are, since that is what a reader is looking for:
// the codes that produced simulations and analyses, or the instruments that
// measured. Whether a source is tied to a device is shown on its card.
const GROUPS: { key: Group; title: string; icon: typeof Cpu; empty: string }[] = [
  { key: 'software', title: 'Codes', icon: Cpu, empty: 'No codes match.' },
  { key: 'instrument', title: 'Instruments', icon: Gauge, empty: 'No instruments match.' },
  { key: 'agents', title: 'People and organisations', icon: Users, empty: 'None match.' },
  { key: 'unclassified', title: 'Unclassified', icon: Activity, empty: 'None match.' },
];

type Group = 'software' | 'instrument' | 'agents' | 'unclassified';

function groupOf(source: Source): Group {
  if (source.kind === 'software' || source.kind === 'instrument') return source.kind;
  if (source.kind === 'person' || source.kind === 'organization') return 'agents';
  return 'unclassified';
}

export default function SourcesPage() {
  const { data: sources, error: sourcesError, isLoading: sourcesLoading } = useSWR<Source[]>(`${API_BASE}/sources/`, fetcher);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<'all' | Group>('all');

  const query = searchQuery.toLowerCase();
  const filteredSources = sources?.filter(
    (source) =>
      !query ||
      source.name.toLowerCase().includes(query) ||
      source.description?.toLowerCase().includes(query)
  );
  const present = GROUPS.filter((group) => sources?.some((s) => groupOf(s) === group.key));

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-foreground mb-2">Data Sources</h1>
          <p className="text-muted-foreground">
            The codes, instruments and people that produce data. A code&apos;s page lists the runs it
            carried out and the data they generated.
          </p>
        </div>
      </div>

      {/* Search and Filter Bar */}
      <div className="flex flex-col md:flex-row gap-4 mb-8">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search sources by name or description..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-card/50 border border-border rounded-lg text-foreground placeholder-muted-foreground focus:outline-hidden focus:border-border transition-colors"
          />
        </div>
        {present.length > 1 && (
          <div className="flex gap-2 flex-wrap">
            {[{ key: 'all' as const, title: 'All' }, ...present].map((option) => (
              <button
                key={option.key}
                onClick={() => setFilterType(option.key)}
                aria-pressed={filterType === option.key}
                className={`px-4 py-2 rounded-lg transition-colors ${
                  filterType === option.key
                    ? 'bg-foreground text-background'
                    : 'bg-muted text-muted-foreground hover:text-foreground'
                }`}
              >
                {option.title}
              </button>
            ))}
          </div>
        )}
      </div>

      {sourcesLoading && (
        <div className="card p-8 text-center text-muted-foreground">
          Loading sources...
        </div>
      )}

      {sourcesError && (
        <div className="card p-8 text-center text-destructive">
          Failed to load sources
        </div>
      )}

      {!sourcesLoading && !sourcesError && (!filteredSources || filteredSources.length === 0) && (
        <div className="text-center py-16 bg-muted/30 rounded-lg border border-dashed border-border">
          <div className="flex flex-col items-center gap-4 max-w-md mx-auto">
            <div className="bg-muted/50 p-4 rounded-full">
              <Activity className="w-12 h-12 text-muted-foreground" />
            </div>
            <div>
              <h3 className="text-xl font-semibold text-foreground mb-2">
                {searchQuery ? 'No Matching Sources' : 'No Sources Registered Yet'}
              </h3>
              <p className="text-muted-foreground">
                {searchQuery
                  ? 'Try adjusting your search or filter criteria.'
                  : 'Sources represent diagnostic instruments and simulation codes that produce data. They will appear here once registered via the API.'}
              </p>
            </div>
          </div>
        </div>
      )}

      {!sourcesLoading && !sourcesError && !!filteredSources?.length && (
        <div className="space-y-8">
          {present
            .filter((group) => filterType === 'all' || filterType === group.key)
            .map((group) => {
              const members = filteredSources.filter((s) => groupOf(s) === group.key);
              const Icon = group.icon;
              return (
                <div key={group.key}>
                  <div className="flex items-center gap-3 mb-4">
                    <div className="bg-muted p-2 rounded-lg text-foreground">
                      <Icon className="w-5 h-5" />
                    </div>
                    <h2 className="text-xl font-semibold text-foreground">{group.title}</h2>
                    <span className="text-sm text-muted-foreground">({members.length})</span>
                  </div>
                  {members.length > 0 ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                      {members.map((source) => (
                        <SourceCard key={source.id} source={source} />
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">{group.empty}</p>
                  )}
                </div>
              );
            })}
        </div>
      )}
    </div>
  );
}

function SourceCard({ source }: { source: Source }) {
  return (
    <Link
      href={`/sources/${source.id}`}
      className="card p-6 group hover:bg-muted transition-colors block"
    >
      <div className="flex items-start gap-3 mb-3">
        <div className="p-2 rounded-lg bg-muted text-foreground">
          <Activity className="w-5 h-5" />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-lg font-semibold text-foreground mb-1 truncate group-hover:text-primary transition-colors">
            {source.name}
          </h3>
          <p className="text-sm text-muted-foreground line-clamp-2">
            {source.description || 'No description available'}
          </p>
        </div>
      </div>

      <div className="flex items-center justify-between mt-4">
        <span className="text-xs px-2.5 py-1 rounded-full border font-medium text-foreground bg-muted border-border">
          {source.device_name ?? 'Global'}
        </span>
        <div className="flex items-center text-xs text-muted-foreground group-hover:text-primary transition-colors font-medium">
          View Details <ChevronRight className="w-3.5 h-3.5 ml-1 group-hover:translate-x-0.5 transition-transform" />
        </div>
      </div>

      {/* Bottom accent bar */}
      <div className="h-0.5 w-full mt-4 rounded-full transform scale-x-0 group-hover:scale-x-100 transition-transform origin-left bg-gradient-to-r from-muted to-muted" />
    </Link>
  );
}
