import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';
import { MonitoringGpuPanelComponent } from './monitoring-gpu-panel.component';
import { MonitoringServiceCardsComponent } from './monitoring-service-cards.component';

describe('Monitoring presentation components', () => {
  it('displays service states from the supplied monitoring API response', async () => {
    await TestBed.configureTestingModule({ imports: [MonitoringServiceCardsComponent] }).compileComponents();
    const fixture = TestBed.createComponent(MonitoringServiceCardsComponent);
    fixture.componentRef.setInput('services', [
      { id: 'supervisor', name: 'Supervisor', description: 'Collecte',
        status: 'healthy', detail: 'Disponible' },
      { id: 'mongodb', name: 'MongoDB', description: 'Stockage',
        status: 'unavailable', detail: 'Pas de ping' },
    ]);
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Supervisor');
    expect(text).toContain('Opérationnel');
    expect(text).toContain('Indisponible');
    expect(text).toContain('Pas de ping');
  });

  it('presents GPU values and preserves disabled/unknown states', async () => {
    await TestBed.configureTestingModule({ imports: [MonitoringGpuPanelComponent] }).compileComponents();
    const fixture = TestBed.createComponent(MonitoringGpuPanelComponent);
    fixture.componentRef.setInput('gpu', {
      status: 'healthy', detail: 'Mesures GPU disponibles.', devices: [
        { index: 0, name: 'NVIDIA RTX 3070', utilization_pct: 34,
          memory_used_mib: 2048, memory_total_mib: 8192, temperature_c: 54 },
      ],
    });
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('RTX 3070');
    expect(text).toContain('34 %');
    expect(text).toContain('54 °C');

    fixture.componentRef.setInput('gpu', {
      status: 'disabled', detail: 'Collecte désactivée', devices: [],
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Non configuré');
    expect(fixture.nativeElement.textContent).toContain('Collecte désactivée');
  });
});
