import api from './api';

export interface LoginRequest {
    email: string;
    platform?: string;
}

export interface VerifyRequest {
    email: string;
    otp: string;
    platform?: string;
}

export interface AuthResponse {
    access_token: string;
    token_type: string;
    user_email: string;
    display_name: string;
}

export const authService = {
    login: async (email: string) => {
        const response = await api.post('/auth/login', { email, platform: 'web' });
        return response.data;
    },

    verify: async (email: string, otp: string) => {
        const response = await api.post<AuthResponse>('/auth/verify', {
            email,
            otp,
            platform: 'web'
        });
        return response.data;
    },

    logout: async () => {
        // Client-side only for token-based auth unless we have a revoke endpoint
        return true;
    }
};
