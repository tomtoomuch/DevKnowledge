/** Immutable catalog records; associations are UUID references on a knowledge. */
export interface TechnologyRecord {
  technology_id: string;
  name: string;
  category: string | null;
}

export interface TechnologyVersionRecord {
  technology_version_id: string;
  technology_id: string;
  version: string;
  release_date: string | null;
}

export interface CatalogPage<T> {
  items: T[];
  total: number;
  skip: number;
  limit: number;
}
