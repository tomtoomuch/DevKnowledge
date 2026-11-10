import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
  ChangeDetectionStrategy, Component, DestroyRef, EventEmitter, Input,
  OnChanges, Output, inject, signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize } from 'rxjs';
import { KnowledgeRelation, RelationType } from '../models/relations.model';
import { RelationsApiService } from '../services/relations-api.service';

const UUID_PATTERN = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;
const PAGE_SIZE = 20;

@Component({
  selector: 'app-knowledge-relations',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './knowledge-relations.component.html',
  styleUrl: './knowledge-relations.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class KnowledgeRelationsComponent implements OnChanges {
  private readonly api = inject(RelationsApiService);
  private readonly destroyRef = inject(DestroyRef);
  private generation = 0;

  @Input({ required: true }) knowledgeId = '';
  @Input() canCreate = false;
  @Input() canUpdate = false;
  @Input() canDelete = false;
  @Output() openKnowledge = new EventEmitter<string>();

  readonly types = signal<RelationType[]>([]);
  readonly items = signal<KnowledgeRelation[]>([]);
  readonly total = signal(0);
  readonly page = signal(0);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly notice = signal('');
  readonly editing = signal<string | null>(null);
  readonly editNotes = new FormControl('', {
    nonNullable: true, validators: [Validators.maxLength(4000)],
  });
  readonly createForm = new FormGroup({
    target: new FormControl('', {
      nonNullable: true, validators: [Validators.required, Validators.pattern(UUID_PATTERN)],
    }),
    typeId: new FormControl('', {
      nonNullable: true, validators: [Validators.required],
    }),
    notes: new FormControl('', {
      nonNullable: true, validators: [Validators.maxLength(4000)],
    }),
    reverse: new FormControl(false, { nonNullable: true }),
  });

  ngOnChanges(): void {
    ++this.generation;
    this.page.set(0);
    this.items.set([]);
    this.total.set(0);
    this.error.set('');
    this.notice.set('');
    this.editing.set(null);
    this.createForm.reset({ target: '', typeId: '', notes: '', reverse: false });
    if (!this.knowledgeId) return;
    this.loadTypes();
    this.reload();
  }

  private loadTypes(): void {
    const generation = this.generation;
    this.api.types().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: types => {
        if (generation !== this.generation) return;
        this.types.set(types);
        if (!this.createForm.controls.typeId.value && types.length > 0) {
          this.createForm.controls.typeId.setValue(types[0].relation_type_id);
        }
      },
      error: (err: unknown) => {
        if (generation === this.generation) this.error.set(this.message(err));
      },
    });
  }

  reload(): void {
    if (!this.knowledgeId) return;
    const generation = this.generation;
    const offset = this.page() * PAGE_SIZE;
    this.loading.set(true);
    this.api.list(this.knowledgeId, offset, PAGE_SIZE).pipe(
      takeUntilDestroyed(this.destroyRef),
      finalize(() => { if (generation === this.generation) this.loading.set(false); }),
    ).subscribe({
      next: result => {
        if (generation !== this.generation) return;
        this.items.set(result.items);
        this.total.set(result.total);
      },
      error: (err: unknown) => {
        if (generation === this.generation) this.error.set(this.message(err));
      },
    });
  }

  nextPage(): void {
    if ((this.page()+1)*PAGE_SIZE >= this.total()) return;
    this.page.update(page => page+1);
    this.reload();
  }

  previousPage(): void {
    if (this.page() === 0) return;
    this.page.update(page => page-1);
    this.reload();
  }

  peerId(item: KnowledgeRelation): string {
    return item.origin_knowledge_id === this.knowledgeId
      ? item.target_knowledge_id : item.origin_knowledge_id;
  }

  direction(item: KnowledgeRelation): string {
    const type = this.types().find(t => t.relation_type_id === item.relation_type_id);
    if (!type?.is_directed) return 'Bidirectionnelle';
    return item.origin_knowledge_id === this.knowledgeId
      ? 'De cette fiche vers la fiche liée'
      : 'De la fiche liée vers cette fiche';
  }

  typeLabel(id: string): string {
    return this.types().find(type => type.relation_type_id === id)?.label ?? id;
  }

  create(): void {
    if (!this.canCreate || this.saving() || this.createForm.invalid) {
      this.createForm.markAllAsTouched();
      return;
    }
    const value = this.createForm.getRawValue();
    if (value.target.toLowerCase() === this.knowledgeId.toLowerCase()) {
      this.error.set('Une connaissance ne peut pas être reliée à elle-même.');
      return;
    }
    const generation = this.generation;
    this.saving.set(true);
    this.error.set('');
    this.notice.set('');
    this.api.create({
      origin_knowledge_id: value.reverse ? value.target : this.knowledgeId,
      target_knowledge_id: value.reverse ? this.knowledgeId : value.target,
      relation_type_id: value.typeId,
      relation_notes: value.notes.trim() || null,
    }).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => {
      if (generation === this.generation) this.saving.set(false);
    })).subscribe({
      next: () => {
        if (generation !== this.generation) return;
        this.notice.set('Relation ajoutée.');
        this.createForm.controls.target.setValue('');
        this.createForm.controls.notes.setValue('');
        this.page.set(0);
        this.reload();
      },
      error: (err: unknown) => {
        if (generation === this.generation) this.error.set(this.message(err));
      },
    });
  }

  beginEdit(item: KnowledgeRelation): void {
    if (!this.canUpdate) return;
    this.editNotes.setValue(item.relation_notes ?? '');
    this.editing.set(item.relation_id);
    this.error.set('');
  }

  saveNotes(item: KnowledgeRelation): void {
    if (!this.canUpdate || this.saving() || this.editNotes.invalid) return;
    const generation = this.generation;
    this.saving.set(true);
    this.api.updateNotes(item.relation_id, this.editNotes.value.trim() || null, item.revision)
      .pipe(takeUntilDestroyed(this.destroyRef), finalize(() => {
        if (generation === this.generation) this.saving.set(false);
      })).subscribe({
        next: () => {
          if (generation !== this.generation) return;
          this.editing.set(null);
          this.notice.set('Note mise à jour.');
          this.error.set('');
          this.reload();
        },
        error: (err: unknown) => {
          if (generation === this.generation) this.error.set(this.message(err));
        },
      });
  }

  remove(item: KnowledgeRelation): void {
    if (!this.canDelete || this.saving()) return;
    if (!window.confirm('Supprimer uniquement cette relation ? Les connaissances sont conservées.')) return;
    const generation = this.generation;
    this.saving.set(true);
    this.api.delete(item.relation_id, item.revision)
      .pipe(takeUntilDestroyed(this.destroyRef), finalize(() => {
        if (generation === this.generation) this.saving.set(false);
      })).subscribe({
        next: () => {
          if (generation !== this.generation) return;
          this.notice.set('Relation supprimée.');
          this.error.set('');
          this.editing.set(null);
          if (this.page() > 0 && this.items().length === 1) this.page.update(p => p-1);
          this.reload();
        },
        error: (err: unknown) => {
          if (generation === this.generation) this.error.set(this.message(err));
        },
      });
  }

  private message(error: unknown): string {
    if (!(error instanceof HttpErrorResponse)) return 'Impossible de contacter le service des relations.';
    switch (error.status) {
      case 409: return 'Cette relation existe déjà, y compris dans le sens inverse si elle est non orientée.';
      case 412: return 'Relation modifiée depuis votre dernière lecture (412). Actualisez avant de réessayer.';
      case 422: return 'Référence invalide, relation sur soi-même ou fiche cible introuvable.';
      case 403: return 'Vous ne disposez pas des autorisations nécessaires.';
      case 404: return 'Relation ou connaissance introuvable.';
      default: return 'Erreur lors de la gestion des relations (HTTP ' + error.status + ').';
    }
  }
}
