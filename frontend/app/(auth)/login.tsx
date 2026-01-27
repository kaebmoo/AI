import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, ActivityIndicator, KeyboardAvoidingView, Platform, Alert } from 'react-native';
import { useRouter } from 'expo-router';
import { authService } from '../../services/auth';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

export default function LoginScreen() {
    const [email, setEmail] = useState('');
    const [loading, setLoading] = useState(false);
    const router = useRouter();

    const handleLogin = async () => {
        if (!email) {
            Alert.alert('Error', 'Please enter your email');
            return;
        }

        setLoading(true);
        try {
            await authService.login(email);
            router.push({ pathname: '/(auth)/verify', params: { email } });
        } catch (error: any) {
            const msg = error.response?.data?.detail || 'Failed to login';
            // If it's a cooldown, just proceed (for dev convenience or warn user)
            if (msg.includes('wait')) {
                // Check if we should still allow proceeding to verify manually
                Alert.alert('Notice', msg + '\n Proceeding to verification anyway (for existing OTP).');
                router.push({ pathname: '/(auth)/verify', params: { email } });
            } else {
                Alert.alert('Error', msg);
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <SafeAreaView className="flex-1 bg-gray-50 dark:bg-gray-900 justify-center px-6">
            <KeyboardAvoidingView
                behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
                className="w-full max-w-md mx-auto"
            >
                <View className="items-center mb-10">
                    <View className="w-20 h-20 bg-blue-600 rounded-2xl items-center justify-center mb-4 shadow-lg shadow-blue-500/30">
                        <Ionicons name="chatbubbles" size={40} color="white" />
                    </View>
                    <Text className="text-3xl font-bold text-gray-900 dark:text-gray-100">Welcome Back</Text>
                    <Text className="text-gray-500 dark:text-gray-400 mt-2 text-center">
                        Sign in to access your AI Assistant
                    </Text>
                </View>

                <View className="space-y-4">
                    <View>
                        <Text className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1 ml-1">Email Address</Text>
                        <TextInput
                            className="w-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl px-4 py-3.5 text-gray-900 dark:text-gray-100"
                            placeholder="name@ntplc.co.th"
                            placeholderTextColor="#9CA3AF"
                            value={email}
                            onChangeText={setEmail}
                            autoCapitalize="none"
                            keyboardType="email-address"
                        />
                    </View>

                    <TouchableOpacity
                        onPress={handleLogin}
                        disabled={loading}
                        className={`w-full bg-blue-600 rounded-xl py-4 items-center shadow-lg shadow-blue-500/20 active:opacity-90 ${loading ? 'opacity-70' : ''}`}
                    >
                        {loading ? (
                            <ActivityIndicator color="white" />
                        ) : (
                            <Text className="text-white font-semibold text-lg">Send OTP</Text>
                        )}
                    </TouchableOpacity>
                </View>

                <View className="mt-8 items-center">
                    <Text className="text-xs text-gray-400">
                        Internal Use Only • NT PLC
                    </Text>
                </View>
            </KeyboardAvoidingView>
        </SafeAreaView>
    );
}
