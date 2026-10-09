export interface Device {
  name: string;
  title?: string;
  description?: string;
  // Add other fields as per backend response
}

export interface Shot {
  device_name: string;
  id: string; // Changed from shot_id: number to match backend ShotRead model
  shot_at?: string;
  // Wall-clock instant of the shot's relative t=0. Provider-declared; never used
  // to convert an annotation's coordinates into another frame.
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

// An entry in scientific_metadata. With an extent it is an *annotation*: the same
// property, localised on one axis. Without one it is a plain scalar property.
export interface ScientificProperty {
  name: string;
  value: unknown;
  unit?: string | null;
  description?: string | null;
  extent?: Extent | null;
  // What the value is, as the producer declared it. Absent means FDS infers it.
  kind?: MetadataKind | null;
}

// What a scientific property's value is, as the producer declared it or as FDS
// inferred it. It says what the value *is*, not how to draw it; the control
// follows from the kind together with how many distinct values there are.
export type MetadataKind = 'term' | 'quantity' | 'text';

// One scientific-metadata name in scope. `values` is absent when there are too
// many to enumerate; `distinct` is always present, so absence is never
// ambiguous. `dimension` is set when the property carries an extent, which
// makes it an annotation: a claim about a region of the data rather than the whole
// record. `text` names never appear, because prose describes a record rather than
// classifying it.
export interface AvailableProperty {
  name: string;
  records: number;
  distinct: number;
  kind: MetadataKind;
  unit?: string | null;
  description?: string | null;
  dimension?: string | null;
  min?: number | null;
  max?: number | null;
  values?: string[];
}

// `total` counts the records in scope after any filter, which is the count a
// listing page cannot give: the page is capped, the scope is not.
export interface AvailableProperties {
  total: number;
  properties: AvailableProperty[];
}

// A page of one name's values, for a vocabulary too large to enumerate inline.
export interface PropertyValue {
  value: string;
  records: number;
}

export interface PropertyValues {
  name: string;
  distinct: number;
  values: PropertyValue[];
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
  creator?: string | null;
  version?: string | null;
  // Comma-separated, as stored.
  keywords?: string | null;
  temporal_start?: string | null;
  temporal_end?: string | null;
  quality_flag?: string | null;
  // Registered elsewhere (a DOI, say), as an absolute URI or compact form.
  persistent_identifier?: string | null;
  // When the data was formally published, as a date. Not created_at, which is
  // when FDS listed it.
  issued?: string | null;
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
  // Set on an annotation dataset: the property it localises. Its subject
  // fixes the frame — subject_dataset_id, or else the shot it belongs to.
  annotates?: string | null;
  subject_dataset_id?: number | null;
  // Resolved reference versions, populated by ?include_geometry / ?include_calibration.
  geometry?: Dataset[];
  calibration?: Dataset[];
  // Resolved annotations, populated by ?include_annotations. Frame-scoped: a
  // dataset resolves only the annotations whose subject it is.
  annotations?: Dataset[];
  // Every copy of the data, the default among them. url and media_type above
  // are the default's, inlined.
  distributions?: Distribution[] | null;
}

// One copy of a dataset's data. Copies carry the same information: the same
// data in another format, another store or another schema.
export interface Distribution {
  id: number;
  url: string;
  // The group inside the file at url that holds this dataset, when the file
  // holds several datasets.
  group?: string | null;
  // URI of the schema this copy follows, such as an IMAS Data Dictionary
  // version. Values can differ between copies in different schemas.
  conforms_to?: string | null;
  endpoint_url?: string | null;
  region?: string | null;
  media_type?: string | null;
  format?: string | null;
  default_distribution: boolean;
  storage_options_type?: 'fsspec_s3' | 'icechunk_s3' | null;
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
  root_url?: string | null;
  created_at?: string;
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
