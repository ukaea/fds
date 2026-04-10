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
