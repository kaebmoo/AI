import React, { createContext, useContext, useEffect, useState } from 'react';
import { storage } from '../services/storage';
import { useRouter, useSegments } from 'expo-router';

interface AuthContextType {
    token: string | null;
    isLoading: boolean;
    signIn: (token: string) => Promise<void>;
    signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
    token: null,
    isLoading: true,
    signIn: async () => { },
    signOut: async () => { },
});

export function useAuth() {
    return useContext(AuthContext);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [token, setToken] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const segments = useSegments();
    const router = useRouter();

    useEffect(() => {
        const loadToken = async () => {
            try {
                const storedToken = await storage.getItem('session_token');
                if (storedToken) {
                    setToken(storedToken);
                }
            } catch (e) {
                console.error('Failed to load token', e);
            } finally {
                setIsLoading(false);
            }
        };
        loadToken();
    }, []);

    useEffect(() => {
        console.log('[AuthContext] State changed:', { token, isLoading, segments: segments.join('/') });
        if (isLoading) return;

        const inAuthGroup = segments[0] === '(auth)';

        if (!token && !inAuthGroup) {
            console.log('[AuthContext] Redirecting to login');
            router.replace('/(auth)/login');
        } else if (token && inAuthGroup) {
            console.log('[AuthContext] Redirecting to app');
            // Try explicit path
            router.replace('/');
        }
    }, [token, segments, isLoading]);

    const signIn = async (newToken: string) => {
        console.log('[AuthContext] Signing in...');
        await storage.setItem('session_token', newToken);
        setToken(newToken);
        console.log('[AuthContext] Token set');
    };

    const signOut = async () => {
        await storage.removeItem('session_token');
        setToken(null);
    };

    return (
        <AuthContext.Provider value={{ token, isLoading, signIn, signOut }}>
            {children}
        </AuthContext.Provider>
    );
}
