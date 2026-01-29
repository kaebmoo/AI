import api from './api';

export interface User {
    id: number;
    email: string;
    display_name: string;
    role: 'admin' | 'user' | 'viewer';
    department?: string;
    is_active: boolean;
    created_at: string;
    updated_at?: string;
}

export interface UserCreate {
    email: string;
    password?: string;
    display_name: string;
    role: 'admin' | 'user' | 'viewer';
    department?: string;
    is_active?: boolean;
}

export interface UserUpdate {
    password?: string;
    display_name?: string;
    role?: 'admin' | 'user' | 'viewer';
    department?: string;
    is_active?: boolean;
}

export interface UserListResponse {
    users: User[];
    total: number;
}

export const userService = {
    list: async (): Promise<UserListResponse> => {
        const response = await api.get<UserListResponse>('/users');
        return response.data;
    },

    get: async (id: number): Promise<User> => {
        const response = await api.get<User>(`/users/${id}`);
        return response.data;
    },

    create: async (data: UserCreate): Promise<User> => {
        const response = await api.post<User>('/users', data);
        return response.data;
    },

    update: async (data: UserUpdate & { id: number }): Promise<User> => {
        const { id, ...updateData } = data;
        const response = await api.put<User>(`/users/${id}`, updateData);
        return response.data;
    },

    delete: async (id: number): Promise<void> => {
        await api.delete(`/users/${id}`);
    }
};
