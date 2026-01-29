import api from './api';

export interface SemanticMapping {
    id: number;
    keyword: string;
    keyword_type: 'abbreviation' | 'term' | 'synonym';
    target_column?: string;
    target_condition?: string;
    description?: string;
    is_active: boolean;
    priority: number;
    created_at: string;
    updated_at?: string;
}

export interface SemanticMappingCreate {
    keyword: string;
    keyword_type: 'abbreviation' | 'term' | 'synonym';
    target_column: string;
    target_condition: string;
    description?: string;
    is_active?: boolean;
    priority?: number;
}

export interface SemanticMappingUpdate {
    keyword?: string;
    keyword_type?: 'abbreviation' | 'term' | 'synonym';
    target_column?: string;
    target_condition?: string;
    description?: string;
    is_active?: boolean;
    priority?: number;
}

export interface SemanticMappingListResponse {
    mappings: SemanticMapping[];
    total: number;
}

export const getMappings = async (params?: { keyword_type?: string; is_active?: boolean }) => {
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
