export interface Device {
  name: string;
  title?: string;
  description?: string;
  // Add other fields as per backend response
}

export interface Shot {
  device_name: string;
  id: string; // Changed from shot_id: number to match backend ShotRead model
  timestamp?: string;
  shot_at?: string;
  // Wall-clock instant of the shot's relative t=0. Provider-declared; never used
  // to convert a feature's coordinates into another frame.
  t0_at?: string;
  description?: string;
  scientific_metadata?: ScientificProperty[];
  // Resolved annotation datasets, populated by ?include_annotations.
  annotations?: Dataset[];
}

// A 1D range that localises a property on one named axis of the data. Its
// start/end are coordinates in that axis's own frame, not wall-clock times.
export interface Extent {
  dimension: string;
  start: number;
  end?: number | null; // absent = a point (an instant or a single slice)
  unit?: string | null;
}

// An entry in scientific_metadata. With an extent it is a *feature*: the same
// property, localised on one axis. Without one it is a plain scalar property.
export interface ScientificProperty {
  name: string;
  value: unknown;
  unit?: string | null;
  description?: string | null;
  extent?: Extent | null;
}

export interface Dataset {
  id?: number;
  name: string;
  title?: string;
  device_name?: string;
  shot_id?: string;
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
  applies_to?: Coverage;
  scientific_metadata?: ScientificProperty[];
  // Set on a feature annotation dataset: the feature it localises. Its subject
  // fixes the frame — subject_dataset_id, or else the shot it belongs to.
  annotates?: string | null;
  subject_dataset_id?: number | null;
  // Resolved reference versions, populated by ?include_geometry / ?include_calibration.
  geometry?: Dataset[];
  calibration?: Dataset[];
  // Resolved annotations, populated by ?include_annotations. Frame-scoped: a
  // dataset resolves only the annotations whose subject it is.
  annotations?: Dataset[];
}

export interface Coverage {
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
  scientific_metadata?: ScientificProperty[];
  datasets?: Dataset[];
  child_collections?: Collection[];
}

export interface Activity {
  id: number;
  // Optional executor agent: a raw acquisition names no agent, just its instrument.
  source_id?: number | null;
  activity_type?: string;
  source_version?: string;
  parameters?: Record<string, unknown>;
  started_at?: string;
  ended_at?: string;
}

export type SourceKind = 'software' | 'instrument' | 'person' | 'organization';

export interface Source {
  id: number;
  name: string;
  description?: string;
  device_id?: number;
  // How the source projects into the PROV-O graph. null = unclassified.
  kind?: SourceKind | null;
}

// An agent associated with an Activity, with its role (prov:wasAssociatedWith).
export interface ActivityAgent {
  activity_id: number;
  source_id: number;
  role: string;
}

// A delegation edge on an Activity (prov:actedOnBehalfOf).
export interface ActivityDelegation {
  activity_id: number;
  subordinate_source_id: number;
  responsible_source_id: number;
}
