export interface LoginRequest {
    email: string
    password?: string
    platform: string
}

export interface LoginResponse {
    access_token: string
    token_type: string
    user_email: string
    display_name: string
    role: string
    force_password_change?: boolean
}

export interface User {
    email: string
    display_name: string
    role: string
}
