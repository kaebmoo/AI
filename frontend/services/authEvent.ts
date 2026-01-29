
// Simple event emitter for auth events
type AuthCallback = () => void;

class AuthEventEmitter {
    private listeners: AuthCallback[] = [];

    subscribe(callback: AuthCallback) {
        this.listeners.push(callback);
        return () => {
            this.listeners = this.listeners.filter(cb => cb !== callback);
        };
    }

    emitSignOut() {
        this.listeners.forEach(cb => cb());
    }
}

export const authEvents = new AuthEventEmitter();
