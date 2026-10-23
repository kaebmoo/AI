import axios from 'axios'

const resolveApiUrl = () => {
    const configuredUrl = import.meta.env.VITE_API_URL?.trim()
    if (configuredUrl) {
        return configuredUrl.replace(/\/$/, '')
    }

    if (import.meta.env.DEV) {
        return 'http://localhost:8000/api/v1'
    }

    throw new Error('VITE_API_URL must be configured for production builds.')
}

export const API_URL = resolveApiUrl()

// Create axios instance
const api = axios.create({
    baseURL: API_URL,
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

// 401 → force logout. Registered on the global axios too, because adminService /
// contextService / providerService call `axios.*` directly and would otherwise
// just render "Error loading ..." with a dead token still in localStorage.
const forceLogoutOn401 = (error: any) => {
    if (error.response?.status === 401 && window.location.pathname !== '/login') {
        localStorage.removeItem('token')
        localStorage.removeItem('user')
        window.location.href = '/login'
    }
    return Promise.reject(error)
}
api.interceptors.response.use((response) => response, forceLogoutOn401)
axios.interceptors.response.use((response) => response, forceLogoutOn401)

export default api
