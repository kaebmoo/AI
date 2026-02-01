import api from './api';

export interface ViewColumnMapping {
    col: string;
    alias?: string;
}

export interface ViewCreateRequest {
    view_name: string;
    source_table: string;
    mapping: ViewColumnMapping[];
}

export interface ViewMappingSuggestion {
    col: string;
    suggested_alias: string;
    reason?: string;
}

export const viewBuilderService = {
    listTables: async (): Promise<string[]> => {
        const response = await api.get<string[]>('/admin/schema/tables');
        return response.data;
    },

    suggestMapping: async (tableName: string): Promise<ViewMappingSuggestion[]> => {
        const response = await api.get<ViewMappingSuggestion[]>(`/admin/schema/tables/${tableName}/suggest-mapping`);
        return response.data;
    },

    createView: async (data: ViewCreateRequest): Promise<any> => {
        const response = await api.post('/admin/schema/views', data);
        return response.data;
    }
};
