import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, Input } from '@angular/core';
import { GpuDevice, GpuTelemetry } from '../services/monitoring.service';

@Component({
  selector: 'app-monitoring-gpu-panel',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './monitoring-gpu-panel.component.html',
  styleUrl: './monitoring-gpu-panel.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MonitoringGpuPanelComponent {
  @Input({ required: true }) gpu!: GpuTelemetry;

  statusLabel(status: GpuTelemetry['status']): string {
    switch (status) {
      case 'healthy': return 'Mesures disponibles';
      case 'unavailable': return 'Collecteur indisponible';
      case 'disabled': return 'Non configuré';
      default: return 'Non vérifié';
    }
  }

  metric(value: number | null): string {
    return value === null || !Number.isFinite(value) ? 'Non disponible' : String(value);
  }

  memoryRatio(device: GpuDevice): number | null {
    if (device.memory_used_mib === null || device.memory_total_mib === null ||
        !Number.isFinite(device.memory_used_mib) || !Number.isFinite(device.memory_total_mib) ||
        device.memory_total_mib <= 0) return null;
    return Math.min(100, Math.max(0, Math.round(device.memory_used_mib * 100 / device.memory_total_mib)));
  }
}
