import { CommonModule } from '@angular/common';
import { HttpErrorResponse, HttpResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { debounceTime, distinctUntilChanged, finalize } from 'rxjs';
import {
  Knowledge, KnowledgeType, KnowledgeWrite, KNOWLEDGE_TYPES, knowledgeTypeLabel,
} from './models/knowledge.model';
import {
  SPECIALIZATION_FIELDS, DetailValue, KnowledgeDetails,
  detailToFormValue, displayDetailValue, toSpecialization,
} from './models/specialization-fields';
import { KnowledgeApiService } from './services/knowledge-api.service';
import { TagApiService } from './services/tag-api.service';
import { TagRecord } from './models/tag.model';
import { TechnologyApiService } from './services/technology-api.service';
import { TechnologyRecord, TechnologyVersionRecord } from './models/technology.model';
import { AuthService, LocalIdentity } from './services/auth.service';
import { UserAdminComponent } from './components/user-admin.component';
import { MonitoringComponent } from './components/monitoring.component';

type EditorMode = 'view' | 'create' | 'edit';
const PAGE_SIZE = 20;

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, UserAdminComponent, MonitoringComponent],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AppComponent implements OnInit {
  private readonly api = inject(KnowledgeApiService);
  private readonly tagApi = inject(TagApiService);
  private readonly technologyApi = inject(TechnologyApiService);
  private readonly auth = inject(AuthService);
  private readonly destroyRef = inject(DestroyRef);

  readonly authMode = signal<'checking' | 'login' | 'active'>('checking');
  readonly principal = signal<LocalIdentity | null>(null);
  readonly section = signal<'knowledge' | 'users' | 'monitoring'>('knowledge');
  readonly loginError = signal('');
  readonly loggingIn = signal(false);
  readonly loginForm = new FormGroup({
    username: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
    password: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
  });

  readonly types = KNOWLEDGE_TYPES;
  readonly currentType = signal<KnowledgeType>('CODE_SNIPPET');
  readonly specializationFields = computed(() => SPECIALIZATION_FIELDS[this.currentType()]);
  readonly detailsEnabled = new FormControl(false, { nonNullable: true });
  detailsForm = new FormGroup<Record<string, FormControl<string>>>({});
  readonly pageSize = PAGE_SIZE;
  readonly mode = signal<EditorMode>('view');
  readonly items = signal<Knowledge[]>([]);
  readonly selected = signal<Knowledge | null>(null);
  readonly etag = signal<string | null>(null);
  readonly total = signal(0);
  readonly pageIndex = signal(0);
  readonly busy = signal(false);
  readonly detailLoading = signal(false);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly formError = signal('');
  readonly notice = signal('');
  readonly confirmingDelete = signal(false);
  readonly searchTerm = signal('');
  readonly favoritesOnly = signal(false);
  readonly tags = signal<TagRecord[]>([]);
  readonly tagError = signal('');
  readonly savingTag = signal(false);
  readonly tagSelection = signal<string[]>([]);
  readonly tagSelectionDirty = signal(false);
  readonly tagName = new FormControl('', {
    nonNullable: true, validators: [Validators.required, Validators.maxLength(100)],
  });
  readonly technologies = signal<TechnologyRecord[]>([]);
  readonly technologyVersions = signal<TechnologyVersionRecord[]>([]);
  readonly technologySelection = signal<string[]>([]);
  readonly versionSelection = signal<string[]>([]);
  readonly technologySelectionDirty = signal(false);
  readonly technologyError = signal('');
  readonly savingTechnology = signal(false);
  readonly newTechnologyName = new FormControl('', {
    nonNullable: true, validators: [Validators.required, Validators.maxLength(100)],
  });
  readonly newTechnologyCategory = new FormControl('', {
    nonNullable: true, validators: [Validators.maxLength(100)],
  });
  readonly newVersionTechnology = new FormControl('', {
    nonNullable: true, validators: [Validators.required],
  });
  readonly newVersionName = new FormControl('', {
    nonNullable: true, validators: [Validators.required, Validators.maxLength(50)],
  });
  readonly newVersionDate = new FormControl('', { nonNullable: true });

  // The KMS now performs all list filters before pagination.
  readonly visibleItems = computed(() => this.items());
  private listSequence = 0;
  private authGeneration = 0;
  readonly pageCount = computed(() => Math.max(1, Math.ceil(this.total() / PAGE_SIZE)));
  readonly currentPage = computed(() => this.pageIndex() + 1);

  readonly search = new FormControl('', { nonNullable: true });
  readonly typeFilter = new FormControl<KnowledgeType | ''>('', { nonNullable: true });
  readonly statusFilter = new FormControl('', { nonNullable: true });
  readonly favoritesFilter = new FormControl(false, { nonNullable: true });
  readonly tagFilter = new FormControl('', { nonNullable: true });
  readonly technologyFilter = new FormControl('', { nonNullable: true });
  readonly versionFilter = new FormControl('', { nonNullable: true });

  readonly editor = new FormGroup({
    knowledge_type: new FormControl<KnowledgeType>('CODE_SNIPPET', {
      nonNullable: true, validators: [Validators.required],
    }),
    title: new FormControl('', {
      nonNullable: true, validators: [Validators.required, Validators.maxLength(150), Validators.pattern(/.*\S.*/s)],
    }),
    content: new FormControl('', {
      nonNullable: true, validators: [Validators.required, Validators.pattern(/[\s\S]*\S[\s\S]*/)],
    }),
    description: new FormControl('', { nonNullable: true }),
    language_code: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(10)] }),
    difficulty_level: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(30)] }),
    status: new FormControl('DRAFT', {
      nonNullable: true, validators: [Validators.required, Validators.maxLength(30)],
    }),
    is_favorite: new FormControl(false, { nonNullable: true }),
  });

  ngOnInit(): void {
    this.configureDetails(this.editor.controls.knowledge_type.value);
    this.editor.controls.knowledge_type.valueChanges.pipe(
      takeUntilDestroyed(this.destroyRef),
    ).subscribe(kind => {
      this.configureDetails(kind);
      // Switching type keeps specialization opt-in but replaces incompatible fields.
      this.detailsForm.markAsDirty();
    });
    this.search.valueChanges.pipe(
      debounceTime(300), distinctUntilChanged(), takeUntilDestroyed(this.destroyRef),
    ).subscribe((value) => {
      this.searchTerm.set(value.trim());
      this.resetPage();
    });
    this.typeFilter.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.resetPage());
    this.statusFilter.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.resetPage());
    this.tagFilter.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.resetPage());
    this.technologyFilter.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.resetPage());
    this.versionFilter.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.resetPage());
    this.favoritesFilter.valueChanges.pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((value) => {
        this.favoritesOnly.set(value);
        this.resetPage();
      });
    this.checkAuth();
  }

  can(permission: string): boolean {
    return this.principal()?.permissions.includes(permission) ?? false;
  }

  showSection(next: 'knowledge' | 'users' | 'monitoring'): void {
    if (next === 'users' && !this.can('users.manage')) return;
    if (next === this.section() || !this.mayLeaveEditor()) return;
    this.section.set(next);
  }

  checkAuth(): void {
    this.authMode.set('checking');
    this.auth.me().subscribe({
      next: principal => this.signedIn(principal),
      error: (error: unknown) => {
        this.authMode.set('login');
        this.principal.set(null);
        if (error instanceof HttpErrorResponse && error.status !== 401) {
          this.loginError.set('Vérification de session impossible. Vérifie les conteneurs.');
        }
      },
    });
  }

  submitLogin(): void {
    if (this.loginForm.invalid || this.loggingIn()) return;
    this.loginError.set('');
    this.loggingIn.set(true);
    const credentials = this.loginForm.getRawValue();
    this.auth.login(credentials.username, credentials.password).pipe(
      finalize(() => this.loggingIn.set(false)),
    ).subscribe({
      next: principal => {
        this.loginForm.controls.password.reset();
        this.signedIn(principal);
      },
      error: (error: unknown) => {
        this.loginError.set(error instanceof HttpErrorResponse && error.status === 429
          ? 'Trop de tentatives. Réessaie après une minute.'
          : 'Connexion refusée. Vérifie les identifiants et le compte administrateur initial.');
      },
    });
  }

  logout(): void {
    this.auth.logout().subscribe({
      next: () => {
        this.clearWorkspace();
        this.authMode.set('login');
        this.loginForm.reset({ username: '', password: '' });
      },
      error: () => this.error.set('Déconnexion impossible. Réessaie.'),
    });
  }

  private signedIn(principal: LocalIdentity): void {
    this.clearWorkspace();
    this.principal.set(principal);
    this.authMode.set('active');
    this.loginError.set('');
    this.loadTags();
    this.loadTechnologies();
    this.loadPage();
  }

  private clearWorkspace(): void {
    this.section.set('knowledge');
    ++this.authGeneration;
    ++this.listSequence;
    this.principal.set(null);
    this.items.set([]);
    this.total.set(0);
    this.selected.set(null);
    this.etag.set(null);
    this.pageIndex.set(0);
    this.mode.set('view');
    this.busy.set(false);
    this.detailLoading.set(false);
    this.saving.set(false);
    this.confirmingDelete.set(false);
    this.notice.set('');
    this.error.set('');
    this.formError.set('');
    this.searchTerm.set('');
    this.favoritesOnly.set(false);
    this.tags.set([]);
    this.tagError.set('');
    this.savingTag.set(false);
    this.tagSelection.set([]);
    this.tagSelectionDirty.set(false);
    this.tagName.reset('', { emitEvent: false });
    this.technologies.set([]);
    this.technologyVersions.set([]);
    this.technologySelection.set([]);
    this.versionSelection.set([]);
    this.technologySelectionDirty.set(false);
    this.technologyError.set('');
    this.savingTechnology.set(false);
    this.newTechnologyName.reset('', { emitEvent: false });
    this.newTechnologyCategory.reset('', { emitEvent: false });
    this.newVersionTechnology.reset('', { emitEvent: false });
    this.newVersionName.reset('', { emitEvent: false });
    this.newVersionDate.reset('', { emitEvent: false });
    this.search.setValue('', { emitEvent: false });
    this.typeFilter.setValue('', { emitEvent: false });
    this.statusFilter.setValue('', { emitEvent: false });
    this.favoritesFilter.setValue(false, { emitEvent: false });
    this.tagFilter.setValue('', { emitEvent: false });
    this.technologyFilter.setValue('', { emitEvent: false });
    this.versionFilter.setValue('', { emitEvent: false });
    this.editor.reset({
      knowledge_type: 'CODE_SNIPPET', title: '', content: '', description: '',
      language_code: '', difficulty_level: '', status: 'DRAFT', is_favorite: false,
    });
    this.detailsEnabled.setValue(false, { emitEvent: false });
    this.detailsEnabled.markAsPristine();
    this.configureDetails('CODE_SNIPPET');
    this.editor.markAsPristine();
  }

  typeLabel(code: string): string {
    return knowledgeTypeLabel(code);
  }

  tagLabel(tagId: string): string {
    return this.tags().find(tag => tag.tag_id === tagId)?.name ?? tagId;
  }

  isTagSelected(tagId: string): boolean {
    return this.tagSelection().includes(tagId);
  }

  toggleTag(tagId: string, selected: boolean): void {
    this.tagSelection.update(ids => selected
      ? (ids.includes(tagId) ? ids : [...ids, tagId])
      : ids.filter(id => id !== tagId));
    this.tagSelectionDirty.set(true);
  }

  private loadTags(): void {
    const generation = this.authGeneration;
    this.tagError.set('');
    this.tagApi.list().subscribe({
      next: page => {
        if (generation !== this.authGeneration) return;
        this.tags.set(page.items);
        if (page.total > page.items.length) {
          this.tagError.set('Seuls les 100 premiers tags sont proposés. La pagination avancée reste à développer.');
        }
      },
      error: (error: unknown) => {
        if (generation === this.authGeneration) this.tagError.set(this.errorMessage(error));
      },
    });
  }

  createTag(): void {
    if (!this.can('knowledge.create') || this.tagName.invalid || this.savingTag()) return;
    const name = this.tagName.value.trim();
    if (!name) return;
    const generation = this.authGeneration;
    this.tagError.set('');
    this.savingTag.set(true);
    this.tagApi.create(name).pipe(
      finalize(() => this.savingTag.set(false)),
    ).subscribe({
      next: tag => {
        if (generation !== this.authGeneration) return;
        this.tags.update(items => [...items, tag]
          .sort((a, b) => a.name.localeCompare(b.name, 'fr')));
        this.toggleTag(tag.tag_id, true);
        this.tagName.setValue('');
        this.notice.set('Tag créé. Enregistre la connaissance pour lui associer ce tag.');
      },
      error: (error: unknown) => {
        if (generation !== this.authGeneration) return;
        this.tagError.set(error instanceof HttpErrorResponse && error.status === 409
          ? 'Ce tag existe déjà.'
          : this.errorMessage(error));
      },
    });
  }

  technologyLabel(technologyId: string): string {
    return this.technologies().find(item => item.technology_id === technologyId)?.name ?? technologyId;
  }

  versionLabel(versionId: string): string {
    const record = this.technologyVersions().find(item => item.technology_version_id === versionId);
    return record ? this.technologyLabel(record.technology_id) + ' · ' + record.version : versionId;
  }

  isTechnologySelected(id: string): boolean {
    return this.technologySelection().includes(id);
  }

  isVersionSelected(id: string): boolean {
    return this.versionSelection().includes(id);
  }

  hasVersionForTechnology(id: string): boolean {
    return this.technologyVersions().some(version =>
      version.technology_id === id && this.isVersionSelected(version.technology_version_id));
  }

  toggleTechnology(id: string, checked: boolean): void {
    this.technologySelection.update(ids => checked
      ? (ids.includes(id) ? ids : [...ids, id])
      : ids.filter(item => item !== id));
    if (checked) {
      // A generic link replaces precise links for the same technology.
      const versions = new Set(this.technologyVersions()
        .filter(version => version.technology_id === id).map(version => version.technology_version_id));
      this.versionSelection.update(ids => ids.filter(item => !versions.has(item)));
    }
    this.technologySelectionDirty.set(true);
  }

  toggleVersion(id: string, checked: boolean): void {
    const version = this.technologyVersions().find(item => item.technology_version_id === id);
    if (checked && version) {
      // Precise version links take precedence over the generic association.
      this.technologySelection.update(ids => ids.filter(item => item !== version.technology_id));
    }
    this.versionSelection.update(ids => checked
      ? (ids.includes(id) ? ids : [...ids, id])
      : ids.filter(item => item !== id));
    this.technologySelectionDirty.set(true);
  }

  private loadTechnologies(): void {
    const generation = this.authGeneration;
    this.technologyError.set('');
    this.technologyApi.listTechnologies().subscribe({
      next: page => {
        if (generation !== this.authGeneration) return;
        this.technologies.set(page.items);
        if (page.total > page.items.length) {
          this.technologyError.set('Plus de 100 technologies : seules les premières sont proposées.');
        }
      },
      error: (error: unknown) => {
        if (generation === this.authGeneration) this.technologyError.set(this.errorMessage(error));
      },
    });
    this.technologyApi.listVersions().subscribe({
      next: page => {
        if (generation !== this.authGeneration) return;
        this.technologyVersions.set(page.items);
        if (page.total > page.items.length) {
          this.technologyError.set('Plus de 100 versions : seules les premières sont proposées.');
        }
      },
      error: (error: unknown) => {
        if (generation === this.authGeneration) this.technologyError.set(this.errorMessage(error));
      },
    });
  }

  createTechnology(): void {
    if (!this.can('knowledge.create') || this.savingTechnology() || this.newTechnologyName.invalid) return;
    const name = this.newTechnologyName.value.trim();
    if (!name) return;
    const generation = this.authGeneration;
    this.technologyError.set('');
    this.savingTechnology.set(true);
    this.technologyApi.createTechnology(
      name, this.newTechnologyCategory.value.trim() || null,
    ).pipe(finalize(() => this.savingTechnology.set(false))).subscribe({
      next: record => {
        if (generation !== this.authGeneration) return;
        this.technologies.update(items => [...items, record]
          .sort((a, b) => a.name.localeCompare(b.name, 'fr')));
        this.toggleTechnology(record.technology_id, true);
        this.newVersionTechnology.setValue(record.technology_id);
        this.newTechnologyName.setValue('');
        this.newTechnologyCategory.setValue('');
        this.notice.set('Technologie créée : enregistre la connaissance pour la lier.');
      },
      error: (error: unknown) => {
        if (generation !== this.authGeneration) return;
        this.technologyError.set(error instanceof HttpErrorResponse && error.status === 409
          ? 'Cette technologie existe déjà.' : this.errorMessage(error));
      },
    });
  }

  createVersion(): void {
    if (!this.can('knowledge.create') || this.savingTechnology() ||
        this.newVersionName.invalid || this.newVersionTechnology.invalid) return;
    const techId = this.newVersionTechnology.value;
    const version = this.newVersionName.value.trim();
    if (!techId || !version) return;
    const date = this.newVersionDate.value || null;
    const generation = this.authGeneration;
    this.technologyError.set('');
    this.savingTechnology.set(true);
    this.technologyApi.createVersion(techId, version, date).pipe(
      finalize(() => this.savingTechnology.set(false)),
    ).subscribe({
      next: record => {
        if (generation !== this.authGeneration) return;
        this.technologyVersions.update(items => [...items, record].sort((a, b) =>
          (this.technologyLabel(a.technology_id) + a.version).localeCompare(
            this.technologyLabel(b.technology_id) + b.version, 'fr')));
        this.toggleVersion(record.technology_version_id, true);
        this.newVersionName.setValue('');
        this.newVersionDate.setValue('');
        this.notice.set('Version créée : enregistre la connaissance pour la lier.');
      },
      error: (error: unknown) => {
        if (generation !== this.authGeneration) return;
        this.technologyError.set(error instanceof HttpErrorResponse && error.status === 409
          ? 'Cette version existe déjà pour cette technologie.' : this.errorMessage(error));
      },
    });
  }

  dateLabel(value: string): string {
    return new Date(value).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  resetFilters(): void {
    this.search.setValue('');
    this.favoritesFilter.setValue(false);
    this.typeFilter.setValue('');
    this.statusFilter.setValue('');
    this.tagFilter.setValue('');
    this.technologyFilter.setValue('');
    this.versionFilter.setValue('');
  }

  reload(): void {
    this.notice.set('');
    this.loadPage();
  }

  previousPage(): void {
    if (this.pageIndex() === 0) return;
    this.pageIndex.update((value) => value - 1);
    this.loadPage();
  }

  nextPage(): void {
    if (this.currentPage() >= this.pageCount()) return;
    this.pageIndex.update((value) => value + 1);
    this.loadPage();
  }

  createKnowledge(): void {
    if (!this.can('knowledge.create') || !this.mayLeaveEditor()) return;
    this.notice.set('');
    this.formError.set('');
    this.error.set('');
    this.selected.set(null);
    this.etag.set(null);
    this.confirmingDelete.set(false);
    this.tagSelection.set([]);
    this.tagSelectionDirty.set(false);
    this.tagName.setValue('');
    this.technologySelection.set([]);
    this.versionSelection.set([]);
    this.technologySelectionDirty.set(false);
    this.newTechnologyName.setValue('');
    this.newVersionName.setValue('');
    this.editor.reset({
      knowledge_type: 'CODE_SNIPPET',
      title: '', content: '', description: '',
      language_code: '', difficulty_level: '', status: 'DRAFT', is_favorite: false,
    });
    this.detailsEnabled.setValue(false, { emitEvent: false });
    this.detailsEnabled.markAsPristine();
    this.configureDetails('CODE_SNIPPET');
    this.editor.markAsPristine();
    this.mode.set('create');
  }

  openKnowledge(item: Knowledge): void {
    if (!this.mayLeaveEditor()) return;
    this.fetchDetail(item.knowledge_id);
  }

  refreshDetail(): void {
    const current = this.selected();
    if (current && window.confirm('Recharger la version enregistrée ? Les modifications non sauvegardées seront perdues.')) {
      this.fetchDetail(current.knowledge_id);
    }
  }

  beginEdit(): void {
    if (!this.can('knowledge.update')) return;
    const item = this.selected();
    if (!item) return;
    this.fillEditor(item);
    this.formError.set('');
    this.confirmingDelete.set(false);
    this.mode.set('edit');
  }

  cancelEdit(): void {
    this.mode.set('view');
    this.confirmingDelete.set(false);
    this.formError.set('');
    this.editor.markAsPristine();
    this.detailsForm.markAsPristine();
    this.detailsEnabled.markAsPristine();
    this.tagSelectionDirty.set(false);
    this.technologySelectionDirty.set(false);
  }

  saveKnowledge(): void {
    if ((this.mode() === 'create' && !this.can('knowledge.create')) ||
        (this.mode() === 'edit' && !this.can('knowledge.update'))) return;
    if (this.saving()) return;
    if (this.editor.invalid || (this.detailsEnabled.value && this.detailsForm.invalid)) {
      this.editor.markAllAsTouched();
      if (this.detailsEnabled.value) this.detailsForm.markAllAsTouched();
      this.formError.set('Vérifie les champs obligatoires, les formats et les limites du type sélectionné.');
      return;
    }
    const value = this.editor.getRawValue();
    const payload: KnowledgeWrite = {
      knowledge_type: value.knowledge_type,
      title: value.title.trim(),
      content: value.content,
      description: value.description.trim() || null,
      language_code: value.language_code.trim() || null,
      difficulty_level: value.difficulty_level.trim() || null,
      status: value.status.trim(),
      is_favorite: value.is_favorite,
      tag_ids: this.tagSelection(),
      technology_ids: this.technologySelection(),
      technology_version_ids: this.versionSelection(),
    };
    if (!payload.title || !payload.content.trim()) {
      this.formError.set('Le titre et le contenu ne peuvent pas être vides.');
      return;
    }
    try {
      // A PATCH contains the complete specialization, never a partial merge.
      // An explicit null removes a previous specialization without deleting the knowledge.
      payload.details = this.detailsEnabled.value
        ? toSpecialization(this.specializationFields(), this.detailsForm.getRawValue())
        : null;
    } catch (error) {
      this.formError.set(error instanceof Error ? error.message : 'Détails spécialisés invalides.');
      return;
    }
    this.formError.set('');
    this.notice.set('');
    const current = this.selected();
    const tag = this.etag();
    if (this.mode() === 'edit' && (!current || !tag)) {
      this.formError.set('Révision absente : recharge la fiche avant toute modification.');
      return;
    }
    const generation = this.authGeneration;
    this.saving.set(true);
    const operation = this.mode() === 'create'
      ? this.api.create(payload)
      : this.api.update(current!.knowledge_id, payload, tag!);
    operation.pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (response) => {
        if (generation !== this.authGeneration) return;
        this.acceptSaved(response);
        this.notice.set(this.mode() === 'create' ? 'Connaissance créée.' : 'Modifications enregistrées.');
        this.mode.set('view');
        this.editor.markAsPristine();
        this.detailsForm.markAsPristine();
        this.detailsEnabled.markAsPristine();
        this.tagSelectionDirty.set(false);
        this.technologySelectionDirty.set(false);
        this.loadPage();
      },
      error: (error: unknown) => {
        if (generation === this.authGeneration) this.formError.set(this.errorMessage(error));
      },
    });
  }

  askDelete(): void {
    if (!this.can('knowledge.delete')) return;
    this.confirmingDelete.set(true);
    this.formError.set('');
  }

  cancelDelete(): void {
    this.confirmingDelete.set(false);
  }

  deleteKnowledge(): void {
    const item = this.selected();
    const tag = this.etag();
    if (!item || !tag || this.saving()) {
      this.formError.set('Révision absente : recharge la fiche avant toute suppression.');
      return;
    }
    const generation = this.authGeneration;
    this.saving.set(true);
    this.formError.set('');
    this.api.delete(item.knowledge_id, tag).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: () => {
        if (generation !== this.authGeneration) return;
        this.selected.set(null);
        this.etag.set(null);
        this.confirmingDelete.set(false);
        this.mode.set('view');
        this.notice.set('Connaissance retirée de la liste (suppression logique).');
        if (this.pageIndex() > 0 && this.items().length === 1) this.pageIndex.update((value) => value - 1);
        this.loadPage();
      },
      error: (error: unknown) => {
        if (generation === this.authGeneration) this.formError.set(this.errorMessage(error));
      },
    });
  }

  private resetPage(): void {
    this.pageIndex.set(0);
    this.loadPage();
  }

  private loadPage(): void {
    const sequence = ++this.listSequence;
    const generation = this.authGeneration;
    this.busy.set(true);
    this.error.set('');
    const type = this.typeFilter.value;
    const status = this.statusFilter.value.trim();
    const q = this.searchTerm().slice(0, 100);
    this.api.list({
      skip: this.pageIndex() * PAGE_SIZE,
      limit: PAGE_SIZE,
      ...(type ? { knowledge_type: type } : {}),
      ...(status ? { status } : {}),
      ...(q ? { q } : {}),
      ...(this.favoritesOnly() ? { is_favorite: true } : {}),
      ...(this.tagFilter.value ? { tag_id: this.tagFilter.value } : {}),
      ...(this.technologyFilter.value ? { technology_id: this.technologyFilter.value } : {}),
      ...(this.versionFilter.value ? { technology_version_id: this.versionFilter.value } : {}),
    }).pipe(finalize(() => {
      if (sequence === this.listSequence && generation === this.authGeneration) this.busy.set(false);
    })).subscribe({
      next: (page) => {
        // Ignore responses to superseded searches and filter changes.
        if (sequence !== this.listSequence || generation !== this.authGeneration) return;
        this.items.set(page.items);
        this.total.set(page.total);
      },
      error: (error: unknown) => {
        if (sequence !== this.listSequence || generation !== this.authGeneration) return;
        this.items.set([]);
        this.total.set(0);
        this.error.set(this.errorMessage(error));
      },
    });
  }

  private fetchDetail(id: string): void {
    const generation = this.authGeneration;
    this.detailLoading.set(true);
    this.formError.set('');
    this.error.set('');
    this.confirmingDelete.set(false);
    this.api.get(id).pipe(finalize(() => {
      if (generation === this.authGeneration) this.detailLoading.set(false);
    })).subscribe({
      next: (response) => {
        if (generation !== this.authGeneration) return;
        const item = response.body;
        if (!item) {
          this.error.set('Réponse vide du service de connaissances.');
          return;
        }
        this.selected.set(item);
        this.etag.set(response.headers.get('ETag') ?? '"' + item.revision + '"');
        this.mode.set('view');
        this.editor.markAsPristine();
      },
      error: (error: unknown) => {
        if (generation === this.authGeneration) this.error.set(this.errorMessage(error));
      },
    });
  }

  private acceptSaved(response: HttpResponse<Knowledge>): void {
    const item = response.body;
    if (item) {
      this.selected.set(item);
      this.etag.set(response.headers.get('ETag') ?? '"' + item.revision + '"');
    }
  }

  private fillEditor(item: Knowledge): void {
    this.editor.reset({
      knowledge_type: item.knowledge_type,
      title: item.title,
      content: item.content,
      description: item.description ?? '',
      language_code: item.language_code ?? '',
      difficulty_level: item.difficulty_level ?? '',
      status: item.status,
      is_favorite: item.is_favorite,
    });
    this.configureDetails(item.knowledge_type, item.details);
    this.detailsEnabled.setValue(item.details != null, { emitEvent: false });
    this.detailsEnabled.markAsPristine();
    this.tagSelection.set(item.tag_ids ?? []);
    this.tagSelectionDirty.set(false);
    this.technologySelection.set(item.technology_ids ?? []);
    this.versionSelection.set(item.technology_version_ids ?? []);
    this.technologySelectionDirty.set(false);
    this.editor.markAsPristine();
  }

  private configureDetails(kind: KnowledgeType, details?: KnowledgeDetails | null): void {
    this.currentType.set(kind);
    this.detailsForm = new FormGroup<Record<string, FormControl<string>>>({});
    for (const field of SPECIALIZATION_FIELDS[kind]) {
      const validators = [];
      if (field.required) validators.push(Validators.required, Validators.pattern(/[\s\S]*\S[\s\S]*/));
      if (field.maxLength !== undefined) validators.push(Validators.maxLength(field.maxLength));
      if (field.kind === 'integer') {
        validators.push(Validators.pattern(/^-?\d+$/));
        if (field.min !== undefined) validators.push(Validators.min(field.min));
        if (field.max !== undefined) validators.push(Validators.max(field.max));
      }
      if (field.kind === 'uuid') {
        validators.push(Validators.pattern(/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/));
      }
      this.detailsForm.addControl(field.key, new FormControl(
        detailToFormValue(field, details), { nonNullable: true, validators },
      ));
    }
    this.detailsForm.markAsPristine();
  }

  detailsToShow(item: Knowledge): { label: string; value: string }[] {
    if (!item.details) return [];
    return SPECIALIZATION_FIELDS[item.knowledge_type]
      .filter(field => item.details?.[field.key] !== undefined && item.details?.[field.key] !== null)
      .map(field => ({
        label: field.label.replace(/ \*$/, ''),
        value: displayDetailValue(field, item.details![field.key] as DetailValue),
      }));
  }

  private mayLeaveEditor(): boolean {
    return this.mode() === 'view' ||
      (!this.editor.dirty && !this.detailsForm.dirty &&
        !this.detailsEnabled.dirty && !this.tagSelectionDirty() &&
        !this.technologySelectionDirty()) ||
      window.confirm('Abandonner les modifications non enregistrées ?');
  }

  private errorMessage(error: unknown): string {
    if (!(error instanceof HttpErrorResponse)) return 'Une erreur inattendue est survenue.';
    switch (error.status) {
      case 0: return 'Connexion impossible. Vérifie que le frontend et la Gateway fonctionnent.';
      case 401:
        this.clearWorkspace();
        this.authMode.set('login');
        this.loginError.set('Session expirée. Connecte-toi à nouveau.');
        return 'Session expirée.';
      case 403: return 'Permissions insuffisantes pour cette opération.';
      case 400: return 'Précondition de version invalide. Recharge la connaissance.';
      case 404: return 'Cette connaissance est introuvable ou a été supprimée.';
      case 412: return 'Conflit de modification (412) : une autre version existe. Recharge et compare avant de réessayer.';
      case 413: return 'Le contenu dépasse la limite de 1 Mio de la Gateway.';
      case 422: return 'Données refusées par le serveur (422). Vérifie le titre, le contenu et les champs.';
      case 428: return 'La révision est obligatoire (428). Recharge la connaissance.';
      case 502: return 'Le Knowledge Service ne répond pas à la Gateway (502).';
      case 503: return 'MongoDB ou le Knowledge Service est indisponible (503).';
      case 504: return 'Le Knowledge Service n’a pas répondu à temps (504).';
      default: return 'Échec de l’opération (HTTP ' + error.status + ').';
    }
  }
}
