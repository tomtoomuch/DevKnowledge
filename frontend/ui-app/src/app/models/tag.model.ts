/** Canonical tags are identified by UUID; names can be reused by many records. */
export interface TagRecord {
  tag_id: string;
  name: string;
}
export interface TagPage {
  items: TagRecord[];
  total: number;
  skip: number;
  limit: number;
}
