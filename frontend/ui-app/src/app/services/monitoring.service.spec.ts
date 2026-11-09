import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { MonitoringService } from './monitoring.service';

describe('MonitoringService', () => {
  let service: MonitoringService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), MonitoringService],
    });
    service = TestBed.inject(MonitoringService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());

  it('queries only the Gateway using the local session', () => {
    service.getServices().subscribe(snapshot => {
      expect(snapshot.services[0].status).toBe('healthy');
    });
    const request = http.expectOne('/api/v1/monitoring/services');
    expect(request.request.method).toBe('GET');
    expect(request.request.withCredentials).toBe(true);
    request.flush({
      checked_at: '2026-11-10T00:00:00Z',
      services: [{ id: 'api-gateway', name: 'API Gateway',
        description: 'Point HTTP', status: 'healthy', detail: 'Accessible' }],
    });
  });

  it('returns GPU telemetry in the same Gateway response (no extra HTTP call)', () => {
    service.getServices().subscribe(snapshot => {
      expect(snapshot.gpu?.status).toBe('healthy');
      expect(snapshot.gpu?.devices[0].temperature_c).toBe(66);
    });
    http.expectOne('/api/v1/monitoring/services').flush({
      checked_at: '2026-11-10T00:00:00Z',
      services: [],
      gpu: { status: 'healthy', detail: 'GPU prêt', devices: [
        { index: 0, name: 'NVIDIA RTX Demo', utilization_pct: 51,
          memory_used_mib: 1024, memory_total_mib: 8192, temperature_c: 66 },
      ] },
    });
    http.expectNone('/metrics');
  });

  it('preserves a Gateway error for the monitoring UI', () => {
    service.getServices().subscribe({
      next: () => { throw new Error('Unexpected successful response'); },
      error: error => expect(error.status).toBe(502),
    });
    http.expectOne('/api/v1/monitoring/services').flush(
      { detail: 'KMS unavailable' }, { status: 502, statusText: 'Bad Gateway' },
    );
  });
});
