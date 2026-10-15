import { Search } from 'lucide-react';

/** A search field with its magnifier, as the shot list and the simulation browser use it. */
export function SearchBox({
  value,
  onChange,
  label,
  placeholder = label,
  inputMode,
}: {
  value: string;
  onChange: (value: string) => void;
  label: string;
  placeholder?: string;
  inputMode?: 'numeric' | 'text';
}) {
  return (
    <div className="relative w-full">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
      <input
        type="search"
        inputMode={inputMode}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={label}
        className="w-full pl-9 pr-3 py-2 text-sm bg-card border border-border rounded-lg text-foreground placeholder-muted-foreground focus:outline-hidden focus:border-foreground/40"
      />
    </div>
  );
}
