import axios from 'axios'

// Create axios instance
const api = axios.create({
    baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1',
    headers: {
        'Content-Type': 'application/json',
    },
})

// Request interceptor for API calls
api.interceptors.request.use(
    (config) => {
        const token = localStorage.getItem('token')
        if (token) {
            config.headers['X-Session-Token'] = token
        }
        return config
    },
    (error) => {
        return Promise.reject(error)
    }
)

// Response interceptor for API calls
api.interceptors.response.use(
    (response) => response,
    async (error) => {
        const originalRequest = error.config

        // Handle 401 Unauthorized
        if (error.response?.status === 401 && !originalRequest._retry) {
            localStorage.removeItem('token')
            localStorage.removeItem('user')
            window.location.href = '/login'
        }

        return Promise.reject(error)
    }
)

export default api
