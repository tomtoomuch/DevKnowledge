export interface RelationType {
  relation_type_id: string;
  code: string;
  label: string;
  is_directed: boolean;
}

export interface KnowledgeRelationWrite {
  origin_knowledge_id: string;
  target_knowledge_id: string;
  relation_type_id: string;
  relation_notes: string | null;
}

export interface KnowledgeRelation extends KnowledgeRelationWrite {
  relation_id: string;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface RelationPage {
  items: KnowledgeRelation[];
  total: number;
  skip: number;
  limit: number;
}
