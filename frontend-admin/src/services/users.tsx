import api from './api'

interface CreateUserRequest {
    email: string
    password?: string
    display_name: string
    role: string
    department?: string
    is_active?: boolean
}

interface UpdateUserRequest {
    id: number
    display_name?: string
    role?: string
    department?: string
    is_active?: boolean
    password?: string
}

export const userService = {
    list: async () => {
        const response = await api.get('/users')
        return response.data
    },

    create: async (data: CreateUserRequest) => {
        const response = await api.post('/users', data)
        return response.data
    },

    update: async (data: UpdateUserRequest) => {
        const { id, ...rest } = data
        const response = await api.put(`/users/${id}`, rest)
        return response.data
    },

    delete: async (id: number) => {
        await api.delete(`/users/${id}`)
    }
}
