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
  name: string;
  device_name?: string;
  shot_id?: number;
  data_url?: string;
  created_at?: string;
}

export interface Source {
  id: number;
  name: string;
  description?: string;
  device_id?: number;
}
