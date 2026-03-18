import api from './api';

export interface OnboardingParams {
    view_name: string;
    dry_run?: boolean;
    provider?: string;
    model?: string;
    api_url?: string;
    inspect_only?: boolean;
}

export interface AvailableView {
    name: string;
    type: string;
    has_config: boolean;
    row_count: number | null;
}

export interface AvailableViewsResponse {
    unconfigured: AvailableView[];
    configured: AvailableView[];
}

export interface InspectionSummary {
    row_count: number;
    columns: number;
    detected_structure: string;
    quality_issues: number;
}

export interface AnalysisSummary {
    data_structure: Record<string, any>;
    context: Record<string, any>;
    rules_count: number;
    examples_count: number;
    mappings_count: number;
}

export interface ConfigSummary {
    summary: string;
    sql_count: number;
    sql_statements: string[] | null;
}

export interface ValidationSummary {
    passed: boolean;
    results: Record<string, any>[];
    issues: string[];
}

export interface OnboardingResponse {
    status: string;
    inspection: InspectionSummary;
    analysis?: AnalysisSummary;
    config?: ConfigSummary;
    apply?: Record<string, any>;
    validation?: ValidationSummary;
}

export interface ApplySqlResponse {
    status: string;
    apply: Record<string, any>;
    validation?: ValidationSummary;
}

export interface InspectionDetail {
    view_name: string;
    row_count: number;
    detected_structure: string;
    columns: Array<{
        name: string;
        type: string;
        distinct_count: number;
        null_count: number;
        is_numeric: boolean;
        is_time_column: boolean;
        has_numeric_prefix: boolean;
        sample_values: string[];
    }>;
    cross_column_analyses: Array<{
        value_column: string;
        category_column: string;
        has_mixed_signs: boolean;
        likely_semi_crosstab: boolean;
        categories: Record<string, any>;
    }>;
    quality_issues: Array<{
        column: string;
        type: string;
        description: string;
        examples: string[];
    }>;
}

export const onboardingService = {
    getAvailableViews: async (): Promise<AvailableViewsResponse> => {
        const response = await api.get('/admin/contexts/onboard/available-views');
        return response.data;
    },

    inspect: async (viewName: string): Promise<{ status: string; inspection: InspectionDetail }> => {
        const response = await api.post('/admin/contexts/onboard/inspect', {
            view_name: viewName
        });
        return response.data;
    },

    onboard: async (params: OnboardingParams): Promise<OnboardingResponse> => {
        const response = await api.post('/admin/contexts/onboard', params, {
            timeout: 120000,
        });
        return response.data;
    },

    applySql: async (viewName: string, sqlStatements: string[]): Promise<ApplySqlResponse> => {
        const response = await api.post('/admin/contexts/onboard/apply-sql', {
            view_name: viewName,
            sql_statements: sqlStatements,
        });
        return response.data;
    },

    validate: async (viewName: string) => {
        const response = await api.post('/admin/contexts/onboard/validate', {
            view_name: viewName
        });
        return response.data;
    },
};
