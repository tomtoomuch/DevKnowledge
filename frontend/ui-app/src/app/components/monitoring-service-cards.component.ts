import { ChangeDetectionStrategy, Component, Input } from '@angular/core';
import { MonitoredService, ServiceHealth } from '../services/monitoring.service';

@Component({
  selector: 'app-monitoring-service-cards',
  standalone: true,
  templateUrl: './monitoring-service-cards.component.html',
  styleUrl: './monitoring-service-cards.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MonitoringServiceCardsComponent {
  @Input({ required: true }) services: MonitoredService[] = [];

  statusLabel(status: ServiceHealth): string {
    switch (status) {
      case 'healthy': return 'Opérationnel';
      case 'degraded': return 'Dégradé';
      case 'unavailable': return 'Indisponible';
      default: return 'Inconnu';
    }
  }
}
