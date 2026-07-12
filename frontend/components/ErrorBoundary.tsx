import React from 'react';
import { View, Text } from 'react-native';

interface Props {
    children: React.ReactNode;
    /** Optional custom fallback UI. Defaults to a compact red error card. */
    fallback?: React.ReactNode;
    /** Context label for logging (e.g. "ChatBubble"). */
    label?: string;
}

interface State {
    hasError: boolean;
}

/**
 * Catches render/lifecycle errors in its subtree so an unexpected data shape
 * (e.g. a malformed chart_config that crashes DataChart) shows a fallback card
 * instead of white-screening the whole app. Defense-in-depth: even errors we
 * never anticipated surface visibly here.
 */
export class ErrorBoundary extends React.Component<Props, State> {
    state: State = { hasError: false };

    static getDerivedStateFromError(): State {
        return { hasError: true };
    }

    componentDidCatch(error: unknown, info: unknown) {
        // Always log so unknown/unpredicted render errors are diagnosable
        console.error(`[ErrorBoundary${this.props.label ? ':' + this.props.label : ''}]`, error, info);
    }

    render() {
        if (this.state.hasError) {
            if (this.props.fallback !== undefined) return this.props.fallback;
            return (
                <View style={{
                    padding: 12, marginVertical: 8, borderRadius: 12,
                    backgroundColor: '#FEF2F2', borderWidth: 1, borderColor: '#FECACA',
                }}>
                    <Text style={{ color: '#991B1B', fontSize: 13, lineHeight: 20 }}>
                        ⚠️ แสดงผลส่วนนี้ไม่สำเร็จ (ข้อมูลไม่รองรับการแสดงผล) — ส่วนอื่นยังใช้งานได้ตามปกติ
                    </Text>
                </View>
            );
        }
        return this.props.children;
    }
}
