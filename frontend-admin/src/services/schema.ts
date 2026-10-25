import api from './api';

export interface SchemaMetadata {
    id: number;
    table_name: string;
    column_name: string;
    display_name_th?: string;
    display_name_en?: string;
    description?: string;
    data_type?: string;
    format_hint?: string;
    example_value?: string;
    is_summable: boolean;
    is_groupable: boolean;
    hierarchy_level?: number;
    special_notes?: string;
    source?: string;
    status?: string;
    created_at: string;
    updated_at?: string;
}

export interface SchemaMetadataUpdate {
    display_name_th?: string;
    display_name_en?: string;
    description?: string;
    // data_type is usually not editable as it comes from DB
    format_hint?: string;
    example_value?: string;
    is_summable?: boolean;
    is_groupable?: boolean;
    special_notes?: string;
}

export interface SchemaListResponse {
    columns: SchemaMetadata[];
    total: number;
}

export interface ColumnDraft {
    id: number;
    column_name: string;
    description: string;
    confidence: number | null;
    reason: string | null;
    created_at: string | null;
    current_description: string | null;
}

export interface DraftResult {
    table: string;
    drafted: number;
    skipped: { column_name: string; reason: string }[];
    drafts: { column_name: string; description: string; facts: Record<string, unknown> }[];
}

export interface SchemaMetadataCreate {
    table_name: string;
    column_name: string;
    data_type: string;
    display_name_th?: string;
    display_name_en?: string;
    description?: string;
    is_summable?: boolean;
    is_groupable?: boolean;
    special_notes?: string;
}

export const getSchemaColumns = async (params?: { table_name?: string }) => {
    const response = await api.get<SchemaListResponse>('/admin/schema/columns', { params });
    return response.data;
};

export const getSchemaColumn = async (id: number) => {
    const response = await api.get<SchemaMetadata>(`/admin/schema/columns/${id}`);
    return response.data;
};

export const createSchemaColumn = async (data: SchemaMetadataCreate) => {
    const response = await api.post<SchemaMetadata>('/admin/schema/columns', data);
    return response.data;
};

export const updateSchemaColumn = async (id: number, data: SchemaMetadataUpdate) => {
    const response = await api.put<SchemaMetadata>(`/admin/schema/columns/${id}`, data);
    return response.data;
};

export const deleteSchemaColumn = async (id: number) => {
    await api.delete(`/admin/schema/columns/${id}`);
};

export const draftColumns = async (table: string) => {
    const response = await api.post<DraftResult>('/admin/schema/columns/draft', undefined, { params: { table } });
    return response.data;
};

export const getColumnDrafts = async (table: string) => {
    const response = await api.get<ColumnDraft[]>('/admin/schema/columns/drafts', { params: { table } });
    return response.data;
};

export const acceptColumnDraft = async (id: number, description?: string) => {
    const response = await api.post<SchemaMetadata>(`/admin/schema/columns/drafts/${id}/accept`, { description });
    return response.data;
};

export const rejectColumnDraft = async (id: number) => {
    const response = await api.post<{ id: number; status: string }>(`/admin/schema/columns/drafts/${id}/reject`);
    return response.data;
};
