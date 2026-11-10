import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { finalize, timer } from 'rxjs';
import { GpuTelemetry, MonitoredService, MonitoringService, MonitoringSnapshot } from '../services/monitoring.service';
import { MonitoringServiceCardsComponent } from './monitoring-service-cards.component';
import { MonitoringGpuPanelComponent } from './monitoring-gpu-panel.component';

const GPU_UNKNOWN: GpuTelemetry = {
  status: 'unknown', detail: 'La disponibilité des métriques GPU n’a pas été vérifiée.', devices: [],
};

const UNCHECKED: MonitoredService[] = [
  { id: 'api-gateway', name: 'API Gateway', description: 'Point d’entrée HTTP unique',
    status: 'unknown', detail: 'Aucun résultat de contrôle disponible.' },
  { id: 'frontend', name: 'Frontend Angular', description: 'Interface web servie par Nginx',
    status: 'unknown', detail: 'Aucun résultat de contrôle disponible.' },
  { id: 'api-kms', name: 'Knowledge Service', description: 'API FastAPI et gestion des connaissances',
    status: 'unknown', detail: 'Aucun résultat de contrôle disponible.' },
  { id: 'mongodb', name: 'MongoDB', description: 'Base documentaire locale',
    status: 'unknown', detail: 'Aucun résultat de contrôle disponible.' },
  { id: 'collector', name: 'Collector', description: 'Collecte centralisée des services et du GPU',
    status: 'unknown', detail: 'Aucun résultat de contrôle disponible.' },
];

@Component({
  selector: 'app-monitoring',
  standalone: true,
  imports: [CommonModule, MonitoringServiceCardsComponent, MonitoringGpuPanelComponent],
  templateUrl: './monitoring.component.html',
  styleUrl: './monitoring.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MonitoringComponent implements OnInit {
  private readonly api = inject(MonitoringService);
  private readonly destroyRef = inject(DestroyRef);

  readonly snapshot = signal<MonitoringSnapshot | null>(null);
  readonly loading = signal(false);
  readonly error = signal('');
  readonly services = computed(() => this.snapshot()?.services ?? UNCHECKED);
  readonly gpu = computed(() => this.snapshot()?.gpu ?? GPU_UNKNOWN);
  readonly checkedAt = computed(() => this.snapshot()?.checked_at ?? null);
  readonly healthyCount = computed(() => this.services().filter(service => service.status === 'healthy').length);
  readonly degradedCount = computed(() => this.services().filter(service => service.status === 'degraded').length);
  readonly unavailableCount = computed(() => this.services().filter(service => service.status === 'unavailable').length);
  readonly unknownCount = computed(() => this.services().filter(service => service.status === 'unknown').length);
  readonly summary = computed(() => {
    if (this.unknownCount() === this.services().length) return 'Disponibilité non vérifiée';
    if (this.unavailableCount() > 0) return 'Certains services sont indisponibles';
    if (this.degradedCount() > 0 || this.unknownCount() > 0) return 'Disponibilité partielle ou dégradée';
    return 'Tous les services surveillés sont opérationnels';
  });

  ngOnInit(): void {
    // This component only exists while the Monitoring tab is selected.
    timer(0, 30_000).pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.refresh());
  }

  refresh(): void {
    if (this.loading()) return;
    this.loading.set(true);
    this.error.set('');
    this.api.getServices().pipe(
      takeUntilDestroyed(this.destroyRef),
      finalize(() => this.loading.set(false)),
    ).subscribe({
      next: snapshot => this.snapshot.set(snapshot),
      error: (error: unknown) => {
        // An HTTP 502/504 proves the Gateway replied, but says nothing about MongoDB.
        if (error instanceof HttpErrorResponse && (error.status === 502 || error.status === 504)) {
          this.snapshot.set({
            checked_at: new Date().toISOString(),
            services: [
              { ...UNCHECKED[0], status: 'healthy', detail: 'La Gateway a répondu à la requête.' },
              { ...UNCHECKED[1], status: 'unknown' },
              { ...UNCHECKED[2], status: 'unavailable', detail: 'Le KMS ne répond pas à la Gateway.' },
              UNCHECKED[3],
              UNCHECKED[4],
            ],
          });
          this.error.set('Le Knowledge Service est inaccessible ou n’a pas répondu à temps.');
        } else {
          // Do not continue displaying stale green statuses after a failed refresh.
          this.snapshot.set(null);
          if (error instanceof HttpErrorResponse && error.status === 401) {
            this.error.set('Session expirée. Reconnecte-toi pour consulter le monitoring.');
          } else if (error instanceof HttpErrorResponse && error.status === 403) {
            this.error.set('Droits de consultation insuffisants.');
          } else {
            this.error.set('Impossible de vérifier la santé des services via la Gateway.');
          }
        }
      },
    });
  }
}
