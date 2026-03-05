import api from './api';

export interface ViewSummaryItem {
    view_name: string;
    source_table: string;
    mapping_count: number;
    metadata_with_thai_count: number;
}

export interface ViewSummaryListResponse {
    views: ViewSummaryItem[];
    total: number;
}

export interface ViewColumnMappingItem {
    id: number;
    view_name: string;
    view_column: string;
    source_table: string;
    source_column: string;
    mapping_type: string;
    expression_sql?: string;
}

export interface ViewMappingsListResponse {
    view_name: string;
    mappings: ViewColumnMappingItem[];
    total: number;
}

export interface MissingColumnInfo {
    view_column: string;
    source_table: string;
    source_column: string;
}

export interface PropagateMetadataResponse {
    view_name: string;
    created: number;
    updated: number;
    skipped: number;
    missing_columns: MissingColumnInfo[];
    message: string;
}

export const viewManagerService = {
    listViews: async (): Promise<ViewSummaryListResponse> => {
        const response = await api.get<ViewSummaryListResponse>('/admin/schema/views/summary');
        return response.data;
    },

    getMappings: async (viewName: string): Promise<ViewMappingsListResponse> => {
        const response = await api.get<ViewMappingsListResponse>(`/admin/schema/views/${viewName}/mappings`);
        return response.data;
    },

    propagateMetadata: async (viewName: string): Promise<PropagateMetadataResponse> => {
        const response = await api.post<PropagateMetadataResponse>(`/admin/schema/views/${viewName}/propagate-metadata`);
        return response.data;
    },
};
