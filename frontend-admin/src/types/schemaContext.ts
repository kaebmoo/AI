export interface SchemaContext {
    id: number;
    name: string;
    display_name: string;
    description?: string;
    main_view: string;
    is_active: boolean;
    priority: number;
    keywords: string[];
    created_at?: string;
}

export interface SchemaContextCreate {
    name: string;
    display_name?: string;
    description?: string;
    main_view?: string;
    is_active?: boolean;
    priority?: number;
    keywords?: string[];
}

export interface SchemaContextUpdate {
    display_name?: string;
    description?: string;
    main_view?: string;
    is_active?: boolean;
    priority?: number;
    keywords?: string[];
}
