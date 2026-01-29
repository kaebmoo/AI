import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ConfigProvider } from 'antd'
import App from './App.tsx'
import './index.css'

const queryClient = new QueryClient()

console.log('App starting... (Full Mode)');

class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { hasError: boolean, error: Error | null }> {
  constructor(props: any) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: any) {
    console.error("Uncaught error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 20, color: 'red' }}>
          <h1>Something went wrong.</h1>
          <pre>{this.state.error?.toString()}</pre>
          <pre>{this.state.error?.stack}</pre>
        </div>
      );
    }

    return this.props.children;
  }
}

try {
  const root = ReactDOM.createRoot(document.getElementById('root')!)
  console.log('Root created, rendering...');
  root.render(
    <React.StrictMode>
      <ErrorBoundary>
        <QueryClientProvider client={queryClient}>
          <ConfigProvider
            theme={{
              token: {
                colorPrimary: '#1677ff',
              },
            }}
          >
            <App />
          </ConfigProvider>
        </QueryClientProvider>
      </ErrorBoundary>
    </React.StrictMode>,
  )
} catch (e) {
  console.error("Critical Error during App initialization:", e);
  document.getElementById('root')!.innerHTML = `<div style="color: red; padding: 20px;">
    <h1>Critical Error</h1>
    <p>The application failed to start.</p>
    <pre>${e}</pre>
    <p>Check console for more details.</p>
  </div>`;
}
