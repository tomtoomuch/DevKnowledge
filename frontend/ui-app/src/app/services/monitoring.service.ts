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

export interface MonitoringSnapshot {
  checked_at: string;
  services: MonitoredService[];
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
