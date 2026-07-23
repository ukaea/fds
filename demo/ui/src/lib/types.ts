export interface Device {
  name: string;
  description?: string;
  // Add other fields as per backend response
}

export interface Shot {
  device_name: string;
  id: string; // Changed from shot_id: number to match backend ShotRead model
  timestamp?: string;
}

export interface Dataset {
  id?: number;
  name: string;
  device_name?: string;
  shot_id?: number;
  url?: string;
  created_at?: string;
  publisher?: string;
  level?: number;
  description?: string;
  license?: string;
  media_type?: string;
  access_level?: string;
  effective_access_level?: string;
  activity_id?: number;
  geometry_roles?: string[];
  geometry_references?: string[];
  calibration_roles?: string[];
  calibration_references?: string[];
  calibration_stage?: number | null;
  applies_to?: ReferenceCoverage;
  // Resolved reference versions, populated by ?include_geometry / ?include_calibration.
  geometry?: Dataset[];
  calibration?: Dataset[];
}

export interface ReferenceCoverage {
  shots?: string[];
  shot_ranges?: { from_shot: string; to_shot?: string | null }[];
  date_ranges?: { from_date: string; to_date?: string | null }[];
}

export interface Collection {
  id: number;
  name: string;
  title?: string;
  description?: string;
  device_name?: string | null;
  shot_id?: string | null;
  access_level?: string;
  effective_access_level?: string;
  activity_id?: number | null;
  datasets?: Dataset[];
  child_collections?: Collection[];
}

export interface Activity {
  id: number;
  source_id: number;
  activity_type?: string;
  source_version?: string;
  parameters?: Record<string, unknown>;
  started_at?: string;
  ended_at?: string;
}

export interface Source {
  id: number;
  name: string;
  description?: string;
  device_id?: number;
}
