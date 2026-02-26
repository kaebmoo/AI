import api from './api';

export interface SemanticMapping {
    id: number;
    keyword: string;
    keyword_type: 'abbreviation' | 'term' | 'synonym';
    target_column?: string;
    target_condition?: string;
    full_condition?: string;
    description?: string;
    is_active: boolean;
    priority: number;
    context_name?: string | null;  // NULL = global (all contexts), string = scoped context
    created_at: string;
    updated_at?: string;
}

export interface SemanticMappingCreate {
    keyword: string;
    keyword_type: 'abbreviation' | 'term' | 'synonym';
    target_column: string;
    target_condition: string;
    full_condition?: string;
    description?: string;
    is_active?: boolean;
    priority?: number;
    context_name?: string | null;  // NULL = global, e.g. 'transfer price', 'revenue', 'expense'
}

export interface SemanticMappingUpdate {
    keyword?: string;
    keyword_type?: 'abbreviation' | 'term' | 'synonym';
    target_column?: string;
    target_condition?: string;
    full_condition?: string;
    description?: string;
    is_active?: boolean;
    priority?: number;
    context_name?: string | null;
}

export interface SemanticMappingListResponse {
    mappings: SemanticMapping[];
    total: number;
}

export const getMappings = async (params?: {
    keyword_type?: string;
    is_active?: boolean;
    context_name?: string;
}) => {
    const response = await api.get<SemanticMappingListResponse>('/admin/mappings', { params });
    return response.data;
};

export const getMapping = async (id: number) => {
    const response = await api.get<SemanticMapping>(`/admin/mappings/${id}`);
    return response.data;
};

export const createMapping = async (data: SemanticMappingCreate) => {
    const response = await api.post<SemanticMapping>('/admin/mappings', data);
    return response.data;
};

export const updateMapping = async (id: number, data: SemanticMappingUpdate) => {
    const response = await api.put<SemanticMapping>(`/admin/mappings/${id}`, data);
    return response.data;
};

export const deleteMapping = async (id: number) => {
    await api.delete(`/admin/mappings/${id}`);
};

// -----------------------------------------------
// Context helpers (for dropdown in Mapping form)
// -----------------------------------------------

export interface SchemaContext {
    id: number;
    name: string;           // exact value to store in context_name e.g. 'transfer price'
    display_name?: string;  // human label e.g. 'ราคาโอนระหว่างหน่วยงาน'
    is_active: boolean;
}

export interface SchemaContextListResponse {
    contexts: SchemaContext[];
    total: number;
}

export const getContexts = async (): Promise<SchemaContext[]> => {
    const response = await api.get<SchemaContextListResponse>('/admin/contexts');
    return response.data.contexts.filter(c => c.is_active);
};
