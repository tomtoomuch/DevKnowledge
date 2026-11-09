import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export type ServiceHealth = 'healthy' | 'degraded' | 'unavailable' | 'unknown';

export interface MonitoredService {
  id: string;
  name: string;
  description: string;
  status: ServiceHealth;
  detail: string;
}

export interface GpuDevice {
  index: number;
  name: string;
  utilization_pct: number | null;
  memory_used_mib: number | null;
  memory_total_mib: number | null;
  temperature_c: number | null;
}

export type GpuHealth = 'healthy' | 'unavailable' | 'disabled' | 'unknown';

export interface GpuTelemetry {
  status: GpuHealth;
  detail: string;
  devices: GpuDevice[];
}

export interface MonitoringSnapshot {
  checked_at: string;
  services: MonitoredService[];
  gpu?: GpuTelemetry;
}

@Injectable({ providedIn: 'root' })
export class MonitoringService {
  private readonly http = inject(HttpClient);

  // The browser communicates only with the Gateway; never with KMS or MongoDB.
  getServices(): Observable<MonitoringSnapshot> {
    return this.http.get<MonitoringSnapshot>('/api/v1/monitoring/services', {
      withCredentials: true,
    });
  }
}
