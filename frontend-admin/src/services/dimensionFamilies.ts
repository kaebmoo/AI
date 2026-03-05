import api from './api';

export interface DimensionFamilyColumn {
    column_name: string;
    source: 'db' | 'auto' | 'ai';
}

export interface DimensionFamilyItem {
    family_name: string;
    columns: DimensionFamilyColumn[];
    source: 'db' | 'auto' | 'mixed';
}

export interface DimensionFamilyListResponse {
    table_name: string;
    families: DimensionFamilyItem[];
    total: number;
}

export interface DimensionFamilySuggestion {
    family_name: string;
    columns: string[];
}

export interface DimensionFamilyAnalyzeResponse {
    table_name: string;
    suggested_families: DimensionFamilySuggestion[];
    llm_reasoning: string;
    provider_used: string;
}

export interface DimensionFamilyAssignment {
    column_name: string;
    dimension_group: string | null;
}

export interface DimensionFamilyBatchUpdateResponse {
    updated_count: number;
    families: DimensionFamilyItem[];
}

export const getFamilies = async (tableName: string): Promise<DimensionFamilyListResponse> => {
    const response = await api.get<DimensionFamilyListResponse>(
        '/admin/schema/dimension-families',
        { params: { table_name: tableName } }
    );
    return response.data;
};

export const analyzeFamilies = async (
    tableName: string,
    contextName?: string
): Promise<DimensionFamilyAnalyzeResponse> => {
    const response = await api.post<DimensionFamilyAnalyzeResponse>(
        '/admin/schema/dimension-families/analyze',
        { table_name: tableName, context_name: contextName }
    );
    return response.data;
};

export const batchUpdateFamilies = async (
    tableName: string,
    assignments: DimensionFamilyAssignment[]
): Promise<DimensionFamilyBatchUpdateResponse> => {
    const response = await api.put<DimensionFamilyBatchUpdateResponse>(
        '/admin/schema/dimension-families',
        { table_name: tableName, assignments }
    );
    return response.data;
};

export const autoPopulateFamilies = async (
    tableName: string,
    overwrite: boolean = false
): Promise<DimensionFamilyBatchUpdateResponse> => {
    const response = await api.post<DimensionFamilyBatchUpdateResponse>(
        '/admin/schema/dimension-families/auto-populate',
        null,
        { params: { table_name: tableName, overwrite } }
    );
    return response.data;
};
